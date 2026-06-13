# Research: Scalable Job-Pool Retrieval

**Feature**: 027-job-retrieval-scaling · **Date**: 2026-06-13

This consolidates the design decisions for the three stages. The unifying idea: today retrieval and exact scoring are fused (the engine runs the full composite `_score_pair_fast` over **every** job, then keeps the top `retrieve_n`). We split them into a cheap **recall** step (embedding similarity over N) and an exact **scoring** step (composite + rerank over a small shortlist), then make the recall step progressively cheaper to store and update.

---

## D1 — Retrieval/scoring split & the swappable retriever interface (all stages)

**Decision**: Introduce a `Retriever` boundary: `shortlist(cv_text_vec, cv_gnn_emb, k) -> list[(job_idx, sim)]`. Three implementations selected by `RETRIEVAL_MODE`:
- `exact` — current behaviour: composite score over the whole pool (the existing loop), no approximation. The A/B baseline.
- `vector` (Stage A) — in-memory vectorized embedding similarity over the whole pool.
- `pgvector` (Stage B) — ANN nearest-neighbour in Postgres.

The engine's `match_cv` always: `cand = retriever.shortlist(...)` → run the **existing** `_score_pair_fast` composite + reranker + calibration over `cand` only. Scoring/rerank/calibration code is untouched.

**Rationale**: One seam makes each stage a drop-in and keeps `exact` as a permanent, bit-for-bit fallback for A/B and incident rollback. The hybrid 4-term formula, reranker, and Platt calibration never move — only *which indices* reach them changes.

**Alternatives considered**: (a) Rewrite scoring to be fully vectorized including skill/seniority/domain — rejected: those terms are lookup/rule-based, hard to vectorize correctly, and vectorizing them is unnecessary once they only run on ~1000 candidates. (b) Replace retrieval **and** scoring with ANN — rejected: loses the exact composite that defines match quality.

---

## D2 — Stage A: in-memory vectorized recall

**Decision**: Compute recall similarity in one matmul over the precomputed pool matrices already in memory (`self._job_embeddings`, `self._job_text_vecs`):

```
sim_gnn  = l2norm(cv_gnn_emb)  @ l2norm(self._job_embeddings).T     # (N,)
sim_text = l2norm(cv_text_vec) @ l2norm(self._job_text_vecs).T      # (N,)
recall   = W_GNN * sim_gnn + W_TEXT * sim_text                       # (N,)
idx      = np.argpartition(-recall, K)[:K]                           # top-K, unsorted O(N)
```

- Job-side norms are **precomputed once** at pool load/snapshot-reload (store `_job_embeddings_unit`, `_job_text_unit`), so per-request cost is two mat-vec products + an `argpartition`.
- `RETRIEVE_K` (shortlist size) configurable, default **1000** (≫ current `retrieve_n=200`, generous for recall). The existing `retrieve_n` then selects the final candidates from within the exactly-scored shortlist, unchanged.
- `W_GNN`/`W_TEXT` recall weights: default to mirror the dominant composite terms (GNN-heavy); tuned only if parity needs it. These gate *recall*, not the final score, so exact ranking is unaffected as long as the right jobs are in the shortlist.

**Rationale**: Removes the Python-loop O(N) with a BLAS O(N·D) that is 10–100× faster and flat to ~1M rows. Reuses matrices that already exist; no new storage.

**Validation gate**: `eval_matching` on-domain@k ≥ baseline AND calibrated P within tolerance on the fixed 20-CV set. If a candidate that the exact path ranked in top-k is missing, raise `RETRIEVE_K` (or rebalance `W_*`) until parity. A debug mode logs recall@shortlist (fraction of exact-top-k present in the vector shortlist) per eval CV.

**Open parameter**: tolerance for calibrated P drift — proposed **±0.005 absolute** on the 20-CV displayed probabilities (ties at the 0.995 saturation cap excluded). Final value confirmed during implementation against observed noise.

---

## D3 — Stage B: pgvector ANN

**Decision**: Add the `vector` extension and a `job_pool_vec` table holding per-job `gnn_emb vector(D)` + `text_vec vector(384)` + `model_fingerprint` + `content_hash` + `updated_at`. Build an **HNSW** index on `gnn_emb` with cosine ops. Retrieval:

