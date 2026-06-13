# Crawler Module

Multi-provider job crawling với DI pattern. Thêm provider mới = 1 file trong `providers/`, auto-discovered (factory quét `providers/` tìm subclass của `CrawlProvider`).

## Providers

| Provider | Source | Auth | Ghi chú |
|----------|--------|------|---------|
| `jobspy` | **Indeed** (mặc định) | Không cần | Ổn định nhất. Lib hỗ trợ 4 site (indeed/linkedin/glassdoor/zip_recruiter) nhưng provider mặc định chỉ `indeed` — đổi bằng kwarg `sites=[...]`. |
| `linkedin` | LinkedIn | Cần login 1 lần | Rất tốt (+ logo, company URL, job type, applicants). Playwright. |
| `adzuna` | Adzuna API | Cần API key | Structured, có salary. |
| `remotive` | Remotive API | Không cần | Remote tech jobs. |
| `remoteok` | RemoteOK API | Không cần | Remote jobs. |

## Crawl — lệnh chính `crawl_jobs`

Crawl **đa luồng theo provider** (mỗi provider 1 thread, chạy song song) và **dump ra file JSON per-provider theo ngày**. **Không ghi DB** — lệnh này chỉ tạo file crawl thô.

```bash
cd backend

# 1 provider
.venv/bin/python manage.py crawl_jobs --provider jobspy --query "react developer" --results 50

# tất cả providers song song (8 query mặc định nếu không truyền --query)
.venv/bin/python manage.py crawl_jobs --all --results 50

# tuỳ chọn
.venv/bin/python manage.py crawl_jobs --all --out-dir data/crawl --workers 4 --location "Vietnam"
```

**Output** — mỗi provider 1 folder riêng, file đặt tên theo ngày crawl:

```
<out-dir>/<provider>/<YYYY-MM-DD>.json     # mảng JSON các RawJob
data/crawl/jobspy/2026-06-12.json
data/crawl/adzuna/2026-06-12.json
```

- Out-dir mặc định: `<BASE_DIR>/data/crawl`.
- Chạy lại **cùng ngày** → **merge** vào đúng file ngày đó, dedup theo `source_url` (không ghi đè, không nhân đôi).
- `--workers` mặc định = số provider. Lỗi 1 query không giết provider; lỗi 1 provider không giết các provider khác.

| Flag | Ý nghĩa |
|------|---------|
| `--provider` | 1 provider (mặc định `jobspy`) |
| `--all` | dùng tất cả provider auto-discovered |
| `--query` | 1 query; bỏ trống → 8 query IT mặc định |
| `--location` | lọc địa điểm |
| `--results` | số kết quả / query (mặc định 50) |
| `--out-dir` | thư mục gốc output |
| `--workers` | số provider chạy song song |

> Nạp các file crawl vào DB là **bước riêng** (chưa wire trong lệnh này). Khi cần ingest: đọc `data/crawl/**/*.json` → `JobService.save_raw_jobs_batch` (extract skill rule-based + tạo `Job`/`JobSkill`).

## Output format (RawJob)

Mỗi job là 1 object trong mảng JSON. Với **jobspy/Indeed** hiện đã map đầy đủ các trường (trước đây nhiều trường rỗng):

```json
{
  "source": "indeed",
  "source_url": "https://www.indeed.com/viewjob?jk=...",
  "title": "Frontend Developer (React)",
  "company": "CareerSwift",
  "location": "San Francisco, CA, US",
  "description": "Full job description text…",
  "salary_min": null,
  "salary_max": null,
  "salary_currency": "USD",
  "date_posted": "2026-06-12",
  "seniority_hint": null,
  "raw_skills": [],
  "company_logo_url": "https://…",
  "company_url": "https://www.indeed.com/cmp/Careerswift",
  "job_type": "fulltime",
  "applicant_count": "",
  "extra": { "is_remote": true, "company_industry": "…", "company_size": "11 to 50", "apply_url": "https://…" },
  "fingerprint": "099b114f91b2aeb6…"
}
```

- `fingerprint` do `storage.py` tự tính (không phải từ API).
- jobspy map: `site→source, job_url→source_url, title, company, location, description, min/max_amount→salary, currency, date_posted, job_type, logo_photo_url→company_logo_url, company_url`; và vào `extra{}`: `is_remote, company_industry, company_size (company_num_employees), apply_url (job_url_direct)`.

## Setup (provider cần auth)

```bash
cd backend

# LinkedIn — login 1 lần, save session
.venv/bin/python -m ml_service.crawler.providers.linkedin_auth
# → Browser mở → login → quay lại terminal nhấn Enter → auth/linkedin_state.json saved

# Adzuna — set API key (đăng ký tại https://developer.adzuna.com/)
export ADZUNA_APP_ID=your_id
export ADZUNA_APP_KEY=your_key
```

Check auth LinkedIn còn valid:

```bash
.venv/bin/python -c "
from ml_service.crawler.providers.linkedin_auth import load_state_path
import json
path = load_state_path()
if not path: print('❌ Chưa login')
else:
    state = json.load(open(path))
    session = next((c for c in state['cookies'] if c['name']=='li_at'), None)
    print('✅ Logged in' if session else '❌ Session expired')
"
```

## Dùng provider trực tiếp (programmatic)

