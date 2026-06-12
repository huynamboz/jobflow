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
| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--results` | 40 | Số job / keyword / provider |
| `--providers` | tất cả API | Danh sách provider (phẩy ngăn). linkedin + adzuna bị loại mặc định |
| `--location` | "" | Lọc địa điểm |
| `--workers` | = số provider | Số provider chạy song song |
| `--delay` | 1.0 | Giây giữa các request **mỗi provider** (`--workers 1` → ~1 req/s toàn cục) |
| `--limit` | 0 | Giới hạn số keyword (debug) |
| `--out-dir` | `data/crawl` | Thư mục output gốc |

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
| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--results` | 50 | Số job / role |
| `--location` | "" | Lọc địa điểm (vd "Vietnam") |
| `--delay` | 2.0 | Giây giữa các role (LinkedIn rate-limit gắt) |
| `--roles` | 16 curated | Override danh sách role (phẩy ngăn) |
| `--limit` | 0 | Giới hạn số role (debug) |
| `--headless / --no-headless` | headless | Ẩn / hiện cửa sổ browser |
| `--out-dir` | `data/crawl` | Thư mục output gốc |

### `crawl_jobs` — ad-hoc (1 provider hoặc 1 query)

```bash
.venv/bin/python manage.py crawl_jobs --provider jobspy --query "react developer" --results 50
.venv/bin/python manage.py crawl_jobs --all --results 50        # provider mặc định (loại linkedin + adzuna)
.venv/bin/python manage.py crawl_jobs --provider linkedin --query "python developer"   # linkedin 1 query
```
| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--provider` | jobspy | Một provider |
| `--query` | 8 query | Query đơn; bỏ trống → 8 query IT mặc định |
| `--all` | off | Dùng tất cả provider mặc định (loại linkedin + adzuna) |
| `--location` | "" | Lọc địa điểm |
| `--results` | 50 | Số job / query |
| `--workers` | = số provider | Số provider song song |
| `--delay` | 1.0 | Giây giữa các request mỗi provider |
| `--out-dir` | `data/crawl` | Thư mục output gốc |

---

## 🤖 Extract (crawl → JD fields)

### `extract_jobs` — extract bằng LLM → file

Đọc `data/crawl/<provider>/<date>.json` → gọi **LLM** (`llm_jd_extractor` / `LLMService`, cần provider active) extract seniority/role/skills/… cho từng job (song song) → ghi `data/extracted/<provider>/<date>.json` (mỗi job + block `extracted`). **Dashboard live**: header tiến độ + **bảng mỗi worker 1 dòng** (state `● run`/`↻ retry` + job title đang xử lý) — cập nhật realtime.

```bash
.venv/bin/python manage.py extract_jobs                       # hôm nay, mọi provider
.venv/bin/python manage.py extract_jobs --provider remotive --workers 6
.venv/bin/python manage.py extract_jobs --provider jobspy --flush-every 20
```
- **Ghi dần (crash-safe)**: lưu file mỗi `--flush-every` job xong (mặc định 10), không gom tới cuối. File trung gian luôn hợp lệ (`extracted` hoặc `null`).
- **Resume**: chạy lại cùng file → **bỏ qua job đã có `extracted`**, chỉ làm phần còn thiếu (tiết kiệm phí, tiếp tục sau khi Ctrl+C).
- Tách extraction (bước LLM tốn phí) khỏi DB-write: ra file rồi `import_extracted` nạp **không gọi LLM lại**. (Còn `import_jobs`/`save_raw_job` thì extract LLM **inline** lúc import.)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--provider` | tất cả | Chỉ extract folder provider này |
| `--date` | hôm nay | File `<date>.json` |
| `--in-dir` | `data/crawl` | Thư mục crawl input |
| `--out-dir` | `data/extracted` | Thư mục output |
| `--workers` | 4 | Số LLM call song song (giảm nếu bị rate-limit / timeout) |
| `--retries` | 2 | Thử lại mỗi job khi timeout / kết quả rỗng (backoff) |
| `--desc-chars` | 6000 | Cắt description / job (giảm token / phí) |
| `--flush-every` | 10 | Ghi file mỗi N job xong (crash-safe) |
| `--limit` | 0 | Giới hạn job / file (debug) |

> 🩺 Nếu nhiều **"read operation timed out"** / provider log *"client closed before stream finished"* → provider (proxy) đang chậm/quá tải. Khắc phục: **giảm `--workers`** (vd 2), tăng `--retries`, hoặc đổi provider ổn định hơn. (LLM client đã nới timeout 120s + có retry; job timeout sẽ thành `null` → chạy lại lệnh sẽ **resume** retry chúng.)

### `import_extracted` — extracted JSON → DB (KHÔNG gọi LLM)

```bash
.venv/bin/python manage.py import_extracted --provider remotive --dry-run
.venv/bin/python manage.py import_extracted
```
Đọc `data/extracted/**` → `JobService.save_raw_job(raw, extracted=...)` → `Job` + `JobSkill`, **không** gọi LLM (đã extract sẵn).

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--provider` | tất cả | Chỉ folder provider này |
| `--date` | tất cả | File `<date>.json` |
| `--in-dir` | `data/extracted` | Thư mục input |
| `--dry-run` | off | Chỉ đếm, không ghi DB |

## 📥 Nạp vào DB (đường khác)

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

# 2. extract bằng LLM → file
.venv/bin/python manage.py extract_jobs

# 3. nạp DB (không gọi LLM lại — đã extract sẵn)
.venv/bin/python manage.py import_extracted

# 4. bảo trì + rank
.venv/bin/python manage.py dedup_jobs
.venv/bin/python manage.py rebuild_job_pool        # (app khác) → để GNN rank job mới
```

> **Train model là offline** (`run_train_save.py`, LLM labels, GPU Neptune) — xem `docs/codebase-knowledge/05-training-pipeline.md`. Không có lệnh retrain in-app.
