# Phase 0 Research: Defense-Ready Match-Weight Calibration

All resolved against the current source — no open NEEDS CLARIFICATION.

## R1. Where the validation labels live

**Decision**: Use the `("cv","match","job")` and `("cv","no_match","job")` edges stored in the checkpoint `graph.pt` as the labeled pairs (label = 1 / 0). They are present on `self._data` and stripped at encode time by `_strip_label_edges`.

**Rationale**: There is no separate `pairs.json` in the checkpoint; the supervision lives in the graph as match/no_match edges (`builder.build` writes them, line ~217). Both CV and Job of every labeled pair are in-graph nodes, so their GNN embeddings are precomputed — the 3 score components can be computed without re-encoding.

**Alternatives**: Regenerate pairs from the labeling DB — rejected (the checkpoint's edges are the exact training labels; reusing them keeps the validation faithful to what the model saw, and we hold out a split for selection).

## R2. The three score components per pair

**Decision**: For each labeled `(cv_idx, job_idx)`, compute:
- `gnn` = the engine's GNN pair score (decode of the in-graph cv/job embeddings, same as `_gnn_score_fast`).
- `skill` = the engine's `_semantic_skill_overlap(cv, job)`.
- `seniority` = `max(0, 1 - |cv.sen - job.sen| · 0.4)` (same seniority term as `_score_pair_fast`).

Then `score = α·gnn + β·skill + γ·seniority`. Compute the 3 components ONCE per pair; the grid sweep only re-weights them.

**Rationale**: These are exactly the three terms the live `_score_pair_fast` blends, so the tuned weights apply 1:1 to production. Computing components once makes the whole grid sweep a cheap vectorized re-weighting.

## R3. Selection metric

**Decision**: **AUC** (`roc_auc_score`) of `score` vs the binary label on the held-out validation split is the primary objective. Report **NDCG@10** and **precision@10** (grouped by CV) as secondary columns in the ablation table.

**Rationale**: AUC directly measures how well a *single scalar* separates match from no_match across all pairs — the precise question "are these weights good?". It needs both classes present (R7). NDCG/precision@k add a ranking-quality view per CV for the thesis narrative.

**Alternatives**: Optimize precision@k alone — rejected as primary (k-sensitive, needs per-CV grouping that some CVs may not support); AUC is the robust default.

## R4. Grid + determinism

**Decision**: Sweep `(α, β, γ)` on a **0.05 grid** with `α+β+γ=1`, `α,β,γ ≥ 0` (≈ 231 combos). Fixed validation split via a **seeded** shuffle (e.g. 80/20, `random_state=42`). Tie-break: on equal AUC, prefer the combo closest to the current `(0.55,0.30,0.15)` (stable, minimizes churn), else lexicographic.

**Rationale**: 0.05 is fine enough to be meaningful, coarse enough to enumerate + tabulate for a slide. Seed + deterministic tie-break → SC-005 (re-run reproduces the same choice).

## R5. Single source of truth for the weights (config unification)

**Decision**: Persist the chosen weights in the checkpoint **`metadata.json`** under `hybrid_weights: {alpha, beta, gamma}`. `InferenceEngine.from_checkpoint` reads them and passes to `__init__` (falling back to documented defaults if absent). **Remove** the stale `hybrid_alpha/beta/gamma` from `ml_service/config/settings.py` (or repoint them as documentation only) so no contradictory definition remains.

**Rationale**: `metadata.json` already travels with the model and is already loaded in `from_checkpoint` (`node_dims`, `train_config`). Weights belong with the model that produced them. One load path = one source of truth (FR-003, SC-002).

**Alternatives**: A new YAML/env config — rejected (adds a separate artifact to keep in sync; metadata.json already exists and is model-coupled).

## R6. Transparent per-dimension formulas (replace aux heads)

**Decision**: Build `JobMatchResult.dim_scores` (engine ~line 381) from explicit formulas of the match's own data, each `∈ [0,1]`, mirroring the FeatureExtractor's existing feature definitions so "skill fit" keeps its meaning:

| Dimension | Formula | Source feature it mirrors |
|---|---|---|
| `skill_fit` | importance-weighted matched / total required importance (`Σ imp(matched) / Σ imp(required)`); `1.0` if job lists no skills | `_weighted_overlap` |
| `experience_fit` | `1.0` if `job.experience_min` unknown/0; else `clip(1 - max(0, exp_min - cv_exp)/exp_min, 0, 1)` (under-qual penalized; meeting/exceeding → 1) | `experience_gap` |
| `seniority_fit` | `max(0, 1 - |cv.sen - job.sen| · 0.3)` | `seniority_score` |
| `domain_fit` | `1.0` if `cv_role == job.role_category`; `0.5` if job role unknown; else `0.0` | `role_category_match` |

The reranker's **main head still reorders** candidates; only the **aux-head dimension output** is no longer used for display.

**Rationale**: Every number is hand-reproducible from data shown in the UI (FR-004, SC-003) and free of the unknown aux-label provenance (FR-008). Mirroring existing feature definitions keeps semantics consistent with what the model already used.

**Alternatives**: Keep aux heads but document labels — rejected (label source unrecoverable; transparency is the defense win).

## R7. Risk — label balance for AUC

**Decision**: Before sweeping, assert the validation split contains BOTH match and no_match pairs (AUC undefined otherwise). If the graph has only positive edges, fall back to: sample hard negatives (random CV×job not in match set) OR report precision@k only, and surface the limitation.

**Rationale**: AUC needs both classes. The graph DOES store `no_match` edges (negative supervision from training), so balance is expected — but the command must verify and degrade gracefully.

## R8. No-regression guarantee

**Decision**: The chosen weights are AUC-maximizing over a grid that **includes** `(0.55,0.30,0.15)` (it lies on the 0.05 lattice), so by construction the selected AUC ≥ the current weights' AUC (FR-006, SC-004). The ablation table will show both rows.