Khi cần điều khiển tay (vd LinkedIn với `save_path`, hoặc lưu JSONL qua `storage.save_raw_jobs`):

```bash
# LinkedIn (cần đã login) — Playwright, lưu dần ra JSONL
.venv/bin/python -c "
from ml_service.crawler import get_provider
p = get_provider('linkedin', headless=True, save_path='data/raw_jobs.jsonl')
jobs = p.fetch('react developer', location='Vietnam', results_wanted=250)
print(f'{len(jobs)} jobs')
"

# Adzuna (cần API key)
.venv/bin/python -c "
from ml_service.crawler import get_provider
from ml_service.crawler.storage import save_raw_jobs, deduplicate
p = get_provider('adzuna', app_id='xxx', app_key='yyy')
jobs = deduplicate(p.fetch('data engineer', location='london', results_wanted=50))
save_raw_jobs(jobs, 'data/raw_jobs.jsonl')
print(f'{len(jobs)} jobs')
"

# Liệt kê providers
.venv/bin/python -c "from ml_service.crawler import list_providers; print(list_providers())"
# → ['adzuna', 'jobspy', 'linkedin', 'remoteok', 'remotive']
```

## Dedup (`storage.py`)

2 lớp:
1. **URL** — cùng `source_url` → skip.
2. **Fingerprint** — `MD5(normalize(title) + normalize(company) + city)`.
   - "Senior Python Developer @ Google Inc." ≈ "Sr. Python Dev @ Google" → cùng fingerprint (chuẩn hoá seniority/suffix/abbrev).

`deduplicate(jobs)` áp cả 2 lớp. Lệnh `crawl_jobs` dedup theo URL trong từng file ngày; khi ingest DB, `save_raw_job` còn dedup theo fingerprint per platform.

## Thêm provider mới

Tạo `providers/my_provider.py`:

```python
from ml_service.crawler.base import CrawlProvider, RawJob

class MyProvider(CrawlProvider):
    @property
    def name(self) -> str:
        return "my_source"

    def fetch(self, search_term, location="", results_wanted=100, **kwargs) -> list[RawJob]:
        return [RawJob(source="my_source", source_url=..., title=..., company=..., location=..., description=...)]
```

Auto-discovered — không cần sửa factory hay file nào khác.

## Cấu trúc

```
ml_service/crawler/
├── base.py            CrawlProvider ABC + RawJob (dataclass)
├── factory.py         Auto-discover providers (get_provider / list_providers)
├── storage.py         JSONL save/load + fingerprint dedup + _raw_job_to_dict
├── README.md
└── providers/
    ├── jobspy_provider.py       Indeed (python-jobspy)
    ├── linkedin_provider.py     LinkedIn (Playwright)
    ├── linkedin_auth.py         LinkedIn login + save state
    ├── linkedin_selectors.json  CSS selectors
    ├── adzuna_provider.py       Adzuna REST API
    ├── remotive_provider.py     Remotive API
    └── remoteok_provider.py     RemoteOK API
```

## Runbook — crawl nhiều IT jobs từ LinkedIn (Playwright)

LinkedIn rate-limit gắt nên dùng provider riêng (không qua jobspy). Crawl trực tiếp + lưu dần ra JSONL:

```bash
cd backend
> data/raw_jobs.jsonl                      # clear file (nếu muốn crawl mới)
# check / re-login nếu cần:
.venv/bin/python -m ml_service.crawler.providers.linkedin_auth

.venv/bin/python -c "
from ml_service.crawler import get_provider
roles = ['frontend','backend','fullstack','react','python','java','nodejs','devops','data','software','mobile','cloud','AI','QA','machine learning']
locations = ['United States','Canada','Finland','Australia','Singapore']
queries = [(r, l) for l in locations for r in roles]
p = get_provider('linkedin', headless=True, save_path='data/raw_jobs.jsonl')
total = 0
for role, loc in queries:
    try:
        jobs = p.fetch(role, location=loc, results_wanted=100); total += len(jobs)
        print(f'  {role:18s} ({loc:14s}) -> {len(jobs)}, total={total}')
    except Exception as e:
        print(f'  {role:18s} ({loc:14s}) -> FAILED: {e}')
print(f'Done: {total} crawled')
"
```

15 roles × 5 locations × 100 → mục tiêu ~7.500, sau dedup còn ~3.000–4.000 unique. Thời gian ~60–90 phút.

Clean dedup file JSONL:

```bash
.venv/bin/python -c "
from ml_service.crawler.storage import load_raw_jobs, deduplicate, save_raw_jobs
from pathlib import Path
path = Path('data/raw_jobs.jsonl')
jobs = load_raw_jobs(path); unique = deduplicate(jobs)
path.unlink(); save_raw_jobs(unique, path)
print(f'{len(jobs)} -> {len(unique)} unique')
"
```

> **Nạp DB + train**: file crawl mới (`data/crawl/<provider>/*.json`) vào DB qua `manage.py extract_jobs` → `import_extracted` (xem `apps/jobs/management/commands/README.md`). Việc **train model là offline** (script `run_train_save.py` trên LLM labels, chạy GPU Neptune — xem `docs/codebase-knowledge/05-training-pipeline.md`); đường retrain in-app (`retrain_model`/`TrainService`) **đã bị gỡ**.
