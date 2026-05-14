# Contract: `extract_job_dates` Management Command

**Location**: `backend/apps/jobs/management/commands/extract_job_dates.py`

---

## Invocation

```bash
python manage.py extract_job_dates [--platform NAME] [--batch N] [--dry-run] [--json-report]
```

### Arguments

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--platform` | str | `linkedin` | Platform name; v1 only `linkedin`. |
| `--batch` | int | `100` | Max jobs to process per run (≥1, ≤1000). |
| `--dry-run` | flag | off | Run extractor, print report, no DB writes. |
| `--json-report` | flag | off | Emit single-line JSON report on stdout. |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Completed successfully (regardless of per-job outcome). |
| `1` | Configuration error (unknown platform, batch out of range). |
| `2` | Auth-state check failed at start (no `li_at`); operator must re-run `linkedin_auth.py`. |
| `3` | Unexpected exception escaped the orchestrator. |

---

## Behaviour

1. Validate arguments. On invalid input, exit `1` without DB access.
2. Verify auth state: `load_state_path()` returns None or state lacks `li_at` → print one-liner instruction, exit `2`.
3. Select candidates per the query in `data-model.md`. If empty: print "Nothing to do — all rows populated"; exit `0`.
4. Open one Playwright browser context for the batch via `open_browser_page(state_path)`. The pool's `li_at` guard at write time ensures the saved state is not silently degraded.
5. For each candidate URL:
   - Call `extract_date_posted(page)`.
   - Post-navigation auth check: if cookies no longer contain `li_at`, return `SESSION_EXPIRED` for this URL and break out of the loop.
   - Apply the result via the repository:
     - `populated` (any of the three date sources) → `Job.date_posted = result.date` (no other field touched).
     - `expired-redirect` → repository's verifier-style apply with `JobStatus.EXPIRED`.
     - `none` / `ERROR` → repository's apply with `JobStatus.UNKNOWN` / `JobStatus.ERROR`.
   - Sleep `3 + uniform(0, 1.5)` seconds between URLs to throttle.
6. Build and print the `BackfillReport`. If `--json-report` is set, also print the JSON form.

---

## Stdout report — human-readable

```text
extract_job_dates — linkedin — 2026-05-13 18:32:11 UTC
  platform              : linkedin
  batch requested       : 100
  batch examined        : 97          (3 skipped: unsupported url)
  outcomes              :
                          populated       : 68
                          expired_marked  : 22
                          none            : 5
                          error           : 2
                          session_expired : 0
  wall-clock            : 8m 41s
  dry-run               : no
```

When `session_expired_count > 0`, the ALERT block instructs the operator to re-run `linkedin_auth.py` and notes that the state file was not overwritten.

---

## Stdout report — JSON (when `--json-report`)

```json
{
  "version": "1",
  "command": "extract_job_dates",
  "platform": "linkedin",
  "started_at": "2026-05-13T18:32:11+00:00",
  "finished_at": "2026-05-13T18:40:52+00:00",
  "wall_clock_s": 521.0,
  "batch_size_requested": 100,
  "total_examined": 97,
  "skipped_unsupported_url": 3,
  "populated_count": 68,
  "expired_marked_count": 22,
  "none_count": 5,
  "error_count": 2,
  "session_expired_count": 0,
  "dry_run": false
}
```

---

## Cron (documented, not auto-installed)

The backfill is a one-shot until catalog coverage is satisfied. Until then:

```cron
0 3 * * * cd /srv/jobflow/backend && .venv/bin/python manage.py extract_job_dates --platform linkedin --batch 200 --json-report >> /var/log/jobflow/extract.log 2>&1
```

One run/day at 03:00 fills ~200 rows. With ~7,000 rows to backfill, full coverage is reached in ~5 weeks. Operator may also run on demand at higher batch sizes to drain faster.

After 100% coverage, the command is idempotent: it picks zero candidates and exits `0`.
