# Quickstart — date_posted backfill

Operator-facing runbook for the date-extraction feature.

---

## Step 0 — Re-login to LinkedIn (required once)

The verifier feature shipped a bug that silently degraded the saved auth state. If you've run the verifier before, your auth file likely no longer contains the `li_at` cookie. Re-login:

```bash
cd backend
.venv/bin/python -m ml_service.crawler.providers.linkedin_auth
```

Browser opens → log in manually → close. The state file at `backend/auth/linkedin_state.json` is rewritten with a valid `li_at`.

You can confirm:

```bash
.venv/bin/python -c 'import json; s=json.load(open("auth/linkedin_state.json")); print("li_at present:", any(c["name"]=="li_at" for c in s["cookies"]))'
```

Expect: `li_at present: True`.

---

## Step 1 — Dry-run the backfill on a small batch

```bash
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 5 --dry-run
```

Expected: 5 jobs visited; outcomes printed; no DB rows changed. You can confirm:

```bash
.venv/bin/python -c '
import django, os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
from apps.jobs.models import Job
print("LinkedIn jobs with date_posted:", Job.objects.filter(platform__name__iexact="linkedin").exclude(date_posted__isnull=True).count())
'
```

Should be unchanged (0 at the start, still 0 after dry-run).

---

## Step 2 — Real backfill (resumable)

```bash
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 200 --json-report
```

Wall-clock ~15-20 minutes for 200 URLs. Confirm afterwards:

```bash
.venv/bin/python -c '
import django, os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
from apps.jobs.models import Job
qs = Job.objects.filter(platform__name__iexact="linkedin")
print(f"total       : {qs.count()}")
print(f"date_posted : {qs.exclude(date_posted__isnull=True).count()}")
print(f"expired     : {qs.filter(lifecycle=\"expired\").count()}")
'
```

Re-run the same command — it picks up where the previous run stopped (no special flag needed).

---

## Step 3 — Schedule daily (optional)

```cron
0 3 * * * cd /srv/jobflow/backend && .venv/bin/python manage.py extract_job_dates --platform linkedin --batch 200 --json-report >> /var/log/jobflow/extract.log 2>&1
```

At 200/day, full catalog coverage in ~5 weeks. After all rows are populated, the command becomes a no-op (zero candidates).

---

## Troubleshooting

| Symptom | Cause | Action |
|---------|-------|--------|
| Command exits with code 2 | `li_at` missing from auth state | Re-run `linkedin_auth.py` |
| 100% session_expired in report | Session invalidated mid-batch | Re-run `linkedin_auth.py`; state file was preserved by the guard |
| 100% none in report | LinkedIn DOM changed; extractor selectors stale | Check the most recent commit to `ml_service/verifier/date_extractor.py` and `selectors/linkedin.json`; probe one URL manually via debug script |
| populated_count much lower than expected | Likely many guest-layout pages without JSON-LD; relative-text fallback should still produce dates. Inspect the report — if `none_count` is high, the relative parser may not be matching the live text format. |
| `date_posted` written but value looks wrong (e.g. 2010) | Guardrail should have rejected; if it didn't, file a bug — extractor returned an out-of-range value not caught. |
| Backfill is slow | Expected wall-clock is ~5s/URL. Check whether `verify_job_status` is running concurrently — both compete for the auth file (read-only competition is OK, but writes are serialized). |
