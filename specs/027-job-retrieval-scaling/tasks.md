---
description: "Task list for 027-job-retrieval-scaling"
---

# Tasks: Scalable Job-Pool Retrieval

**Input**: Design documents from `specs/027-job-retrieval-scaling/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/retriever.md](contracts/retriever.md), [quickstart.md](quickstart.md)

**Tests**: Validation/parity tasks ARE included — the spec makes `eval_matching` (on-domain@k + calibrated-P tolerance + recall@shortlist) the hard merge gate for every stage, so they are not optional here.

**Organization**: By user story. US1 (Stage A) is the MVP; US2/US3 are independent increments behind the same `RETRIEVAL_MODE` seam.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different file, no incomplete dependency)
- Paths are repo-relative; backend root is `backend/`.

---

## Phase 1: Setup (shared infrastructure)

- [ ] T001 Create the retrieval package `backend/ml_service/inference/retrieval/__init__.py` with a `get_retriever(mode, engine)` factory stub returning the right class by `RETRIEVAL_MODE`.
- [ ] T002 [P] Add config defaults in `backend/config/settings.py`: `RETRIEVAL_MODE="exact"`, `RETRIEVE_K=1000`, `W_GNN`, `W_TEXT`, `HNSW_M=16`, `HNSW_EF_SEARCH=64` (env-overridable, documented inline).
- [ ] T003 [P] Capture the pre-change baseline: run `python manage.py eval_matching`, save on-domain@k + the 20-CV calibrated probabilities to `specs/027-job-retrieval-scaling/baseline.md` as the parity reference.

**Checkpoint**: package + settings exist; baseline numbers recorded.

---

## Phase 2: Foundational (BLOCKING — the Retriever seam)

**Purpose**: the interface + the exact baseline that all three stages plug into. Nothing in US1/US2/US3 can start until this is done.

- [ ] T004 Define the `Retriever` Protocol in `backend/ml_service/inference/retrieval/base.py` per [contracts/retriever.md](contracts/retriever.md): `shortlist(cv_text_vec, cv_gnn_emb, k) -> list[tuple[int, float]]`, with the semantics docstring (returns pool indices, eligibility preserved, bounded, recall-not-score, deterministic).
- [ ] T005 Implement `ExactRetriever` in `backend/ml_service/inference/retrieval/exact.py` by extracting today's full-composite loop (`engine.py:435` region) so it returns top-`k` by the existing `_score_pair_fast` — behaviour-identical to current code.
- [ ] T006 Refactor `EngineV2.match_cv` in `backend/ml_service/inference/engine.py`: replace the inline stage-1 loop with `cand = self._retriever.shortlist(cv_text_vec, cv_gnn_emb, RETRIEVE_K)`, then run the EXISTING composite + reranker + calibration over `cand` only. Wire `self._retriever = get_retriever(settings.RETRIEVAL_MODE, self)` at load.
- [ ] T007 Parity test (`backend/apps/matching/tests.py`): with `RETRIEVAL_MODE=exact` and `k=retrieve_n`, assert `match_cv` output (job order + calibrated P) is byte-for-byte identical to the pre-refactor baseline for the 20-CV set.

**Checkpoint**: `RETRIEVAL_MODE=exact` reproduces today's results exactly through the new seam. ⚠️ Gate before any stage.

---

## Phase 3: User Story 1 — Vectorized recall (Stage A, P1) 🎯 MVP

**Goal**: replace O(N) Python recall with a vectorized matmul; identical quality, flat latency to ~100k.
**Independent test**: `RETRIEVAL_MODE=vector` passes the gate on `eval_matching` and is 10–100× faster on a synthetic 100k pool.

- [ ] T008 [US1] Precompute unit-norm pool matrices in `backend/ml_service/inference/engine.py`: build/cache `_job_embeddings_unit` and `_job_text_unit` at pool load AND in the snapshot-reload path (lines ~696-697) so they stay in sync on hot-reload.
- [ ] T009 [US1] Implement `VectorRetriever.shortlist` in `backend/ml_service/inference/retrieval/vector.py`: `recall = W_GNN*(unit(cv_gnn)@J_gnn_unit.T) + W_TEXT*(unit(cv_text)@J_text_unit.T)`; `np.argpartition(-recall, k)[:k]`, sort the K, return `[(idx, sim)]`. Handle `cv_gnn_emb is None` (text-only) and pool smaller than `k`.
- [ ] T010 [US1] Register `vector` in `get_retriever` (`backend/ml_service/inference/retrieval/__init__.py`).
- [ ] T011 [US1] Extend `backend/apps/matching/management/commands/eval_matching.py` with `--report-recall`: compute and print recall@shortlist (fraction of exact-top-`top_k` present in the vector shortlist) and calibrated-P drift vs baseline, per CV + aggregate.
- [ ] T012 [US1] Add a synthetic-inflation latency bench (`backend/apps/matching/management/commands/bench_retrieval.py` or a test): duplicate/perturb the pool to ~100k, time `match_cv` under `exact` vs `vector`, print both.
- [ ] T013 [US1] Validation: run `eval_matching --report-recall` in `vector` mode; tune `RETRIEVE_K`/`W_GNN`/`W_TEXT` until on-domain@k ≥ baseline, |ΔP| ≤ 0.005, recall@shortlist ≈ 1.0. Record final params + numbers in `specs/027-job-retrieval-scaling/baseline.md`.
- [ ] T014 [US1] Flip `RETRIEVAL_MODE` default to `vector` in `backend/config/settings.py` once T013 passes; note rollback (`=exact`).

**Checkpoint**: Stage A shippable — faster, quality-neutral, reversible. **MVP done.**

---

## Phase 4: User Story 2 — pgvector ANN (Stage B, P2)

**Goal**: sublinear retrieval at 200k+ via Postgres ANN; per-job upsert; snapshot fallback.
**Independent test**: `RETRIEVAL_MODE=pgvector` passes the gate and is materially faster than `vector` at 200k+.

- [ ] T015 [US2] Migration in `backend/apps/matching/migrations/`: `CREATE EXTENSION IF NOT EXISTS vector`; create `job_pool_vec` (`job_id` PK/FK CASCADE, `gnn_emb vector(D)`, `text_vec vector(384)`, `model_fingerprint`, `content_hash`, `updated_at`) + HNSW index on `gnn_emb` (`vector_cosine_ops`, `m=HNSW_M`) + btree on `model_fingerprint`. Per [data-model.md](data-model.md).
- [ ] T016 [P] [US2] Add `JobPoolVec` model (managed or unmanaged + raw SQL helper) in `backend/apps/matching/models.py` with an `upsert(job_id, gnn_emb, text_vec, fp, content_hash)` and `delete_missing(job_ids)`.
- [ ] T017 [US2] In `backend/apps/matching/management/commands/rebuild_job_pool.py`, upsert each pooled job's embeddings into `job_pool_vec` (alongside the snapshot) with the live `model_fingerprint`; evict rows for jobs no longer eligible.
- [ ] T018 [US2] Implement `PgVectorRetriever.shortlist` in `backend/ml_service/inference/retrieval/pgvector.py`: SQL `... WHERE model_fingerprint=%s ORDER BY gnn_emb <=> %s LIMIT k` with `SET LOCAL hnsw.ef_search=HNSW_EF_SEARCH`; map `job_id→job_idx`; **fallback** to `vector` then `exact` on missing extension/table, fingerprint mismatch, or empty result for a non-empty pool (log once).
- [ ] T019 [US2] Register `pgvector` in `get_retriever` (`backend/ml_service/inference/retrieval/__init__.py`).
- [ ] T020 [US2] Validation via `backend/apps/matching/management/commands/eval_matching.py --report-recall` in `pgvector`; tune `HNSW_EF_SEARCH` (and `m` if needed) to gate parity with `vector`/`exact`; bench at synthetic 200k+ vs `vector`. Record params + numbers in `specs/027-job-retrieval-scaling/baseline.md`.
- [ ] T021 [US2] Fallback test (`backend/apps/matching/tests.py`): with the table dropped / a mismatched fingerprint, `pgvector` mode serves via `vector` without erroring.
- [ ] T022 [US2] Flip `RETRIEVAL_MODE` default to `pgvector` in `backend/config/settings.py` only when scale warrants (document the decision; not required to ship Stage A/B independently).

**Checkpoint**: Stage B shippable — sublinear at scale, safe fallback, gate-passing.

---

## Phase 5: User Story 3 — Incremental refresh (Stage C, P3)

**Goal**: `rebuild_job_pool` encodes only new/changed jobs; `--full` reproduces from scratch.
**Independent test**: post-crawl refresh encodes only the deltas; incremental == full on an unchanged catalog.

- [ ] T023 [US3] Add `content_hash(JobData) -> str` in `backend/ml_service/inference/pool_diff.py`: sha256 of encode-affecting fields (canonical skills+importances, seniority, encode_text). Per [data-model.md](data-model.md) — identical embedding ⇒ identical hash.
- [ ] T024 [US3] Persist prior hashes: extend snapshot meta (`backend/ml_service/inference/job_pool_snapshot.py`) with a `{job_id: content_hash}` map; for `pgvector` mode reuse `job_pool_vec.content_hash`.
- [ ] T025 [US3] Implement `pool_diff(live_jobdata, stored_hashes)` in `backend/ml_service/inference/pool_diff.py` → `{to_encode, to_reuse, to_drop}`.
- [ ] T026 [US3] Make `backend/apps/matching/management/commands/rebuild_job_pool.py` incremental: diff → inductively encode only `to_encode`, carry forward `to_reuse` embeddings, evict `to_drop`, upsert deltas (snapshot rewrite for `vector`; row upsert/delete for `pgvector`). Add `--full` to force from-scratch.
- [ ] T027 [US3] Correctness test (`backend/apps/matching/tests.py`): on an unchanged catalog, incremental `rebuild_job_pool` produces an embedding+order-identical pool to `--full` (diff = 0); after adding N jobs, only N are encoded (assert via log/counter).
- [ ] T028 [US3] Add a weekly `--full` safety-net rebuild to `morning_refresh` (`backend/apps/matching/management/commands/morning_refresh.py` or its schedule).

**Checkpoint**: Stage C shippable — refresh cost O(new+changed), full rebuild as safety net.

---

## Phase 6: Polish & cross-cutting

- [ ] T029 [P] Update `backend/apps/matching/management/commands/README.md` (or feature docs) with `RETRIEVAL_MODE`, `RETRIEVE_K`, HNSW params, and the per-stage validation/rollback recipe from [quickstart.md](quickstart.md).
- [ ] T030 [P] Update `CLAUDE.md` "Notes / gotchas" with a one-line note: retrieval is now `exact|vector|pgvector` behind `RETRIEVAL_MODE`; `rebuild_job_pool` is incremental (`--full` to force); `eval_matching --report-recall` is the gate.
- [ ] T031 Final gate: run `eval_matching` in the shipped default mode; confirm on-domain@k ≥ baseline and calibrated-P within tol; record in `baseline.md`.

---

## Dependencies & order

- **Phase 1 → Phase 2 → (Phase 3 | Phase 4 | Phase 5)**. Phase 2 (the seam) BLOCKS all stories.
- **US1 (Stage A)** depends only on Phase 2 → ship first (MVP).
- **US2 (Stage B)** depends on Phase 2; reuses US1's shortlist→score split but does not require US1's default to be flipped.
- **US3 (Stage C)** depends on Phase 2; integrates with whichever store is active (snapshot for `vector`, `job_pool_vec` for `pgvector`).
- Validation tasks (T007, T013, T020/T021, T027, T031) are the **gates** — a stage is not "done" until its gate passes.

## Parallel opportunities

- Phase 1: T002, T003 in parallel (different files).
- US2: T016 in parallel with T015's review; T018 after T015–T017.
- Polish: T029, T030 in parallel.

## MVP scope

**Phase 1 + Phase 2 + Phase 3 (US1)** = a complete, shippable, reversible win: vectorized retrieval, quality-neutral, flat latency to ~100k jobs. US2/US3 are added only as scale/ops demand.
