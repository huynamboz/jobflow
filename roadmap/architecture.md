# JobFlow GNN — Architecture & Flow

> Tài liệu này mô tả toàn bộ kiến trúc hệ thống, flow dữ liệu, và cách các thành phần liên kết với nhau.
> Mục đích: đảm bảo không đi sai hướng khi build thêm tính năng.
>
> Cập nhật: 2026-04-24 (Week 11)

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
           ┌──────────────────────────┐
           │   INFERENCE ENGINE       │
           │  Stage 1: Retrieve top 50│
           │  Stage 2: Rerank → top K │
           └──────────────────────────┘
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

**Edge types:**
| Edge | Attr | Mô tả |
|------|------|-------|
| `(CV) -[has_skill]→ (Skill)` | proficiency (1–5) | CV biết skill này |
| `(Job) -[requires_skill]→ (Skill)` | importance (1–5) | Job yêu cầu skill này |
| `(CV) -[has_seniority]→ (Seniority)` | — | CV thuộc mức seniority nào |
| `(Job) -[requires_seniority]→ (Seniority)` | — | Job yêu cầu mức seniority nào |
| `(Skill) -[relates_to]→ (Skill)` | PMI score | Skills liên quan nhau (co-occurrence) |
| `(CV) -[similar_profile]→ (CV)` | Jaccard ≥ 0.3 | CVs có skill profile giống nhau |
| `(Job) -[similar_to]→ (Job)` | Jaccard | Jobs có skill profile giống nhau |
| `(CV) -[match]→ (Job)` | — | Training signal: positive pair |
| `(CV) -[no_match]→ (Job)` | — | Training signal: negative pair |

---

## Inference Flow (2-Stage)

### Stage 1 — Retrieve (fast, top 50)

```
score = α × GNN_score + β × skill_overlap + γ × seniority_score
      = 0.55 × GNN_score + 0.30 × skill_overlap + 0.15 × seniority_score
```

Trong đó:
- `GNN_score = 0.6 × gnn_decode(cv_emb, job_emb) + 0.4 × cosine(cv_text, job_text)`
- `skill_overlap` = weighted Jaccard (theo importance), có PMI bonus (+0.6×) cho related skills
- `seniority_score = max(0, 1 - |cv_seniority - job_seniority| × 0.4)`

**Trọng số `0.55/0.30/0.15` là hardcode (heuristic)**, không học từ data.
Chỉ để lọc sơ top 50 candidates, không phải kết quả cuối.

**Penalties áp dụng thêm (sau khi có reranker score):**

| Tình huống | Multiplier | Label |
|------------|-----------|-------|
| `cv_exp < job_exp_min` (thiếu năm kinh nghiệm) | ×0.40 | `experience_fit=weak` |
| `cv_exp − job_exp_min > 3yr` (overqualified về năm) | ×0.85 | `experience_fit=weak` |
| `job_seniority − cv_seniority ≥ 2` hoặc job Senior+ mà CV ≤ Mid | ×0.70 | `seniority_fit=weak` |
| `cv_seniority − job_seniority ≥ 2` (overqualified về seniority) | ×0.75 | `seniority_fit=weak` |
| Role mismatch (cv_role ≠ job_role) | giảm nhẹ | — |
| Must-have skill thiếu (importance ≥ 4) | giảm theo số thiếu | — |
| Edge case: CV < 4 skills / intersection toàn tools | ×penalty | — |

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

| Type | Cách chọn | Mục đích | Số lượng (hiện tại) |
|------|-----------|---------|-------------------|
| `high_overlap` | Jaccard ≥ 0.5 + same role | Positive examples rõ ràng | ~1,505 |
| `medium_overlap` | Jaccard 0.2–0.5 + same/related role | Hard positive | ~2,178 |
| `hard_negative` | Stage-1 score ≥ 0.50 nhưng Jaccard < 0.35 | Model-confusing negatives | ~3,360 |
| `random` | Random CV × Job | Easy negative | ~3,495 |

**Tổng hiện tại: 11,611 labeled pairs** (split 70/15/15)

**Hard negative mining** (`mine_hard_negatives.py`): score toàn bộ CV×Job pool qua Stage-1, lấy pairs model đang bị nhầm để đưa vào PairQueue → LLM label.

---

## LLM Labeling

**Label dimensions:**
- `skill_fit` 0/1/2: CV skills đáp ứng JD requirements không
- `experience_fit` 0/1/2: số năm kinh nghiệm có phù hợp không
- `seniority_fit` 0/1/2: seniority có khớp không
- `domain_fit` 0/1/2: role_category có khớp không
- `overall` 0/1/2: kết luận tổng thể

**Phân phối hiện tại (11,611 pairs):**
- overall=0 (not fit): 7,778 — 67%
- overall=1 (suitable): 3,009 — 26%
- overall=2 (strong): 824 — 7%

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

## Dependency Chain (thứ tự bắt buộc)

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
6. Train MLP Reranker (train_reranker.py — cần GNN embeddings + labeled pairs)
        ↓
7. Stage 2 inference hoạt động (patch checkpoint nếu cần)
```

**Checkpoint patch:** nếu thay đổi DB data (seniority, skills) mà không retrain, cần patch `checkpoints/<name>/jobs.json` thủ công vì engine đọc từ file, không từ DB trực tiếp.

---

## Những gì KHÔNG làm

- **Không dùng Word2Vec hay TF-IDF** — dùng SentenceTransformers (tốt hơn nhiều)
- **Không label thủ công** — dùng LLM auto-label
- **Không hardcode trọng số final ranking** — MLP học từ data
- **Không include HR/PM CVs** — tập trung dev roles (AI/SE/DevOps/QA/UX)
- **Không cosine similarity đơn thuần** — 2-stage: GNN + MLP reranker
- **Không infer skills từ job title** — LLM CV parser chỉ lấy skills được mention explicitly

---

## Kết quả hiện tại (Week 11)

| Metric | Giá trị |
|--------|---------|
| GNN Test AUC-ROC | **0.876** |
| GNN NDCG@5 | 1.000 |
| GNN MRR | 1.000 |
| Labeled pairs | 11,611 |
| CVs / Jobs trong checkpoint | 364 / 6,251 |
| Reranker | MLP ordinal 3-class, 23 features |
| Calibration | a=1.016, b=−1.078 |

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
| **Week 11** | **0.876** | **11,611** | **Ordinal 3-class MLP** | 23 features, intern fix |
