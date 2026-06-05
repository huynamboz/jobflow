# JobFlow GNN — Architecture & Flow

> Tài liệu này mô tả toàn bộ kiến trúc hệ thống, flow dữ liệu, và cách các thành phần liên kết với nhau.
> Mục đích: đảm bảo không đi sai hướng khi build thêm tính năng.
>
> Cập nhật: 2026-05-14 — đồng bộ với code thực tế (`backend/ml_service/` + `backend/apps/`).
>
> Hai lớp tách rời:
> 1. **ML pipeline** (offline) — extraction → graph → train GNN + reranker → checkpoint
> 2. **Production ops** (online) — crawler + verifier lifecycle + date extractor + schedule daemon + admin dashboard

---

## Bài toán

**Matching CV ↔ Job** — Cho một CV, tìm các Job phù hợp nhất (và ngược lại).

Đây là bài toán **ranking**, không phải classification đơn thuần:
- Không chỉ trả lời "phù hợp hay không"
- Mà phải **sắp xếp thứ tự** từ phù hợp nhất → kém nhất

---

## Kiến trúc tổng quan

```
┌─────────────────────────────────────────────────────────┐
│                    RAW DATA                             │
│  CVs (PDF/DOCX → raw_text)   JDs (LinkedIn crawl)      │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────┐      ┌─────────────────────────┐
│  CV Batch Extraction │      │   JD Batch Extraction   │
│  LLM → structured   │      │   LLM → structured      │
│  role_category       │      │   role_category          │
│  seniority (0-5)     │      │   seniority (0-5)*       │
│  skills + proficiency│      │   skills + importance    │
│  experience_years    │      │   experience_min/max     │
└──────────┬──────────┘      └────────────┬────────────┘
           │                              │
           └──────────────┬───────────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │      GRAPH DATABASE      │
           │  CV nodes ←→ Skill nodes │
           │  Job nodes ←→ Skill nodes│
           │  Skill ←→ Skill (PMI)    │
           │  Seniority nodes         │
           └──────────────┬───────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │   PAIR GENERATION        │
           │  4 strategies (xem bên   │
           │  dưới), split 70/15/15   │
           └──────────────┬───────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │   LLM LABELING           │
           │  skill_fit 0/1/2         │
           │  seniority_fit 0/1/2     │
           │  experience_fit 0/1/2    │
           │  domain_fit 0/1/2        │
           │  overall 0/1/2           │
           └──────────────┬───────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │   MODEL TRAINING         │
           │  1. GNN (HeteroSAGE)     │
           │  2. MLP Reranker         │
           │     (ordinal 3-class)    │
           └──────────────┬───────────┘
                          │
                          ▼
           ┌────────────────────────────┐
           │   INFERENCE ENGINE         │
           │  Stage 1: Retrieve top N=200│
           │  Stage 2: Rerank → top K   │
           └────────────────────────────┘
```

*JD seniority có hard override rule: title chứa "intern/co-op/fresher/trainee/thực tập" → bắt buộc seniority=0, bất kể skills hay experience trong JD.

---

## Node Features trong Graph

| Node type | Dims | Features |
|-----------|------|---------|
| CV | 386 | 384-dim sentence embedding (full text) + experience_years + education_level |
| Job | 397 | 384-dim sentence embedding (full text) + salary_min_norm + salary_max_norm + role_category_onehot(11) |
| Skill | 385 | 384-dim embedding (skill name) + category |
| Seniority | 6 | One-hot (6 mức: Intern=0 → Manager=5) |

**Embedding model:** `all-MiniLM-L6-v2` (SentenceTransformers, 384-dim)

**Edge types** (xây trong `ml_service/graph/builder.py`):