```sql
SELECT job_id FROM job_pool_vec
WHERE model_fingerprint = %(fp)s
ORDER BY gnn_emb <=> %(cv_gnn_emb)s
LIMIT %(k)s;
```

→ map `job_id`→`job_idx` → exact composite + rerank in-process (same as Stage A from there on). Per-job `upsert`. `model_fingerprint` (sha of model weights, same scheme as the snapshot compatibility check) guards against serving embeddings from a different model — on mismatch the engine ignores pgvector and falls back (`vector` then `exact`).

**Rationale**: HNSW gives high recall at low `ef_search` and supports incremental insert (no full reindex), which Stage C needs. Postgres is already in the stack; no new datastore. The text-vec column is stored for completeness/future hybrid ANN but recall ranks on `gnn_emb` (the dominant term) to keep the query single-index.

**Alternatives considered**: (a) IVFFlat — rejected: needs periodic retrain of lists as data grows and worse incremental-insert story than HNSW. (b) FAISS in-process — rejected for now: another artifact to persist/reload and no transactional upsert; pgvector reuses the DB we already operate. Revisit only if DB-side ANN latency disappoints.

**Tuning**: HNSW `m` (default 16) and `ef_search` (raise until recall@shortlist parity with Stage A on `eval_matching`); record chosen values in the plan/quickstart. `LIMIT k` = same `RETRIEVE_K` as Stage A so downstream is identical.

---

## D4 — Stage C: incremental rebuild

**Decision**: Give each pooled job a `content_hash` = stable hash of the JobData fields that affect encoding (canonical skills + importances + seniority + the text used for the MiniLM vector). Persist the prior `{job_id: content_hash}` map (in snapshot meta for `vector` mode, in `job_pool_vec.content_hash` for `pgvector` mode). On rebuild:

1. Build `get_all_job_data()` (unchanged eligibility: active + ≥2 skills).
2. Diff vs stored hashes → `to_encode = new ∪ changed`, `to_drop = removed`, `unchanged = reuse`.
3. Inductively encode only `to_encode`; carry forward existing embeddings for `unchanged`.
4. Upsert deltas (snapshot rewrite for `vector`; row upsert/delete for `pgvector`).

`--full` flag forces from-scratch (ignore stored hashes). A periodic full rebuild (weekly, added to `morning_refresh`) is the safety net against hash-logic drift.

**Rationale**: Refresh cost becomes O(new+changed) instead of O(catalog). Content-hash (not `updated_at` alone) catches edits that don't bump a timestamp and avoids re-encoding on no-op saves.

**Correctness gate**: an incremental refresh of an unchanged catalog must produce a byte-identical pool (same embeddings, same order) as `--full`; a CI/manual check diffs the two.

**Edge**: removed/now-ineligible jobs (dropped below 2 skills, deactivated) must be evicted from the pool/index, not left stale.

---

## D5 — Rollout, flags, and safety

**Decision**: `RETRIEVAL_MODE` (env/settings) = `exact | vector | pgvector`, default starts `exact`, flips to `vector` after Stage A passes its gate, to `pgvector` after Stage B. Each stage is independently revertible by flipping the flag — no schema or code from a later stage is required by an earlier one. `eval_matching` is run and recorded (before/after numbers in the plan's progress notes) as the merge gate for every stage. Snapshot/in-memory path is retained as the `vector` fallback even after `pgvector` ships.

**Rationale**: De-risks an ML-sensitive change set: ship the cheap, reversible win (A) first; add infrastructure (B) only when scale demands; keep ops efficiency (C) orthogonal. Nothing forces adopting B or C.

---

## Resolved unknowns

| Question | Resolution |
|---|---|
| Can the composite be fully vectorized? | No — only recall (embedding) is vectorized; skill/seniority/domain stay exact on the shortlist. |
| Shortlist size? | `RETRIEVE_K` default 1000, tuned up to parity. |
| ANN engine? | pgvector **HNSW** (incremental insert, reuses Postgres). |
| Change detection for incremental? | content_hash of encode-affecting fields + periodic full rebuild. |
| How to guarantee no quality regression? | `eval_matching` on-domain@k ≥ baseline + calibrated-P tolerance gate, per stage; `exact` mode as permanent A/B baseline. |
| Index/model mismatch? | `model_fingerprint` guard → fall back to `vector`/`exact`. |
