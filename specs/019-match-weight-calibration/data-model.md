# Phase 1 Data Model: Defense-Ready Match-Weight Calibration

No database schema changes. This feature touches model-metadata, an offline artifact, and the in-memory dimension computation.

## Entity 1 — Labeled validation pair (extracted, in-memory)

Pulled from the checkpoint graph's label edges.

| Field | Source | Notes |
|---|---|---|
| `cv_idx` | `("cv","match"\|"no_match","job").edge_index[0]` | index into `self._cvs` |
| `job_idx` | `…edge_index[1]` | index into `self._jobs` |
| `label` | edge type | `1` for `match`, `0` for `no_match` |
| `gnn` | engine GNN pair score | computed once (in-graph embeddings) |
| `skill` | `_semantic_skill_overlap` | computed once |
| `seniority` | `max(0, 1 - |Δsen|·0.4)` | computed once |

Split deterministically (seeded 80/20) into train-unused / validation. Only the validation split scores the weight grid.

## Entity 2 — Hybrid weight record (the tuned weights)

Persisted in checkpoint `metadata.json`:

```json
{ "hybrid_weights": { "alpha": 0.55, "beta": 0.30, "gamma": 0.15 },
  "hybrid_weights_meta": { "metric": "auc", "auc": 0.0, "tuned_at": "", "grid_step": 0.05 } }
```

**Rules**:
- `alpha + beta + gamma == 1.0` (within float tolerance); each `≥ 0`.
- Single source of truth: the engine reads ONLY this; `settings.py` no longer defines competing values.
- Absent → engine falls back to documented defaults `(0.55, 0.30, 0.15)` and logs a warning (backward compatible with un-tuned checkpoints).

## Entity 3 — Ablation table (thesis artifact)

Written to `specs/019-match-weight-calibration/ablation.md` (and printed). One row per weight combo:

| α | β | γ | AUC | NDCG@10 | P@10 |
|---|---|---|-----|---------|------|
| … | … | … | …   | …       | …    |

Sorted by AUC desc; the chosen row + the previous `(0.55,0.30,0.15)` row are highlighted.

## Entity 4 — Per-dimension diagnostics (transparent formulas)

`EmployeeJobMatch.dim_scores` (existing JSONField from feature 018) keeps shape `{skill_fit, experience_fit, seniority_fit, domain_fit}` with values `∈ [0,1]` — now produced by the formulas in [research.md R6], computed in the engine when `JobMatchResult.dim_scores` is built. No schema/serializer/UI change (the UI already renders numeric bars).

| Dimension | Inputs (all on the match) | Output |
|---|---|---|
| skill_fit | matched skills + importances vs job required | `Σimp(matched)/Σimp(required)`, `[0,1]` |
| experience_fit | `cv.experience_years`, `job.experience_min` | `[0,1]`, neutral 1.0 if unknown |
| seniority_fit | `cv.seniority`, `job.seniority` | `max(0, 1-|Δ|·0.3)` |
| domain_fit | inferred cv role, `job.role_category` | `1.0 / 0.5 / 0.0` |

**Invariant**: each value is reproducible by hand from data the UI already shows (matched/missing skills, seniority gap, role) → SC-003.

## Flow

```text
checkpoint graph (match/no_match edges)
   │  extract labeled pairs + compute (gnn, skill, seniority) once
   ▼
validation split (seeded)
   │  sweep α+β+γ=1 (0.05 grid) → AUC per combo
   ▼
ablation.md  +  best (α,β,γ) → metadata.json
   │  engine.from_checkpoint loads hybrid_weights (single source)
   ▼
live matching uses tuned weights  ·  dim_scores from transparent formulas
```