| Edge | Attr | Mô tả |
|------|------|-------|
| `(CV) -[has_skill]→ (Skill)` | proficiency (1–5) | CV biết skill này |
| `(Job) -[requires_skill]→ (Skill)` | importance (1–5) | Job yêu cầu skill này |
| `(CV) -[has_seniority]→ (Seniority)` | — | CV thuộc mức seniority nào |
| `(Job) -[requires_seniority]→ (Seniority)` | — | Job yêu cầu mức seniority nào |
| `(Skill) -[relates_to]→ (Skill)` | PMI score (+ semantic ≥ 0.70) | Skills liên quan nhau (co-occurrence + skill-name embedding similarity) |
| `(CV) -[similar_profile]→ (CV)` | Jaccard ≥ 0.3 | CVs có skill profile giống nhau |
| `(Job) -[similar_to]→ (Job)` | Jaccard | Jobs có skill profile giống nhau |
| `(CV) -[match]→ (Job)` | — | Training signal: positive pair |
| `(CV) -[no_match]→ (Job)` | — | Training signal: negative pair |

Lưu ý: `relates_to`, `similar_profile`, `similar_to` được builder add trực tiếp vào `HeteroData` nhưng **không** liệt kê trong enum `EdgeType` của `graph/schema.py` (enum chỉ có 6 loại bắt buộc cho training signal).

---

## Inference Flow (2-Stage)

### Stage 1 — Retrieve (fast, top N)

`InferenceEngine.match_cv()` mặc định `retrieve_n=200` (`engine.py:223`). Tất cả `N` job được scoring và rerank, top-K trả về cho user.

```
score = α × GNN_score + β × skill_overlap + γ × seniority_score
      = 0.55 × GNN_score + 0.30 × skill_overlap + 0.15 × seniority_score
```

Trong đó:
- `GNN_score = 0.6 × sigmoid(gnn_decode(cv_emb, job_emb)) + 0.4 × cosine(cv_text, job_text)` (cả 2 đều normalize về [0,1])
- `skill_overlap` = weighted Jaccard (theo importance), có PMI bonus (×0.6) cho related skills
- `seniority_score = max(0, 1 - |cv_seniority - job_seniority| × 0.4)`

**Trọng số `0.55/0.30/0.15` là hardcode (heuristic)**, không học từ data — chỉ làm điểm khởi đầu cho Stage 2.

Stage 1 còn áp các multiplicative penalty **trong lúc scoring** (`_apply_must_have_penalty` + `_apply_edge_case_penalties`):

| Tình huống | Multiplier |
|------------|-----------|
| Missing required (importance ≥ 4) — 1 skill thiếu | ×0.90 |
| Missing required — 2 thiếu | ×0.75 |
| Missing required — ≥3 thiếu | ×0.60 |
| CV < 4 skills (sparse profile) | ×0.85 |
| `cv_seniority ≥ 3` và `job_seniority ≤ 1` (senior CV vs intern/junior job) | ×0.80 |
| Job < 3 skills (sparse JD — Stage-1 only) | ×0.80 |
| Intersection toàn tool skills (git, jira, docker…) | ×0.75 |
| Role mismatch (`role_match_penalty`) | nhân hệ số ∈ [0.5, 1.0] |

**Display-score penalties (áp sau Stage 2, trên reranker score):**

| Tình huống | Multiplier | Label set ở `dim_scores` |
|------------|-----------|-------------------------|
| `cv_exp < job_exp_min` (thiếu năm kinh nghiệm) | ×0.40 | `experience_fit=weak` |
| `cv_exp − job_exp_min > 3yr` (overqualified về năm) | ×0.85 | `experience_fit=weak` |
| `job_seniority − cv_seniority ≥ 2` hoặc (gap ≥ 1 và job ≥ Senior, CV ≤ Mid) | ×0.70 | `seniority_fit=weak` |
| `cv_seniority − job_seniority ≥ 2` (overqualified về seniority) | ×0.75 | `seniority_fit=weak` |

`experience_fit` và `seniority_fit` là hai gate độc lập — có thể cùng bị weak một lúc.

### Stage 2 — Rerank (learned, top 50 → top K)

**Model:** `_RerankerMLP` — PyTorch MLP với multi-task learning.

