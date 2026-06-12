# Job management commands

Các lệnh `manage.py` của app `jobs`. Chạy từ `backend/`:

```bash
cd backend && .venv/bin/python manage.py <command> [options]
```

---

## 🕷️ Crawl (lấy job → file JSON, KHÔNG ghi DB)

Crawl ghi ra file thô per-provider theo ngày: `data/crawl/<provider>/<YYYY-MM-DD>.json`
(mảng JSON, merge-dedup theo `source_url`). Chi tiết provider: [ml_service/crawler/README.md](../../../ml_service/crawler/README.md).

### `crawl_daily` — master sweep IT/Software/AI ⭐

1 lệnh = crawl **tất cả provider API mặc định** (jobspy, freelancer, remotive, remoteok) song song × **~58 keyword IT/AI** vào file hôm nay, có dashboard live. **Loại mặc định**: `linkedin` (chạy `crawl_linkedin`) và `adzuna` (cần API key — gọi rõ `--providers adzuna` nếu đã set `ADZUNA_APP_ID/KEY`).

```bash
.venv/bin/python manage.py crawl_daily                          # mặc định
.venv/bin/python manage.py crawl_daily --results 80             # nhiều job/keyword hơn
.venv/bin/python manage.py crawl_daily --providers freelancer,remotive   # subset
.venv/bin/python manage.py crawl_daily --delay 1 --workers 1    # global ~1 req/s (tuần tự)
.venv/bin/python manage.py crawl_daily --limit 5 --results 5    # test nhanh 5 keyword
```
Flags: `--results` (40), `--providers`, `--location`, `--workers`, `--delay` (1.0s/req per provider), `--limit`, `--out-dir`.

### `crawl_linkedin` — master LinkedIn 🔗

Crawl **16 role IT curated** từ LinkedIn, **tuần tự (serial main-thread)**, 1 browser/role. **Cần login.**

```bash
# login 1 lần (nếu chưa / session hết hạn)
.venv/bin/python -m ml_service.crawler.providers.linkedin_auth

.venv/bin/python manage.py crawl_linkedin                       # mặc định
.venv/bin/python manage.py crawl_linkedin --location "Vietnam" --results 80
.venv/bin/python manage.py crawl_linkedin --no-headless --limit 1   # xem browser (debug)
.venv/bin/python manage.py crawl_linkedin --roles "react developer,devops engineer"
```
Flags: `--results` (50), `--location`, `--delay` (2.0s), `--roles`, `--limit`, `--headless/--no-headless`, `--out-dir`.

### `crawl_jobs` — ad-hoc (1 provider hoặc 1 query)

```bash
.venv/bin/python manage.py crawl_jobs --provider jobspy --query "react developer" --results 50
.venv/bin/python manage.py crawl_jobs --all --results 50        # provider mặc định (loại linkedin + adzuna)
.venv/bin/python manage.py crawl_jobs --provider linkedin --query "python developer"   # linkedin 1 query
```
Flags: `--provider` (jobspy), `--query` (bỏ trống → 8 query mặc định), `--all`, `--location`, `--results` (50), `--workers`, `--delay`, `--out-dir`.

---

## 📥 Nạp vào DB

### `import_jobs` — JSONL → DB

```bash
.venv/bin/python manage.py import_jobs --file data/raw_jobs.jsonl
```
> ⚠️ Đọc **JSONL** (`save_raw_jobs`), KHÔNG phải file `data/crawl/<provider>/*.json` mới (mảng JSON). Đường ingest từ file crawl mới vào DB chưa được wire — cần lệnh riêng nếu muốn.

### `sync_extracted` — đẩy kết quả LLM-extract vào Job/CV

```bash
.venv/bin/python manage.py sync_extracted              # cả jobs + cvs
.venv/bin/python manage.py sync_extracted --jobs-only --dry-run
```
Sync `JDExtractionRecord` / `CVExtractionRecord` → `Job` / `CV`. Flags: `--jobs-only`, `--cvs-only`, `--dry-run`.

### `rebuild_jobs` — dedup + apply extraction + import

```bash
.venv/bin/python manage.py rebuild_jobs --dry-run
```
Dedup jobs → apply LLM extractions → import unmatched extraction records. Flags: `--dry-run`, `--skip-dedup`, `--skip-apply`, `--skip-import`.

---

## 🧹 Bảo trì catalog

### `dedup_jobs` — gỡ job trùng

```bash
.venv/bin/python manage.py dedup_jobs --dry-run
```
Deactivate job trùng (cùng title+company), giữ bản đã engage / mới nhất.

### `verify_job_status` — kiểm job còn sống

```bash
.venv/bin/python manage.py verify_job_status --platform linkedin --batch 50 --dry-run
```
Verify listing với platform nguồn (Playwright) → cập nhật lifecycle. Flags: `--platform`, `--batch`, `--dry-run`, `--json-report`, `--no-auth-check`, `--headed`.

### `extract_job_dates` — backfill ngày đăng

```bash
.venv/bin/python manage.py extract_job_dates --platform linkedin --batch 100 --dry-run
```
Backfill `Job.date_posted` cho row NULL. Flags: `--platform`, `--batch`, `--dry-run`, `--json-report`, `--no-auth-check`, `--no-verify`, `--headed`.

### `backfill_job_roles` — phân loại role

```bash
.venv/bin/python manage.py backfill_job_roles --export --out roles_export.jsonl
.venv/bin/python manage.py backfill_job_roles --import-dir results/
```
Export job chưa có role → (phân loại ngoài) → import lại. Flags: `--export`, `--out`, `--chunk-size`, `--import-dir`, `--dry-run`.

---

## Pipeline điển hình

```bash
# 1. crawl hôm nay
.venv/bin/python manage.py crawl_daily
.venv/bin/python manage.py crawl_linkedin          # (tuỳ chọn, cần login)

# 2. nạp DB  (hiện qua JSONL — xem ghi chú import_jobs)
# 3. bảo trì
.venv/bin/python manage.py dedup_jobs
.venv/bin/python manage.py rebuild_job_pool        # (app khác) → để GNN rank job mới
```

> **Train model là offline** (`run_train_save.py`, LLM labels, GPU Neptune) — xem `docs/codebase-knowledge/05-training-pipeline.md`. Không có lệnh retrain in-app.
