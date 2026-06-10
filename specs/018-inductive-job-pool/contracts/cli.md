# Contract: `rebuild_job_pool` management command

`python manage.py rebuild_job_pool [--limit N] [--dry-run] [--no-save]`

**Purpose**: Build `JobData` from the live `Job` catalog, inductively encode it into the engine, and persist the job-pool snapshot.

**Behaviour**:
1. `jobs = build_jobdata_from_db()` — all `Job` rows with usable skills (optionally `--limit` for testing).
2. `engine = _get_engine()` → `engine.rebuild_job_pool(jobs)`.
3. Unless `--no-save`: `job_pool_snapshot.save(...)` (atomic) → live servers pick it up via mtime reload.
4. Print a summary: `built N jobs, S skill-skipped edges, encode T s, snapshot=path`.

**Flags**:
- `--dry-run`: build + encode, report counts, **do not** save the snapshot.
- `--no-save`: rebuild the in-process pool only (used when the caller already saved, or for tests).
- `--limit N`: build only the first N jobs (smoke tests).

**Exit**: non-zero on feature-recipe dimension mismatch or empty job set.

## Wiring into `morning_refresh`

`morning_refresh` step order becomes:

```text
[0/3] rebuild_job_pool   → refresh rankable pool from live catalog + save snapshot
[1/3] re-match all employees (no-LLM, against the refreshed pool)
[2/3] send HR digest
```

`--no-digest` unchanged. The rebuild is the new first step; re-match + digest follow as today.

## Sanity-check (manual gate before trusting in prod)

After the first `rebuild_job_pool`, run the ranking sanity-check (the `test-ranking` skill or a small harness) on a fixed CV sample and confirm top-K overlap vs the current engine on already-covered jobs meets tolerance (SC-004) before enabling the wired `morning_refresh` step in production.
