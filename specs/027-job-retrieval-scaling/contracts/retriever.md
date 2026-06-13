# Contract: Retriever interface

**Feature**: 027-job-retrieval-scaling · **Date**: 2026-06-13

The single seam this feature introduces. All three stages are implementations of this interface; the engine depends only on the interface, selected by `RETRIEVAL_MODE`.

## Interface

```python
# ml_service/inference/retrieval/base.py
class Retriever(Protocol):
    def shortlist(
        self,
        cv_text_vec: np.ndarray,   # (384,)  MiniLM CV text vector
        cv_gnn_emb:  np.ndarray | None,  # (D,) inductive CV GNN emb; None when no GNN
        k: int,                    # RETRIEVE_K
    ) -> list[tuple[int, float]]:  # [(job_idx, recall_sim)], len ≤ k, descending sim
        ...
```

### Semantics (all implementations MUST honor)

1. **Returns pool indices**: each `job_idx` indexes `engine._jobs` (so downstream exact scoring is unchanged). `pgvector` maps its `job_id` → `job_idx` before returning.
2. **Eligibility preserved**: only pool-eligible jobs (active + ≥2 skills) are ever returned — never an ineligible/stale job.
3. **Bounded size**: returns at most `k` items; fewer only if the pool has fewer eligible jobs.
4. **Recall, not final score**: `recall_sim` orders the *shortlist*; it does NOT replace the 4-term hybrid/calibrated score. The engine re-scores the shortlist with the existing composite + reranker + calibration. So two retrievers returning the same set yield identical final results regardless of `recall_sim` values.
5. **Deterministic given the pool**: same inputs + same pool ⇒ same set (ANN `ef_search` fixed). Ties broken by `job_idx` for stable output.

## Implementations

| Mode | Recall source | Cost | Use when |
|---|---|---|---|
| `exact` | full composite `_score_pair_fast` over all N (today's loop) | O(N), Python | A/B baseline, rollback, parity reference |
| `vector` | `argpartition` over `W_GNN·(cv_gnn·J_gnnᵀ)+W_TEXT·(cv_txt·J_txtᵀ)` | O(N·D), BLAS | default ≤ ~1M jobs |
| `pgvector` | SQL `ORDER BY gnn_emb <=> cv_gnn_emb LIMIT k` (HNSW) | sublinear | 200k+ jobs |

### `exact` (baseline) — MUST be bit-for-bit
`ExactRetriever.shortlist` returns the top-`k` by the **full composite** — i.e. it reproduces today's `retrieve_n` selection exactly. This is the parity oracle: with `RETRIEVAL_MODE=exact` and `k=retrieve_n`, results equal pre-feature behaviour byte-for-byte.

### `vector` (Stage A)
Uses precomputed unit-norm matrices. `recall_sim` = blended cosine. Fallback: never (pure in-memory).

### `pgvector` (Stage B)
Queries `job_pool_vec WHERE model_fingerprint = <live fp> ORDER BY gnn_emb <=> cv ... LIMIT k`. On missing table / extension / fingerprint mismatch / empty result for a non-empty pool → **fall back** to `vector` (then `exact`) and log once. `text_vec` stored but recall ranks on `gnn_emb`.

## Quality contract (gate for every implementation)

A retriever passes only if, on the fixed 20-CV `eval_matching` set vs the `exact` baseline:
- **on-domain@k**: ≥ baseline (no regression), AND
- **calibrated P drift**: |ΔP| ≤ tolerance (proposed ±0.005) per displayed pair (excluding 0.995-saturation ties), AND
- **recall@shortlist**: fraction of `exact`-top-`top_k` candidates present in the shortlist ≥ target (≈1.0 at tuned `RETRIEVE_K`).

`eval_matching` reports these three numbers; a stage cannot flip its default mode until they pass.

## Non-contract (explicitly unchanged)

- `JobMatchResult` shape, the 4-term hybrid formula, reranker inputs/outputs, Platt calibration, `EmployeeJobMatch` rows, and the matching API responses are **untouched**. This contract governs only candidate selection.
