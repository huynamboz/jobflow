# Operator Commands — Quick Reference

Các lệnh hay dùng cho operator. Tất cả chạy từ `backend/` (sau khi `source .venv/bin/activate`).

---

## 1. Setup (one-time)

```bash
# Install Python deps
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Patchright's Chromium (one-time, ~92 MB)
patchright install chromium

# Apply DB migrations
python manage.py migrate
```

---

## 2. LinkedIn auth (manual login)

Chạy **lần đầu** hoặc khi session bị flag (verifier/extractor báo nhiều `SESSION_EXPIRED` / `UNKNOWN`):

```bash
.venv/bin/python -m ml_service.crawler.providers.linkedin_auth
```

Browser sẽ mở visible → login bằng email/password hoặc Google OAuth → nhấn Enter ở terminal → state save vào `backend/auth/linkedin_state.json`.

**Verify auth state vừa save:**

```bash
.venv/bin/python -c '
import json
s = json.load(open("auth/linkedin_state.json"))
print("li_at present:", any(c["name"]=="li_at" for c in s["cookies"]))
print("total cookies:", len(s["cookies"]))
'
```

Output mong đợi: `li_at present: True`.

---

## 3. Verify job status (lifecycle check)

Kiểm tra job còn nhận application hay đã expired. Update `Job.lifecycle`. Matching API tự động lọc `expired` ra khỏi recommendations.

### Dry-run trước (no DB writes)

```bash
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 5 --dry-run
```

### Real run

```bash
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 100
```

### Real run + log file

```bash
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 200 \
    --json-report 2>&1 | tee /tmp/verify_$(date +%Y%m%d_%H%M%S).log
```

### Output (per-URL real-time)

```
[  1/200] job=11510   ACTIVE                                          url=https://...
[  2/200] job=11512   EXPIRED  reason=matched expired marker: text=N  url=https://...
[  3/200] job=11513   UNKNOWN                                         url=https://...
...
verify_job_status — linkedin — ... ← summary
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | OK (kể cả nếu có EXPIRED/UNKNOWN) |
| 1 | Config error (unknown platform, batch out of range) |
| 2 | Auth state thiếu `li_at` — re-run linkedin_auth |
| 3 | Unexpected exception |

---

## 4. Extract job dates (backfill)

Lấy `Job.date_posted` từ LinkedIn (`<time datetime>`, JSON-LD, hoặc relative-text TreeWalker).

### Commands

```bash
# Dry-run
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 5 --dry-run

# Real
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 200

# Real + log file
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 200 \
    --json-report 2>&1 | tee /tmp/extract_$(date +%Y%m%d_%H%M%S).log
```

### Output (per-URL real-time)

```
[  1/200] job=11510   OK     date=2026-04-13 source=relative-text     url=https://...
[  2/200] job=11507   NONE   source=none                              url=https://...
[  3/200] job=11200   EXPIRED                                         url=https://...
[  4/200] job=10800   ERR    TimeoutError                             url=https://...
```

### Idempotent — chạy đi chạy lại được

Mỗi run pick disjoint set (filter `date_posted IS NULL`). Không cần `--resume` flag.

### Cron 2x/day (production)

```cron
# /etc/cron.d/jobflow-jobs
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
JOBFLOW=/srv/jobflow/backend

# Verifier — daily at 02:00 + 14:00 UTC
0 2  * * * cd $JOBFLOW && .venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verify.log 2>&1
0 14 * * * cd $JOBFLOW && .venv/bin/python manage.py verify_job_status --platform linkedin --batch 100 --json-report >> /var/log/jobflow/verify.log 2>&1

# Date backfill — daily at 03:00 UTC (lệch verifier 1h)
0 3 * * * cd $JOBFLOW && .venv/bin/python manage.py extract_job_dates  --platform linkedin --batch 200 --json-report >> /var/log/jobflow/extract.log 2>&1
```

---

## 5. DB inspection helpers

### Đếm jobs theo lifecycle

```bash
.venv/bin/python -c '
import django, os; os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings"); django.setup()
from apps.jobs.models import Job
qs = Job.objects.filter(platform__name__iexact="linkedin")
print(f"total : {qs.count()}")
for lf in ["active","stale","expired","unverified"]:
    print(f"  {lf:11s}: {qs.filter(lifecycle=lf).count()}")