```
Architecture:
  Input (23 features)
    → Linear(23, 64) → ReLU → Dropout(0.2)
    → Linear(64, 64) → ReLU → Dropout(0.2)
    → main_head: Linear(64, 3)    ← ordinal 3-class (overall)
    → aux_heads: 4 × Linear(64, 3) ← skill_fit, experience_fit, seniority_fit, domain_fit
                                      (chỉ dùng khi train, không dùng khi inference)

Score = E[class] = (0×p₀ + 1×p₁ + 2×p₂) / 2  →  [0, 1]
```

**Loss:** `CrossEntropyLoss` (ordinal 3-class) + weighted auxiliary loss.

**23 features:**

| # | Feature | Mô tả |
|---|---------|-------|
| 1 | `text_similarity` | Cosine similarity của full text embeddings |
| 2 | `skill_overlap_jaccard` | Jaccard unweighted |
| 3 | `skill_overlap_weighted` | Jaccard weighted theo importance |
| 4 | `semantic_skill_overlap` | Jaccard + PMI bonus cho related skills |
| 5 | `missing_required_count` | Số skills importance≥4 bị thiếu |
| 6 | `missing_required_ratio` | missing/total required |
| 7 | `matched_skill_count` | Số skills khớp |
| 8 | `total_job_skills` | Tổng skills trong JD |
| 9 | `seniority_distance` | \|cv_seniority - job_seniority\| |
| 10 | `seniority_score` | max(0, 1 - dist×0.4) |
| 11 | `role_penalty` | Penalty khi cv_role ≠ job_role |
| 12 | `experience_years` | Số năm kinh nghiệm của CV |
| 13 | `cv_skill_count` | Số skills trong CV |
| 14 | `skill_specificity` | Độ hiếm trung bình của CV skills |
| 15 | `tool_ratio` | Tỷ lệ tool skills (git, jira, docker...) trong CV |
| 16 | `stage1_score` | Score Stage 1 cho cặp này |
| 17 | `gnn_score` | Raw GNN decode score |
| 18 | `gnn_rank` | Rank Stage 1 normalized [0,1] |
| 19 | `must_have_cap_triggered` | 0/0.5/1.0 theo số required skills bị thiếu |
| 20 | `edge_case_penalty_triggered` | Binary: 1 nếu hit edge case |
| 21 | `skill_coverage_ratio` | matched / total_job_skills |
| 22 | `experience_gap` | (cv_exp - job_exp_min) / 10, clamp [-0.5, 1.0] |
| 23 | `role_category_match` | 1.0 nếu infer_role(CV) == job.role_category |

**Trọng số Stage 2 được HỌC từ labeled pairs** — không hardcode.

---

## LLM Extraction

### CV Extraction

| Field | Type | Mô tả |
|-------|------|-------|
| `name` | string | Tên candidate |
| `experience_years` | float | Số năm kinh nghiệm |
| `seniority` | int 0–5 | Intern/Junior/Mid/Senior/Lead/Manager |
| `role_category` | enum | backend/frontend/fullstack/mobile/devops/data_ml/data_eng/qa/design/ba/other |
| `education` | enum | none/college/bachelor/master/phd |
| `skills` | list | Canonical skill names + proficiency 1–5 |
| `work_experience` | list | title, company, duration, description |

**Rule quan trọng:** Extract ONLY skills explicitly mentioned — không infer từ title hay context.

### JD Extraction

| Field | Mô tả |
|-------|-------|
| `title` | Job title as-is |
| `company` | Tên công ty |
| `location` | City, Country |
| `is_remote` | bool |
| `seniority` | 0–5 (với title override rule*) |
| `role_category` | Cùng enum với CV |
| `job_type` | full-time/part-time/contract/hybrid/on-site |
| `experience_min/max` | Số năm yêu cầu (float) |
| `salary_min/max` | Numeric, giữ nguyên currency gốc |
| `salary_currency` | USD/VND/EUR/... |
| `salary_type` | hourly/monthly/annual |
| `degree_requirement` | 0–5 (None → PhD) |
| `skills` | Canonical names + importance 1–5 |

