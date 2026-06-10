# Quickstart: Inductive Live-Catalog Job Ranking

## Build the rankable job pool from the live catalog

```bash
cd backend
# smoke test on a few jobs first (no snapshot written)
.venv/bin/python manage.py rebuild_job_pool --limit 50 --dry-run

# full rebuild + write snapshot (checkpoints/job_pool/)
.venv/bin/python manage.py rebuild_job_pool
# → "Encoded pool: 6536 jobs, 10 skill-skipped edges, ~61s" + "Snapshot saved"
# Measured (SC-005): full 6536-job rebuild ≈ 61s (after the one-embed-pass
# optimization; was ~90s), dominated by sentence-embedding the job texts; the GNN
# forward pass itself is ~1s. Well inside the overnight maintenance window.
```

## Verify a new job becomes rankable

```bash
cd backend
# 1. confirm the pool now covers live Job ids
.venv/bin/python -c "from apps.matching.services.matching_service import _get_engine; e=_get_engine(); print('pool size', e.num_jobs)"

# 2. re-match one employee and confirm 0 skipped + new jobs present
.venv/bin/python manage.py rematch_employees --employee <ID>
# → "+N new, 0 skipped"   (skipped must be 0 now — id space = Job.id)
```

## Ranking sanity-check (regression gate)

The id space changes (JDExtractionRecord-id → Job.id) and the job pool itself
changes on rebuild, so a raw top-K **id/url overlap** vs the old baseline is
confounded (different jobs available) — measured 2–4/10, NOT a quality signal.

The defensible gate is **skill relevance** of the new top-K: every top job should
share ≥1 skill with the CV. Run for a fixed sample and require ≥80% relevant:

```bash
cd backend
.venv/bin/python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from apps.employees.models import Employee
from apps.matching.services.matching_service import match_cv_data
for eid in (18, 20):
    e = Employee.objects.get(pk=eid)
    res = match_cv_data(skills=list(e.skills), seniority=int(e.seniority),
                        experience_years=float(e.experience_years or 0), top_k=10)
    rel = sum(1 for j in res['jobs'] if j.get('matched_skills'))
    print(f'emp{eid}: {rel}/{len(res[\"jobs\"])} skill-relevant')
"
# Measured: emp18 10/10, emp20 10/10 (Vue dev → frontend roles). Gate: >=80%.
```

## Daily automation (after gate passes)

`morning_refresh` runs the rebuild first, then re-match + digest:

```bash
.venv/bin/python manage.py morning_refresh          # rebuild pool → re-match all → digest
.venv/bin/python manage.py morning_refresh --no-digest
```

The live server reloads the pool automatically when the snapshot changes (mtime check in `_get_engine`) — no restart needed. HR clicking "Refresh jobs" sees the latest catalog.

## Roll back

```bash
# remove the snapshot → engine falls back to the frozen checkpoint job pool on next load/reload
rm -rf backend/checkpoints/job_pool
# (restart the server or wait for the next _get_engine load)
```

## Success signals

- `rebuild_job_pool` reports `num_jobs ≈ live Job count`, encode in seconds.
- `rematch_employees` reports **0 skipped** (down from ~25%).
- A job inserted/crawled after training appears in a matching employee's list after a rebuild + re-match (US1).
- Live "Refresh jobs" reflects the new pool with no restart (US2).
- Re-running with an unchanged catalog: **0 new matches, 0 status changes** (SC-006).
