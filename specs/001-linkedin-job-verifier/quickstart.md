# Quickstart — LinkedIn Job Verifier

This is the operator-facing how-to for running the verifier once it ships. It also lists the manual smoke-test URLs for v1.

---

## Prerequisites

1. The Django app is set up and migrations are applied (including this feature's migration).
2. LinkedIn cookies have been captured to disk via the existing flow:
   ```bash
   cd backend
   .venv/bin/python -m ml_service.crawler.providers.linkedin_auth
   ```
   This opens a browser, you log in to LinkedIn, and the storage state is saved. Re-run it whenever the verifier reports `session_expired`.

3. At least one `Job` row exists with `platform.name = "linkedin"` and a valid `source_url`.

---

## One-off run

```bash
cd backend
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 50
```

Output ends with a report (counts per outcome + wall-clock). Exit code `0` means the run completed; outcome counts like `expired` or `error` are not failures.

### Useful variants

```bash
# Dry run — no DB writes; safest first run after deployment.
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 10 --dry-run

# Small smoke against known URLs to verify markers still parse correctly.
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 5 --json-report

# Larger nightly batch.
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 200
```

---

## Schedule (cron)

Add to crontab (`crontab -e`) or `/etc/cron.d/jobflow-verifier`:

```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

0 2 * * *  cd /srv/jobflow/backend && .venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verifier.log 2>&1
0 14 * * * cd /srv/jobflow/backend && .venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verifier.log 2>&1
```

Twice-a-day at 02:00 and 14:00 UTC gives ~200 jobs/day of coverage; tune by changing `--batch`.

---

## What to do when `session_expired` shows up

If the report contains a non-zero `session_expired` count:

1. Stop the cron (or wait one cycle — the verifier will not corrupt data on session-expired outcomes).
2. Re-run `linkedin_auth` to log in again:
   ```bash
   cd backend
   .venv/bin/python -m ml_service.crawler.providers.linkedin_auth
   ```
3. Manually re-run the verifier once:
   ```bash
   .venv/bin/python manage.py verify_job_status --platform linkedin --batch 50
   ```
4. Confirm zero `session_expired` in the report. Re-enable cron if you stopped it.

---

## Manual smoke test for releases (5-job script)

Before deploying a verifier change to production, run this exact smoke locally and inspect the report by hand.

Required: 5 LinkedIn job URLs that you have manually classified within the last 24 hours:
- 3 jobs that are currently accepting applications (`expected: active`).
- 2 jobs that LinkedIn has marked "No longer accepting applications" (`expected: expired`).

Steps:

1. Insert the 5 jobs into the DB (or pick existing rows) with `platform.name = "linkedin"` and the verified `source_url`. Note the IDs.
2. Force them to `stale` so the candidate selection picks them:
   ```sql
   UPDATE jobs SET lifecycle = 'stale' WHERE id IN (...);
   ```
3. Run:
   ```bash
   .venv/bin/python manage.py verify_job_status --platform linkedin --batch 5 --dry-run --json-report
   ```
4. Confirm the report shows `active: 3, expired: 2, unknown/error/session_expired: 0`.
5. Re-run without `--dry-run` and confirm:
   - The 3 active rows now have `lifecycle='active'`, `last_verified_at` set, `verification_attempts=0`.
   - The 2 expired rows have `lifecycle='expired'`.

If `unknown` or `error` is non-zero, the LinkedIn page structure may have changed — update `linkedin_selectors.json` (`expired_markers` / `active_markers`) and re-run.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Every URL → `session_expired` | Cookies expired or LinkedIn forced re-auth | Re-run `linkedin_auth.py` |
| Every URL → `unknown` | LinkedIn DOM changed; selectors no longer match | Inspect a known-active and a known-expired page; update `linkedin_selectors.json` |
| Every URL → `error` with connection messages | Network down or LinkedIn ratelimiting | Wait 1h; verifier will respect its own backoff |
| Batch takes >15 min for 100 URLs | Likely launching a new browser per URL | Confirm `LinkedInVerifier.verify_batch` is being used (not the default `verify` loop) |
| `verify_job_status` exits `1` | Unknown `--platform` or `--batch` out of range | Check spelling; valid range is 1..1000 |
| Matching API still returns expired jobs | Filter not applied or filter cached | Confirm the matching service code path goes through the new lifecycle filter; restart workers if applicable |