**Importance scale (JD):**
- 5 = Must-have (thiếu là loại ngay) — tối đa 30% skills
- 4 = Required
- 3 = Preferred
- 2 = Nice-to-have
- 1 = Bonus / tangential

*Title override rule: nếu title chứa `intern/internship/fresher/trainee/co-op/thực tập` → seniority=0, không cần đọc skills hay experience.

---

## Pair Generation Strategy

Pipeline chính `python manage.py generate_pairs` (`apps/labeling/management/commands/generate_pairs.py`):

| Type | Cách chọn | Mục đích | Tỉ lệ sample target |
|------|-----------|---------|--------------------|
| `high_overlap` | Same/related role + Jaccard ≥ 0.20 | Positive examples rõ ràng | 30% |
| `medium_overlap` | Same/related role + 0.08 ≤ Jaccard < 0.20 | Hard positive | 40% |
| `hard_negative` | Same/related role + Jaccard < 0.08 | Model-confusing negatives (low overlap, compatible role) | 20% |
| `random` | Incompatible role (capped `max_per_cv=12`) | Easy negative | 10% |

Ngưỡng Jaccard và sample ratio đều được hardcode trong `generate_pairs.py` (`overlap >= 0.20 / >= 0.08 / else`, ratios `0.30/0.40/0.20/0.10`).

**Dataset hiện tại — `data/processed/b89_full` (training input của checkpoint `gnn_v2`):**
- Tổng: **11,509 labeled pairs** (3,786 positive — 33% / 7,723 negative)
- Split: 8,020 train / 1,753 val / 1,736 test (~70/15/15)
- Batch IDs: 6, 8, 9, 10

**Hard negative mining bổ sung** (`mine_hard_negatives.py`, **không** trong flow `generate_pairs`): score toàn bộ CV×Job qua Stage-1, lấy pairs với `score ≥ 0.50 và Jaccard < 0.35` (model đang nhầm) → insert PENDING vào `PairQueue` → LLM label. Đây là pipeline thứ 2, tách biệt với rule-based generation ở trên.

---

## LLM Labeling

**Label dimensions:**
- `skill_fit` 0/1/2: CV skills đáp ứng JD requirements không
- `experience_fit` 0/1/2: số năm kinh nghiệm có phù hợp không
- `seniority_fit` 0/1/2: seniority có khớp không
- `domain_fit` 0/1/2: role_category có khớp không
- `overall` 0/1/2: kết luận tổng thể

**Phân phối hiện tại trên `b89_full` (11,509 pairs):**
- overall=0 (not fit): ~67%
- overall=1 (suitable): ~26%
- overall=2 (strong): ~7%
- `label` (binary fit/not): 3,786 positive (33%) / 7,723 negative

**Data quality tools:**
- `relabel_experience.py` — programmatic fix cho pairs noisy về experience_fit
- `generate_exp_negatives.py` — synthetic negatives khi cv_exp < 65% job_exp_min (unambiguous, không cần LLM)

---

## Canonical Skill System

**218 canonical identifiers** trong prompt files (`jd_extraction.md`, `cv_extraction.md`).

**Quy tắc:**
- Tất cả skill names phải là canonical (lowercase, underscore)
- LLM được cung cấp danh sách canonical để map
- `SkillNormalizer` xử lý alias: "React.js" → "react", "PostgreSQL" → "postgresql"
- Skill không map được → bỏ qua

---

## Dependency Chain (thứ tự bắt buộc — ML pipeline)

```
1. CV batch extraction (role_category + seniority + skills đúng)
        ↓ bắt buộc hoàn thành trước
2. JD batch extraction (song song với bước 1)
        ↓
3. Generate pairs (cần role_category để filter có nghĩa)
        ↓
4. LLM labeling (cần pairs)
        ↓
5. Train GNN (run_train_save.py — cần labeled pairs)
        ↓
6. Train MLP Reranker (run_train_reranker.py — cần GNN embeddings + labeled pairs)
        ↓
7. Stage 2 inference hoạt động (patch checkpoint nếu cần)
```

