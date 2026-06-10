# Quickstart: Match-Weight Calibration & Transparent Dimensions

## 1. Tune the hybrid weights (dry run → see the ablation table)

```bash
cd backend
.venv/bin/python manage.py tune_hybrid_weights            # analyze only, writes ablation.md
# → Pairs: N (match / no_match) · val M
#   Best: α=.. β=.. γ=..  AUC=..  (legacy 0.55/0.30/0.15 AUC=..)
#   Ablation → specs/019-match-weight-calibration/ablation.md
```

Open `specs/019-match-weight-calibration/ablation.md` — the weight-combo → AUC table for the thesis + slides.

## 2. Adopt the tuned weights (single source of truth)

```bash
.venv/bin/python manage.py tune_hybrid_weights --write     # persist winner to metadata.json
# restart the server (or it loads on next engine init)
```

Verify one source only:
```bash
grep -rn "hybrid_alpha\|0.55\|0.30\|0.15" ml_service/config/settings.py   # should be gone/realigned
python -c "import json; print(json.load(open('checkpoints/latest/metadata.json'))['hybrid_weights'])"
```

## 3. Verify transparent dimension scores (reproduce by hand)

```bash
# Re-match a sample employee so dim_scores use the new formulas
.venv/bin/python manage.py rematch_employees --employee 20
.venv/bin/python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from apps.employees.models import EmployeeJobMatch
m = EmployeeJobMatch.objects.filter(employee_id=20).order_by('-match_score').first()
print('dims:', m.dim_scores, '| matched:', m.matched_skills, '| missing:', m.missing_skills, '| sen_gap:', m.seniority_gap)
"
# Hand-check: skill_fit ≈ Σimp(matched)/Σimp(required); seniority_fit ≈ max(0,1-|gap|·0.3); etc.
```

## Success signals

- `tune_hybrid_weights` prints an ablation table; the chosen AUC ≥ the legacy `0.55/0.30/0.15` AUC (SC-004).
- Re-running with the same `--seed` reproduces the same winner (SC-005).
- Exactly one definition of the hybrid weights remains in the code (SC-002).
- Each of the 4 dimension scores is reproducible by hand from the match's data (SC-003).
- The "Why it matches" accordion shows the same four % bars, now formula-backed.

## Defense talking point

> "The matching core is a learned GNN + reranker. The weights that blend GNN, skill and seniority into the overall score were selected by grid-search on a held-out labeled validation set (AUC in the ablation table), not set by hand. The four per-dimension fit scores are transparent, formula-based interpretability diagnostics — each reproducible by hand from the candidate–job data."
