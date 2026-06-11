# Contract — Calibration artifact & serving behavior

## Artifact: `calibration.json`

```json
{
  "a": 7.83,                      // sigmoid slope, MUST be > 0 (fit fails loudly otherwise)
  "b": -5.12,                     // sigmoid offset
  "fitted": true,
  "trained_with": "3fa9c2d1e07b44a8"  // sha256(reranker.pt)[:16] at fit time
}
```

Producer: `train_reranker.py` (after reranker training, fitted on val
rank_scores = reranker × penalty via `engine.rank_scores_for_pairs`).
Consumer: `InferenceEngine` at boot.

## Serving contract

| Condition at boot | Behavior |
|---|---|
| artifact present, fitted, stamp == sha256(serving reranker.pt)[:16] | display = `transform(rank_score)`; no log |
| artifact present, fitted, stamp mismatch / missing stamp | display = `transform(rank_score)`; **WARNING** log: calibration stale, refit via train_reranker |
| artifact missing or `fitted: false` | display = raw `rank_score`; **WARNING** log once: "calibration unavailable — displaying raw rank score" |

The per-basket min-max remap does not exist in any branch.

## API surface (unchanged shape, changed semantics)

`GET /api/employees/.../matches` rows:
- `match_score`: float in [0,1] — **absolute calibrated probability** (was:
  basket-relative). Comparable across employees and stable across reruns.
- `score_breakdown.calibrated`: float — equals `match_score` (chain closure).
- `score_breakdown.rank_score`: float — pre-calibration ordering signal.
- `eligible`: bool — `match_score >= 0.50` (was: `>= 0.65 × basket top`).

## Fit-quality report (train_reranker log)

After fitting, log a reliability table over val pairs: per score-decile —
`n, mean_predicted_P, observed_match_rate`. Gates (from spec SC-005):
- every populated decile: |mean_predicted − observed| ≤ 0.15
- predicted span over observed score range ≥ 0.5
- slope `a > 0`
Violation → loud log; `a ≤ 0` → refuse to save (fitted stays false).
