# Phase 0 — Research: CareerBuilder12 Benchmark

**Date**: 2026-05-21
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

## R1. Dataset source — Kaggle mirror

### Decision

Dùng **`jsrshivam/job-recommendation-case-study`** trên Kaggle. Confirmed bằng `kaggle datasets files`:

```
apps.tsv           75 MB    — applications (user, job, date)
jobs.tsv          3.4 GB    — full job description text
users.tsv          35 MB    — user profile
user_history.tsv   72 MB    — work history (defer cho US2)
test_users.tsv    234 KB    — competition test split (defer — ta dùng LOO chuẩn)
window_dates.tsv   <1 KB    — competition date windows (defer)
popular_jobs.csv   24 MB    — popularity baseline (defer)
```

Tổng compressed: ~766 MB. Extracted: ~3.6 GB.

### Rationale

- **Schema chuẩn**: đúng pattern `users.tsv` + `jobs.tsv` + `apps.tsv` của CareerBuilder Job Recommendation Challenge 2012 (Kaggle competition).
- **Public + cached**: 664 downloads, ổn định từ 2020, không bị takedown.
- **Có bonus data**: `user_history.tsv` cho hetero variant tương lai (skill từ work history), không cần Phase 3.

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| `promptcloud/careerbuilder-job-listing-*` | Chỉ là job listing, KHÔNG có user-job interaction |
| Kaggle CB Challenge gốc | Competition closed, dataset không public link trực tiếp |
| Tự crawl CareerBuilder.com | Vi phạm ToS, không reproducible |

---

## R2. Download mechanism

### Decision

Identical Phase 2: `kaggle datasets download -d jsrshivam/job-recommendation-case-study --unzip` vào `Dataset/careerbuilder-12/`. Reuse `~/.kaggle/kaggle.json` đã có.

### Rationale

- Kaggle CLI đã cài và auth từ Phase 2
- `--unzip` extract tự động vào folder
- Cache check: nếu folder đã có `apps.tsv` + `jobs.tsv` + `users.tsv` thì skip download

---

## R3. TSV parsing

### Decision

`pandas.read_csv(sep='\t', encoding='ISO-8859-1', on_bad_lines='warn', low_memory=False)` cho mọi file. CB12 có:
- Encoding mixed (chủ yếu ISO-8859-1)
- Bad rows (special chars, missing fields)
- Cột `Description` (jobs.tsv) chứa text dài + newline trong field → cần `quoting=csv.QUOTE_MINIMAL` hoặc parse cẩn thận

Với `jobs.tsv` 3.4GB, dùng `chunksize=100000` để stream parse, chỉ giữ cột cần:
- Cho US1 bipartite: chỉ cần `JobID`
- Cho US2 hetero: cần `JobID`, `Title`, `Description` (text), `State`/`City`

### Rationale

- pandas đã có trong env
- ISO-8859-1 chịu được encoding noise của CB12
- `on_bad_lines='warn'` không crash khi gặp bad row (~vài chục row trên 1.6M)
- Chunked parse cần thiết với 3.4GB file (full load = 8GB+ RAM)

### Alternatives considered

- `dask.read_csv` cho parallel parsing — overkill, thêm dep
- Pure stdlib `csv` module — chậm hơn pandas, không có chunksize tự nhiên

---

## R4. jobs.tsv 3.4GB — strategy giảm tải

### Decision

3-tier loading:

1. **Tier 1 (default cho US1 bipartite)**: chỉ load cột `JobID` từ `jobs.tsv` → ~5MB RAM. Dùng `usecols=['JobID']` trong pandas.
2. **Tier 2 (US2 hetero, future)**: load thêm `Title`, `City`, `State` để parse seniority + location → ~50MB
3. **Tier 3 (Phase 4+ nếu cần)**: full Description text cho text embedding → 3.4GB streaming

Phase 3 chỉ dùng Tier 1 + Tier 2.

### Rationale

