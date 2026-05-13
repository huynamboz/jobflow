# Contract: `verify_job_status` Management Command

**Scope**: The single operator entry point for the verifier feature.

**Location**: `backend/apps/jobs/management/commands/verify_job_status.py`

---

## Invocation

```bash
python manage.py verify_job_status [--platform NAME] [--batch N] [--dry-run] [--json-report]
```

### Arguments

| Flag | Type | Default | Required | Description |
|------|------|---------|----------|-------------|
| `--platform` | str | `linkedin` | no | Name of the verifier (matches `JobStatusVerifier.name`). Special value `all` (v2) dispatches per URL. |
| `--batch` | int | `100` | no | Maximum number of jobs to verify in this run (≥1, ≤1000). |
| `--dry-run` | flag | off | no | Run verifier but skip ALL database writes. Report is still produced. |
| `--json-report` | flag | off | no | Print the run report as a single-line JSON object on stdout (in addition to the human-readable lines). |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Run completed; report produced. (Outcome counts may include `ERROR` or `EXPIRED` — those are not command failures.) |
| `1` | Configuration error: unknown `--platform`, `--batch` out of range, etc. No work attempted. |
| `2` | Session expired across the entire batch (operator action required). Treated as a runtime alert, not a per-job failure. |
| `3` | Unexpected exception escaped `StatusCheckService`. Report partial outcomes if possible. |

---

## Behaviour

On invocation:

1. **Parse and validate arguments**. On invalid input, print an error and exit `1` without touching the DB.
2. **Resolve verifier**: call `verifier_factory.get_verifier(platform)`; on `KeyError`, exit `1`.
3. **Apply aging rule** (unless `--dry-run`): bulk `UPDATE jobs SET lifecycle='stale' WHERE lifecycle='active' AND date_posted < NOW() - INTERVAL '14 days'`.
4. **Build candidate set**: at most `--batch` job rows from the candidate selection query (see `data-model.md`).
5. **Group by domain → dispatch via `supports(url)`**. Any URL no registered verifier supports is counted under `skipped_unsupported_url` and not retried.
6. **Call `verify_batch(urls)`** on the selected verifier.
7. **Apply results to the repository** (skipped on `--dry-run`).
8. **Print the human-readable report** (always). Print JSON report when `--json-report` set.
9. **Determine exit code** per the table above.

The command MUST NOT exit between steps 6 and 7 even on a Python exception; partial results from `verify_batch` are still applied (each `VerifyResult` is independent). An exception escaping `verify_batch` itself triggers exit `3`.

---

## Stdout report — human-readable form

```text
verify_job_status — LinkedIn — 2026-05-13 02:00:12 UTC
  platform              : linkedin
  batch requested       : 100
  batch examined        : 98          (2 skipped: unsupported url)
  outcomes              :
                          active           : 71
                          expired          : 12
                          unknown          : 9
                          error            : 4
                          session_expired  : 2
  wall-clock            : 7m 42s
  dry-run               : no

ALERT: 2 jobs returned session_expired.
  → Re-run `python manage.py linkedin_auth` and retry.
```

When `session_expired_count > 0`, the ALERT block is printed below the report. When `session_expired_count == batch_examined > 0`, the command exits `2` after the report.

---

## Stdout report — JSON form (when `--json-report` set)

```json
{
  "version": "1",
  "command": "verify_job_status",
  "platform": "linkedin",
  "started_at": "2026-05-13T02:00:12Z",
  "finished_at": "2026-05-13T02:07:54Z",
  "wall_clock_s": 462,
  "batch_size_requested": 100,
  "total_examined": 98,
  "skipped_unsupported_url": 2,
  "counts_by_outcome": {
    "active": 71,
    "expired": 12,
    "unknown": 9,
    "error": 4,
    "session_expired": 2
  },
  "session_expired_count": 2,
  "dry_run": false
}
```

Reserved for log shippers (Loki/Promtail, etc.).

---

## Wiring (construction of the service inside the command)

```python
def handle(self, *args, **opts):
    verifier = get_verifier(opts["platform"])
    repository = DjangoJobLifecycleRepository()
    service = StatusCheckService(
        verifier_registry={verifier.name: verifier},
        repository=repository,
        clock=lambda: datetime.now(timezone.utc),
    )
    report = service.check_batch(
        platform=opts["platform"],
        batch=opts["batch"],
        dry_run=opts["dry_run"],
    )
    self._print_report(report, json_mode=opts["json_report"])
```

The command MUST NOT construct verifiers directly with the `LinkedInVerifier()` class name — it goes through `get_verifier()`. This is the test seam: integration tests stub `get_verifier` to return a `FakeVerifier`.

---

## Cron entry (documented, not auto-installed)

```cron
# /etc/cron.d/jobflow-verifier  (or user crontab)
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

0 2 * * *  cd /srv/jobflow/backend && /srv/jobflow/backend/.venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verifier.log 2>&1
0 14 * * * cd /srv/jobflow/backend && /srv/jobflow/backend/.venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verifier.log 2>&1
```

(Adjust paths to your deployment.)