print(f"  date_posted set : {qs.exclude(date_posted__isnull=True).count()}")
print(f"  in backoff      : {qs.exclude(verification_backoff_until__isnull=True).count()}")
'
```

### Xem N jobs vừa được verified mới nhất

```bash
.venv/bin/python manage.py shell -c '
from apps.jobs.models import Job
for j in Job.objects.filter(last_verified_at__isnull=False).order_by("-last_verified_at").values("id","lifecycle","last_verified_at","source_url")[:10]:
    print(f"{j[\"id\"]:6d}  {j[\"lifecycle\"]:9s}  {j[\"last_verified_at\"]}  {j[\"source_url\"][:60]}")
'
```

### Reset backoff trên rows bị block

```bash
.venv/bin/python -c '
import django, os; os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings"); django.setup()
from apps.jobs.models import Job
n = Job.objects.filter(platform__name__iexact="linkedin", verification_backoff_until__isnull=False).update(verification_backoff_until=None, verification_attempts=0)
print(f"Reset backoff on {n} rows")
'
```

---

## 6. Crawl new jobs (multi-source)

### LinkedIn (authenticated)

```bash
.venv/bin/python run_crawl.py --provider linkedin --queries "backend engineer,python developer" --results 50
```

### JobSpy (Indeed/Glassdoor — no auth needed)

```bash
# Programmatic — see /tmp/full_crawl.py for full example
.venv/bin/python -c '
import sys; sys.path.insert(0, ".")
from ml_service.crawler import get_provider
provider = get_provider("jobspy", sites=["indeed"])
jobs = provider.fetch(search_term="data engineer", results_wanted=20, country_indeed="USA")
print(f"got {len(jobs)} jobs")
'
```

### RemoteOK (JSON API)

```bash
.venv/bin/python -c '
from ml_service.crawler import get_provider
provider = get_provider("remoteok")
jobs = provider.fetch(search_term="backend engineer", results_wanted=20)
print(f"got {len(jobs)} jobs")
'
```

---

## 7. Tests

### Run all verifier/extractor tests

```bash
.venv/bin/python -m pytest tests_ml/test_verifier.py tests_ml/test_date_extractor.py tests_ml/test_auth_guard.py -v
```

### Run a single test file with coverage

```bash
.venv/bin/python -m pytest tests_ml/test_date_extractor.py \
    --cov=ml_service.verifier --cov-report=term-missing
```

### Run a specific test

```bash
.venv/bin/python -m pytest tests_ml/test_verifier.py::test_di_proof_service_works_with_two_providers -v
```

---

## 8. Log filtering

### Đếm outcome trong 1 batch

```bash
LOG=/tmp/extract_20260513_091627.log

grep "OK"      $LOG | wc -l   # populated
grep "NONE"    $LOG | wc -l   # no date found
grep "EXPIRED" $LOG | wc -l   # expired redirect
grep "ERR"     $LOG | wc -l   # errors
```

### Xem live progress của batch đang chạy

```bash
tail -f /tmp/extract_*.log
```

### Extract chỉ JSON report cuối file

```bash
tail -1 /tmp/extract_*.log | jq .
```

---

## 9. Git workflow trên branch feature

```bash
# Sync code
git fetch origin
git log --oneline -10

# Trên branch 002-job-date-posted-extraction
git status
git diff
git add <files>
git commit -m "..."

# Quay về main khi xong
git checkout main
git merge 002-job-date-posted-extraction
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Exit code 2 | `li_at` missing | Re-run `linkedin_auth` |
| Tất cả URLs → `SESSION_EXPIRED` | Auth state corrupted hoặc IP-banned | Re-run `linkedin_auth` headed mode |
| Tất cả URLs → `NONE`/`UNKNOWN` | LinkedIn DOM changed | Inspect `selectors/linkedin.json`; update markers |
| Batch quá chậm (>15min/100 URLs) | Browser launch per-URL | Confirm `verify_batch` đang được gọi, không phải fallback loop |
| `SynchronousOnlyOperation` | Django ORM call inside Playwright async ctx | Collect results trước, apply DB writes sau khi exit browser |
| 100% `expired_marked` mới crawl | LinkedIn flag IP/session — serving redirect to all | Đợi 30-60min, hoặc re-login từ IP khác |
| `ALERT: N session_expired` cuối log | Mid-batch li_at loss | Đã preserve auth file. Không cần làm gì nếu N < 50% batch |