**Checkpoint patch:** nếu thay đổi DB data (seniority, skills) mà không retrain, cần patch `checkpoints/<name>/jobs.json` thủ công vì engine đọc từ file, không từ DB trực tiếp (xem `patch_checkpoint_jobs.py`).

---

## Production Ops Layer (online, runtime job pool)

Mảng này chạy độc lập với ML pipeline ở trên — mục đích là giữ job pool sạch & up-to-date cho engine inference dùng. Code chính ở `backend/ml_service/verifier/` + `backend/apps/schedule/` + `backend/apps/admin_dashboard/`.

```
┌─────────────────────────────────────────────────────────────────┐
│              CRAWLER (run_crawl.py — LinkedIn)                 │
│   → Job rows: lifecycle=ACTIVE, last_seen_at=now               │
└─────────────────┬──────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│   JD EXTRACTION (LLM) → JDExtractionRecord(result, status=DONE)│
└─────────────────┬──────────────────────────────────────────────┘
                  ↓
        ┌─────────┴────────┐
        ↓                  ↓
┌──────────────┐   ┌──────────────────┐
│ verify_job_  │   │ extract_job_dates │
│ status       │   │  + bundled verify │
│ (Playwright) │   │  (Playwright)     │
└──────┬───────┘   └─────────┬────────┘
       ↓                     ↓
   Lifecycle             Job.date_posted
   transitions:          + JobStatus
   ACTIVE → STALE (aged ≥14d)
   ACTIVE → EXPIRED (404/closed)
   → write VerifierRunLog row
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│         SCHEDULE DAEMON (apps/schedule/management/              │
│                         commands/schedule_runner.py)            │
│   forever: tick 60s → read VerifierSchedule rows →              │
│            subprocess.Popen(verify/extract) when hour matches   │
└─────────────────────────────────────────────────────────────────┘
```

### Verifier subsystem (`ml_service/verifier/`)

- `base.py` — `JobStatus` enum (ACTIVE / EXPIRED / SESSION_EXPIRED / UNKNOWN / ERROR) + `JobStatusVerifier` ABC
- `service.py` — `StatusCheckService` orchestrator: aging rule (active ≥14d → stale) + dispatch verify
- `backfill_service.py` — `DateBackfillService` cho `extract_job_dates` (bundled verify khi backfill date)
- `providers/linkedin_verifier.py` — Playwright SDUI scraping cho LinkedIn (active markers, closed-job detection)
- `selectors/linkedin.json` — CSS/XPath selectors có thể hot-swap không cần redeploy
- `auth_guard.py` — kiểm tra `linkedin_state.json` (`li_at` cookie) trước khi spawn
- `browser_pool.py` — Playwright context pool

`Job` model có 4 lifecycle state + verification metadata (`last_seen_at`, `last_verified_at`, `verification_attempts`, `verification_backoff_until`). `VerifierRunLog` lưu history mỗi lần verify/extract chạy (counts_by_outcome, wall_clock).

### Schedule daemon (`apps/schedule/`)

In-process daemon (KHÔNG dùng Celery/Redis) — operator config qua admin UI, daemon đọc DB và spawn subprocess:

- `models.VerifierSchedule` — 1 row per command (`verify_job_status` | `extract_job_dates`), giữ config (`hours_utc`, `batch_size`, `enabled`) + active-run trio (`current_run_pid`, `started_at`, `log_path`) + `last_fired_at` để idempotent
- `services.py` — `start_run` / `stop_run` (SIGTERM process group) / `is_active_run` (kill -0 probe) / `tail_live_log` (seek + read offset)
- `management/commands/schedule_runner.py` — forever loop, tick 60s mặc định
- `views.py` — REST `/api/admin/schedule/<cmd>/...` (config, start, stop, live-log, history)

Mỗi spawn dùng `subprocess.Popen(..., start_new_session=True)` để child Chromium + Playwright sống độc lập daemon (kill daemon không giết job đang chạy). Log đi vào `backend/logs/runs/<cmd>_<TS>.log` — frontend poll 2s với byte-offset (không SSE/WebSocket). Chi tiết: `roadmap/docs/schedule.md`.

