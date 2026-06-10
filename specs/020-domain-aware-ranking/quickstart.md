# Quickstart: Domain-Aware Ranking

## 0. Baseline — see the bug (before)

```bash
cd backend
.venv/bin/python manage.py eval_matching          # current weights (δ=0, feature 019)
# → backend/devops/data CVs show VFX/animation/non-tech jobs on top; low top1_on_domain rate
```

## 1. Tune the 4 weights on the role-aware metric (dual ablation)

```bash
.venv/bin/python manage.py tune_hybrid_weights              # dry: writes specs/020/ablation.md
# → dual table: chosen (role-NDCG max) vs label-AUC-max (the β-heavy feature-019 winner) vs legacy
.venv/bin/python manage.py tune_hybrid_weights --write      # persist 4 weights to metadata.json
```

Open `specs/020-domain-aware-ranking/ablation.md` — the dual-metric table for the thesis (shows label-AUC and role-aware NDCG/P@10 favoring different weights).

## 2. Adopt + re-evaluate (after)

```bash
# restart the server / reload engine so it picks up the 4 tuned weights
.venv/bin/python manage.py eval_matching          # tuned weights (δ>0)
# → IT CVs now show on-domain jobs on top; top1_on_domain rate materially higher
```

## 3. Re-match employees to adopt new scores

```bash
.venv/bin/python manage.py rematch_employees       # or morning_refresh
```

## Success signals

- `eval_matching` `top1_on_domain` rate ≥ 90% after (vs the lower before) — SC-001.
- 0 IT CVs with an animation/VFX/non-tech #1 match — SC-002.
- The tuned weights keep a non-trivial GNN weight (α clearly > the label-AUC-only ~0.20) — SC-003.
- The dual ablation shows the two objectives favor different weights — SC-004.
- A fullstack CV still matches frontend/backend roles (domain stayed soft) — SC-006.

## Defense talking point

> "Tuning on label-AUC alone produced skill-dominant weights that ranked domain-mismatched jobs at the top (a backend CV → VFX jobs sharing 'python'). We added the role/domain signal to the score and re-tuned on a role-aware ranking metric (NDCG@10). The dual-metric ablation shows label-AUC and role-aware ranking favor different weights; the role-aware objective restores the GNN's weight and removes the cross-domain noise — verified by a reproducible 20-CV evaluation. This is evidence that a single pairwise metric can be misleading and that the semantic GNN signal matters for real ranking quality."