- Tránh OOM trên dev laptop khi prototype
- Save time download (vẫn download full file nhưng parse chọn cột)
- Defer text embedding cho phase sau

### Alternatives considered

- Pre-process jobs.tsv → trimmed jobs.parquet trong cache step (1 lần) — optimization, defer nếu thấy chậm

---

## R5. Subsample strategy

### Decision

**Random 50K user** từ tổng ~1.6M user trong `users.tsv`:

```python
rng = np.random.default_rng(42)  # seed fix
all_user_ids = users_df['UserID'].values
sampled = rng.choice(all_user_ids, size=50_000, replace=False)
apps_filtered = apps_df[apps_df['UserID'].isin(sampled)]
# Sau đó áp k-core=10
```

Áp dụng TRƯỚC k-core. Lý do:
- 1.6M user × 380K job → eval cost O(600 tỷ pair scores), vượt GPU budget
- 50K user ≈ scale Phase 2 MovieLens (~6K user) × 8 → khoảng 1-2 phút full eval mỗi epoch trên RTX 3090

### Rationale

- 50K đủ lớn để có nhiều seed signal sau k-core
- 50K đủ nhỏ để fit < 1h GPU/seed (SC-009)
- Seed fix = reproducible
- Random sampling = unbiased (so với "first 50K" hay "active 50K")

### Alternatives considered

- Subsample by app count (top 50K active user) — biased toward power user
- Time window (chỉ giữ apps trong 3 tháng cuối) — biased toward recent jobs
- Full dataset với mini-batch sampling — phức tạp hóa pipeline, defer

---

## R6. K-core filtering

### Decision

**Identical Phase 2 R5**: iterative bipartite k-core với k=10. Áp dụng sau subsample user, trước split.

```python
def k_core_filter(interactions, k=10):
    while True:
        user_deg = Counter(u for u, _ in interactions)
        job_deg = Counter(j for _, j in interactions)
        new = [(u, j) for u, j in interactions
               if user_deg[u] >= k and job_deg[j] >= k]
        if len(new) == len(interactions):
            return new
        interactions = new
```

### Rationale

Copy exact pattern Phase 2. Verified work với MovieLens.

---

## R7. Leave-one-out split

### Decision

**Identical Phase 2 R6**: sort apps per user theo `ApplicationDate` ascending. Last → test, second-last → val, rest → train.

Schema apps.tsv:
```
UserID  WindowID  Split  ApplicationDate  JobID
```

Dùng `ApplicationDate` cho sort. Ignore competition `Split` field (Train/Test) — ta dùng LOO chuẩn LightGCN.

### Rationale

- Chuẩn LightGCN paper §4.1.2
- Reproducible với Phase 2 methodology
- Per-user split bảo toàn user signal

### Alternatives considered

- Dùng competition split (Train/Test field) — không LOO, không khớp Phase 2 methodology

---

## R8. Hetero variant (US2 stretch)

### Decision

Defer chi tiết. Tentative approach nếu làm:

1. **Skill node**: extract bằng keyword matching từ `jobs.tsv` `Description` cột, dùng `ml_benchmark/data/skill-alias.json` (~1147 dòng — đã có sẵn từ JobFlow sandbox).
2. **Seniority node**: parse từ `jobs.tsv` `Title` bằng regex (Junior/Mid/Senior/Lead/Manager), reuse logic từ JobFlow `ml_benchmark/graph/schema.py` `SeniorityLevel` enum.
3. **Location node** (optional): từ `City` + `State` cột — có thể giúp recommendation.

Không thực hiện trong Phase 3 P1; ghi nhận để Phase 5 hoặc dedicated phase sau.

### Rationale

- Skill extraction bằng keyword đơn giản, deterministic, đủ noise-tolerant cho benchmark
- Seniority regex rule sẵn có
- Tránh LLM-based extraction (đắt, không reproducible)

---

## Tổng kết

8 quyết định kỹ thuật chốt. All NEEDS CLARIFICATION resolved. Sẵn sàng Phase 1.
