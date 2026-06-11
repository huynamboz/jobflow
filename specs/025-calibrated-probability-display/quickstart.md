# Quickstart — Calibrated Probability Display (rollout runbook)

All commands from `backend/` with `.venv`.

```bash
# 0. SNAPSHOT pre-change engine order (gate input — run BEFORE any code change)
python ../specs/025-calibrated-probability-display/capture_order.py before

# 1-4. implement (calibration.py fit, _penalty_product, rank_scores_for_pairs,
#      _finalize_results) — see tasks.md

# 5. unit tests
python manage.py test apps.matching

# 6. refit calibrator locally (CPU, ~2 min — NO GPU/Neptune needed)
python train_reranker.py --data data/processed/v4_relabel --checkpoint checkpoints/latest --calibrate-only
#    → check log: reliability table, span ≥ 0.5, a > 0; calibration.json has trained_with

# 7. ORDER-INVARIANCE GATE
python ../specs/025-calibrated-probability-display/capture_order.py after   # diffs vs before; exits 1 on any mismatch

# 8. eval suites (all must stay 100%)
python manage.py eval_matching
python /tmp/eval_holdout.py & python /tmp/eval_30cv.py; python /tmp/eval_realcv.py

# 9. rollout
python manage.py rematch_employees
kill server && python manage.py runserver 8000   # boot log: no stale-calibration warning

# 10. CURL VERIFY (absolute scores, chain closure, eligible sane)
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login/ -H 'Content-Type: application/json' -d '{"username":"...","password":"..."}' | jq -r .access)
curl -s "localhost:8000/api/employees/matches/?employee=20&page_size=3" -H "Authorization: Bearer $TOKEN" \
  | jq '.results[] | {job: .job, score: .match_score, calibrated: .score_breakdown.calibrated, rank: .score_breakdown.rank_score, eligible}'
# expectations: match_score == calibrated; sorted desc by rank; same pair → same score across employees' lists
```

Done-when: order identical · 4 evals 100% · reliability gates pass · curl shows
absolute scores with closed breakdown chain · docs caveat removed.
