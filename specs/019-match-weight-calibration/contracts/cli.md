# Contract: `tune_hybrid_weights` command + weight config

## `python manage.py tune_hybrid_weights [--grid 0.05] [--val-frac 0.2] [--seed 42] [--write] [--out specs/019-match-weight-calibration/ablation.md]`

**Purpose**: Select the hybrid weights `(α, β, γ)` by grid-search on a held-out labeled validation set, emit the ablation table, and (optionally) persist the winner.

**Behaviour**:
1. Load the engine (checkpoint). Extract labeled pairs from the graph `match`/`no_match` edges; assert both classes present (else degrade per research R7).
2. Compute `(gnn, skill, seniority)` per pair once. Seeded `--val-frac` split.
3. Sweep `α+β+γ=1` on the `--grid` lattice; for each combo compute AUC (+ NDCG@10, P@10) on the validation split.
4. Print + write the ablation table (sorted by AUC desc; mark the winner and the legacy `(0.55,0.30,0.15)` row).
5. With `--write`: persist the winner to checkpoint `metadata.json` (`hybrid_weights` + `hybrid_weights_meta`).

**Flags**:
- `--grid` (default 0.05): lattice step.
- `--val-frac` (default 0.2), `--seed` (default 42): deterministic split.
- `--write`: persist the winner (omit for a dry analysis).
- `--out`: ablation table path.

**Exit**: non-zero if the validation split lacks both classes and no fallback applies, or no labeled edges exist.

**Output (example)**:
```
Pairs: 4120 (match 1890 / no_match 2230) · val 824
Best: α=0.50 β=0.35 γ=0.15  AUC=0.842  (legacy 0.55/0.30/0.15 AUC=0.835)
Ablation → specs/019-match-weight-calibration/ablation.md
[--write] metadata.json updated
```

## Weight config (single source of truth)

`checkpoints/latest/metadata.json`:
```json
{ "hybrid_weights": {"alpha": 0.50, "beta": 0.35, "gamma": 0.15},
  "hybrid_weights_meta": {"metric": "auc", "auc": 0.842, "grid_step": 0.05} }
```
- `InferenceEngine.from_checkpoint` reads `hybrid_weights` → passes to `__init__`. Absent → defaults `(0.55,0.30,0.15)` + warning.
- `ml_service/config/settings.py` MUST NOT define competing hybrid weights after this change.

## Dimension scores (no new endpoint)

`dim_scores` continues to flow `engine → EmployeeJobMatch.dim_scores → serializer → UI` unchanged in shape; only the producing logic changes (transparent formulas). Existing matches show the new values after a re-match ("Refresh jobs" / `morning_refresh`).