### Admin dashboard (`apps/admin_dashboard/`)

REST KPI cho operator (`/api/admin/dashboard/...`):

| Endpoint | Phục vụ card |
|----------|--------------|
| `kpi/` | counts tổng (jobs/CVs/pairs/active labels) |
| `catalog/` | distribution theo role, seniority, platform |
| `freshness/` | tỷ lệ jobs unverified / stale / expired theo bucket thời gian |
| `ops/` | verifier run stats (success/error/session_expired rate) |
| `labeling/` | PairQueue progress (pending / done / split distribution) |
| `model/` | metadata.json + calibration.json từ checkpoint hiện tại |

UI: `admin/src/pages/admin/` (React + Vite). Page schedule chia sẻ component `_schedule-page.tsx`.

### Specs liên quan

- `specs/001-linkedin-job-verifier/` — verifier lifecycle (Week 9)
- `specs/002-job-date-posted-extraction/` — date extraction (Week 10)
- `specs/003-admin-dashboard-v2/` — dashboard cards (Week 12, active)
- `specs/005-verify-schedule-dashboard/` — schedule daemon + live-log UI (Week 13)

---

## Những gì KHÔNG làm

- **Không dùng Word2Vec hay TF-IDF** — dùng SentenceTransformers (tốt hơn nhiều)
- **Không label thủ công** — dùng LLM auto-label
- **Không hardcode trọng số final ranking** — MLP học từ data
- **Không include HR/PM CVs** — tập trung dev roles (AI/SE/DevOps/QA/UX)
- **Không cosine similarity đơn thuần** — 2-stage: GNN + MLP reranker
- **Không infer skills từ job title** — LLM CV parser chỉ lấy skills được mention explicitly

---

## Kết quả hiện tại (checkpoint `gnn_v2` / `latest`)

Đọc trực tiếp từ `backend/checkpoints/latest/metadata.json` + `calibration.json`:

| Metric | Giá trị |
|--------|---------|
| GNN Test AUC-ROC | **0.8764** |
| GNN NDCG@5 | 1.000 |
| GNN Precision@5 | 1.000 |
| GNN Hit@5 | 1.000 |
| GNN MRR | 1.000 |
| Best epoch | 299 |
| Labeled pairs (train input) | 11,509 (`data/processed/b89_full`) |
| CVs / Jobs trong checkpoint | 364 / 6,251 |
| Reranker | MLP ordinal 3-class, 23 features |
| Hidden / Layers (GNN) | 256 / 3 |
| Calibration (Platt) | a = 1.0162, b = −1.0778 |

**Ranking quality theo domain:**

| Domain | Jobs trong DB | Ranking quality |
|--------|--------------|----------------|
| Frontend | 746 | Excellent |
| QA | 630 | Excellent |
| Fullstack | 868 | Good |
| Data ML | 515 | Good |
| DevOps | 492 | Medium |
| Backend | 373 | Medium (ít data) |
| Design | 252 | Medium |
| BA | 216 | Medium |
| Mobile | 149 | Weak (quá ít data) |
| Data Eng | 147 | Weak (quá ít data) |

---

## Lịch sử AUC-ROC

| Tuần | AUC-ROC | Labels | Reranker | Highlights |
|------|---------|--------|----------|------------|
| Week 1 | 0.550 | ~2,000 | Không có | Synthetic baseline |
| Week 2 | 0.712 | 9,889 | Rule-based | Real data |
| Week 9 | 0.701 | 9,889 | Rule-based | Fix early stopping |
| Week 10 (b89) | 0.790 | 5,206 | Binary MLP | LLM labels, biased |
| Week 10 (v2) | 0.786 | 11,565 | Binary MLP 81.2% | Dataset cân bằng |
| **Week 11 (gnn_v2)** | **0.876** | **11,509** | **Ordinal 3-class MLP** | 23 features, intern fix, b89_full |
| Week 12+ | n/a (no retrain) | — | — | Verifier lifecycle, dashboard, schedule daemon (ops layer) |