---

## 11. Speckit (lập plan cho feature mới)

```bash
# Tạo feature mới
specify init --here --integration claude  # đã chạy 1 lần
.specify/scripts/bash/create-new-feature.sh --json --short-name <name> "feature description"

# Sau khi spec/plan/tasks viết xong:
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Order: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`.

---

## 12. Admin dashboard endpoints (spec 003)

The admin app's Dashboard page reads from these JSON endpoints. Useful
for manual inspection or scripting.

```bash
# KPI strip — job lifecycle counts, CV counts, last run timestamps, auth state, model meta
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/dashboard/kpi/ | jq

# Catalog composition — by platform, lifecycle, role_category, seniority
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/dashboard/catalog/ | jq

# Freshness + verifier outcomes per day
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/admin/dashboard/freshness/?days_added=30&days_outcomes=14" | jq

# Ops health — coverage % + recent runs
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/admin/dashboard/ops/?recent_runs_limit=20" | jq

# Labeling stats (mirror of /api/labeling/stats/)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/dashboard/labeling/ | jq

# Active GNN checkpoint metadata
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/dashboard/model/ | jq
```

### Inspect VerifierRunLog (spec 003 data source)

Each `verify_job_status` / `extract_job_dates` run inserts one row.
Powers the "recent runs" table and outcomes-per-day chart.

```bash
.venv/bin/python -c '
import django, os; os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings"); django.setup()
from apps.jobs.models import VerifierRunLog
print(f"Total run logs: {VerifierRunLog.objects.count()}")
for r in VerifierRunLog.objects.order_by("-started_at")[:10]:
    print(f"  {r.started_at:%Y-%m-%d %H:%M} {r.command:18s} n={r.total_examined:3d} dry={r.dry_run}")
    print(f"    {r.counts_by_outcome}")
'
```

---

## 13. Admin design tokens (NODE — spec 004)

The admin app's visual identity ports the **NODE · Economy V1** design
system. Tokens are loaded from
[`admin/src/styles/node-tokens.css`](../admin/src/styles/node-tokens.css)
(copied verbatim from upstream) and exposed via the `@theme` block in
[`admin/src/styles/globals.css`](../admin/src/styles/globals.css).

Available Tailwind utilities (light mode only):

```html
<!-- Colors -->
<div class="bg-node-surface text-node-ink">…</div>
<div class="bg-node-raised border border-node-line">…</div>
<span class="text-node-muted">subdued copy</span>
<span class="text-node-blue">primary accent</span>

<!-- Radii (NODE Figma scale) -->
<div class="rounded-node-12">default card</div>
<div class="rounded-node-20">card outer / modal</div>
<button class="rounded-node-10">small button</button>

<!-- Shadows -->
<div class="shadow-node-card">card surface</div>
<div class="shadow-node-pop">popover</div>
<div class="shadow-node-modal">modal</div>

<!-- Fonts -->
<p class="font-node-sans">Inter body text</p>
<p class="font-node-mono">123,456 sats</p>
```

HeroUI semantic colors are also overridden to NODE values, so existing
`<Button color="primary">` etc. pick up NODE blue automatically — no
component change needed.

To re-sync tokens from upstream, replace `node-tokens.css` with the
latest version of the source file and re-add the copy-attribution header.

---

## Quick links

- Spec 001 (verifier): [specs/001-linkedin-job-verifier/](../specs/001-linkedin-job-verifier/)
- Spec 002 (date extraction): [specs/002-job-date-posted-extraction/](../specs/002-job-date-posted-extraction/)
- Spec 003 (dashboard v2): [specs/003-admin-dashboard-v2/](../specs/003-admin-dashboard-v2/)
- Verifier source: [backend/ml_service/verifier/](../backend/ml_service/verifier/)
- Crawler source: [backend/ml_service/crawler/](../backend/ml_service/crawler/)
- Dashboard backend: [backend/apps/admin_dashboard/](../backend/apps/admin_dashboard/)
- Dashboard frontend: [admin/src/components/dashboard/](../admin/src/components/dashboard/)
