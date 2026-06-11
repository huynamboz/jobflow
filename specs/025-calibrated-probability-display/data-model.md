# Data Model — Calibrated Probability Display

## Calibration artifact (`checkpoints/<dir>/calibration.json`)

| Field | Type | Semantics |
|---|---|---|
| `a` | float | sigmoid slope — `P = 1/(1+exp(-(a·s+b)))` |
| `b` | float | sigmoid offset |
| `fitted` | bool | usable flag; `false`/missing → serving falls back loudly to raw rank_score |
| `trained_with` | str (NEW) | `sha256(reranker.pt)[:16]` of the reranker this calibrator was fitted against; engine warns at boot on mismatch with the serving reranker |

Schema is backward compatible: old artifacts lack `trained_with` → treated as
stale (warn), still usable.

## Match result (engine `JobMatchResult` → API → `EmployeeJobMatch` row)

| Field | Before | After |
|---|---|---|
| `score` / `match_score` | stage-1 value remapped per basket (relative) | `calibrator.transform(rank_score)` — absolute probability, comparable across employees, stable across runs |
| `eligible` | `score >= 0.65 × basket top` (relative) | `score >= ELIGIBLE_MIN_PROB (0.50)` (absolute) |
| `score_breakdown` | weights, stage1 components, reranker, gates, penalty_product, rank_score | + `calibrated` (the displayed probability) — closes the chain rank_score → display |
| `match_level` | thresholds on raw reranker score (0.30/0.22) | unchanged |

No DB migrations: `match_score` stays float; `score_breakdown` is a JSONField.

## Invariants

1. **Monotonicity**: `display = sigmoid(a·rank_score + b)` with `a > 0` →
   display order ≡ rank order, globally, by construction. (Fit asserts `a > 0`;
   a non-positive slope would mean the ranking signal anti-predicts labels —
   fail the fit loudly in that case.)
2. **Determinism**: same (cv, job, model, calibrator) → same displayed score,
   independent of basket composition.
3. **Single gate source**: penalty gates computed by `_penalty_product` only —
   serving loop and fit-time share it (parity-tested).

## Rollout artifacts (spec-dir local, not shipped)

- `order_before.json` — `{employee_id: [job_id, ...]}` engine-output order
  captured pre-change; the order-invariance gate diffs against it post-change.
