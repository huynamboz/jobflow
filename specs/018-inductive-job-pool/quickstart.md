# Quickstart: Inductive Live-Catalog Job Ranking

## Build the rankable job pool from the live catalog

```bash
cd backend
# smoke test on a few jobs first (no snapshot written)
.venv/bin/python manage.py rebuild_job_pool --limit 50 --dry-run

# full rebuild + write snapshot (checkpoints/job_pool/)
.venv/bin/python manage.py rebuild_job_pool
# → "built 6536 jobs, 0 skill-skipped edges, encode 4.2s, snapshot=checkpoints/job_pool"
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

```bash
# fixed CV sample: compare top-K vs the current engine on already-covered jobs.
# Use the test-ranking skill, or a small script that runs match_cv_data for a few
# employees and diffs the top-10 Job ids. Require top-K overlap >= tolerance (SC-004)
# BEFORE enabling the wired morning_refresh step in production.
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
