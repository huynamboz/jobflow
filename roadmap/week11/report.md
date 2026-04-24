# Week 11 — Report (2026-04-24)

Checkpoint hoạt động: `checkpoints/gnn_v2/`  
Dataset: `data/processed/b89_full` (11,565 pairs, 33% positive)

---

## Tóm tắt kết quả

| Metric | Week 10 (v2) | Week 11 (gnn_v2) | Thay đổi |
|--------|-------------|-----------------|---------|
| GNN Test AUC-ROC | 0.786 | **0.876** | **+0.090** |
| GNN NDCG@5 | — | **1.000** | — |
| Reranker | Binary BCE | **Ordinal 3-class** | Upgrade |
| Reranker accuracy | 81.2% | 81.2%* | Maintained |
| Feature count | 20 | **23** | +3 features |
| Role inference | 45% | **54%** | +9% |
| Intern in Senior top-10 | ✗ (bug) | **✓ Fixed** | Fixed |
| CV parser | Rule-based | **LLM** | Upgrade |

*Reranker retrained với ordinal loss — accuracy metric sama nhưng ranking order cải thiện.

---

## 1. Ordinal 3-class Reranker

**Vấn đề:** Binary reranker (BCE loss) chỉ phân biệt fit/not-fit nhưng không phân biệt "phù hợp" vs "rất phù hợp" → ranking order trong top-K kém.

**Fix:** Đổi từ `BCEWithLogitsLoss` → `CrossEntropyLoss` với 3 classes (0=no fit, 1=suitable, 2=strong fit).

```
Score = E[class] = (0×p₀ + 1×p₁ + 2×p₂) / 2  →  continuous [0, 1]
```

**Kết quả:** Model giờ phân biệt "có thể match" vs "match tốt", cải thiện ranking order trong top-10.

Label mapping từ dataset `overall` field:
- `0` (not fit) → class 0
- `1` (suitable) → class 1  
- `2` (strongly suitable) → class 2

**Files:**
- `backend/ml_service/reranker/ranker.py` — `OrdinalReranker` class, `CrossEntropyLoss`
- `backend/train_reranker.py` — thêm `--ordinal` flag

---

## 2. Bổ sung 3 features mới vào FeatureExtractor (20 → 23)

**Vấn đề:** Các features cũ không capture được skill coverage ratio, experience gap chính xác, và role category match trực tiếp.

### Feature 21: `skill_coverage_ratio`
```python
skill_coverage = matched_count / max(total_job_skills, 1)
```
Khác với Jaccard: chỉ tính tỷ lệ job skills được cover bởi CV, không normalize theo union.

### Feature 22: `experience_gap`
```python
raw_gap = cv.experience_years - job.experience_min
experience_gap = max(-5.0, min(10.0, raw_gap)) / 10.0  # →  [-0.5, 1.0]
```
- Dương = over-qualified, âm = under-qualified
- Neutral (0.0) nếu job không specify experience_min

### Feature 23: `role_category_match`
```python
role_category_match = 1.0 if infer_role(cv) == job.role_category else 0.0
# 0.5 nếu job.role_category unknown → neutral
```
Dùng label trực tiếp từ JD extraction thay vì infer cả hai phía → reliable hơn.

**File:** `backend/ml_service/reranker/features.py`

---

## 3. Fix role inference — 45% → 54%

**Vấn đề:** `infer_role()` chỉ đọc job title → nhiều titles ngắn/generic như "Software Engineer" → trả về `other` (45% coverage).

**Fix:** Fallback sang `combined_text` (full JD text) khi title cho ra `other`:

```python
# generate_pairs.py
role = infer_role(skills, title)
if role == "other":
    role = infer_role(skills, combined_text)  # fallback to full text
```

**Kết quả:** `other` rate giảm từ 55% → 46%, role coverage tăng 45% → 54%.

**File:** `backend/apps/labeling/management/commands/generate_pairs.py`

---

## 4. LLM CV Parser — thay thế rule-based

**Vấn đề:** `CVParser` dùng regex không extract được skills từ text tự do; nhiều CVs trả về empty skills list, làm matching chất lượng kém.

**Fix:** `LLMCVParser` dùng `llm_cv_extractor.extract()` — gọi LLM với `cv_extraction.md` prompt, trả về `CVData` với canonical skill identifiers, seniority, experience_years.

**Đồng thời hardening prompt `cv_extraction.md`:**
```
Extract ONLY skills explicitly mentioned in the CV text.
Do NOT infer or add skills based on job title, role, or context.
```
→ Loại bỏ non-determinism: 3/3 lần chạy cùng CV trả về kết quả giống nhau (trước: 7/9/10 skills).

**File:** `backend/apps/matching/services/llm_cv_parser.py`

---

## 5. Fix seniority mislabeling — Intern jobs lọt vào Senior ranking

### Root cause analysis

**Triệu chứng:** Senior Backend CV (seniority=3) → top results chứa "Co-op/Intern DevOps" job.

**Expected behavior:** `edge_penalty=1.0` khi `cv_level >= 3 and job_level <= 1` → reranker downrank mạnh.

**Root cause:** 574/579 intern-titled jobs có `seniority=2 (Mid)` trong DB do LLM extractor đọc skill complexity (Docker, CI/CD) và assign Mid-level thay vì đọc title. Vì `job_level=2`, condition `job_level <= 1` không trigger → `edge_penalty=0`.

### Fix: 3 lớp

**Lớp 1 — JD extraction prompt** (`backend/apps/jobs/prompts/jd_extraction.md`):
```
IMPORTANT — Title override rule:
If the job title contains any of these words (case-insensitive):
intern, internship, fresher, trainee, co-op, thực tập
→ MUST set seniority=0, regardless of skills or experience listed.
The title takes absolute priority over description content.
```

**Lớp 2 — DB relabeling** (Django ORM):
```python
to_fix = Job.objects.filter(title__iregex=r'\b(intern|co-op|fresher|trainee|thực tập)\b', seniority__gt=0)
updated = to_fix.update(seniority=0)
# Result: 574 jobs relabeled
```

**Lớp 3 — Checkpoint patch** (quan trọng nhất — engine đọc từ checkpoint, không từ DB):
```python
# patch gnn_v2/jobs.json bằng cách lookup JDExtractionRecord.result['title']
for job in ckpt_jobs:
    title = jd_map[job['job_id']].lower()
    if any(kw in title for kw in INTERN_KEYWORDS):
        job['seniority'] = 0  # patch in-place
# Result: 515 jobs patched in checkpoint
```

**Kết quả:**
- Senior Frontend (5yr): 0 intern jobs in top 15 ✓
- Senior Backend (6yr): Co-op/Intern DevOps gone từ rank 6 ✓
- Senior QA (5yr): 0 intern jobs ✓

---

## 6. Hard negative mining pipeline

**Mục tiêu:** Tạo training pairs "model nghĩ match nhưng thực ra không" để cải thiện decision boundary.

**Chiến lược:**
- CV × Job pairs với Stage-1 score ≥ 0.50 (model confused)
- Nhưng skill Jaccard < 0.35 (thực ra ít overlap)
- Chưa được label trong DB hoặc dataset files

```bash
python mine_hard_negatives.py --n 2000 --threshold 0.50 --max-overlap 0.35
python manage.py add_hard_neg_pairs --clear-pending
# → Insert PENDING pairs vào PairQueue để LLM label tiếp
```

**Files:**
- `backend/mine_hard_negatives.py`
- `backend/apps/labeling/management/commands/add_hard_neg_pairs.py`

---

## 7. Experience mismatch tooling

### generate_exp_negatives.py
Tạo synthetic negative pairs khi cv_exp << job_exp_min (unambiguous mismatch, không cần LLM label):

```python
EXP_GAP_THRESHOLD = 0.65   # cv_exp < 65% job_exp_min → clear mismatch
MIN_JOB_EXP = 3.0          # chỉ target jobs yêu cầu ≥3 năm
```

Labels được tự động assign:
- `overall = 0`, `experience_fit = 0`
- `skill_fit` = computed từ Jaccard (không mask)
- `seniority_fit`, `domain_fit` = -1 (masked)

### relabel_experience.py
Programmatic relabeling pairs noisy trong dataset (human labeler lenient):

```python
EXP_FIT_THRESHOLD = 0.70   # cv_exp < 70% job_exp_min → experience_fit=0
OVERALL_THRESHOLD = 0.65   # cv_exp < 65% job_exp_min → overall=0
```

---

## 8. BGE-small embedding provider (sẵn sàng, chưa activate)

**Upgrade từ:** `all-MiniLM-L6-v2` (56 MTEB) → `BAAI/bge-small-en-v1.5` (62 MTEB, cùng 384 dim — drop-in).

```python
EMBEDDING_PROVIDER = "bge-small"  # để activate
```

**Chưa activate** — gain kỳ vọng +0.01 AUC không đủ justify full retrain. Sẽ activate khi có lý do retrain lần sau.

**File:** `backend/ml_service/embedding/bge.py`

---

## 9. match_level — Giải thích kết quả cho user

**Mới:** API response giờ có `match_level` trên mỗi job kết quả:

```
score ≥ 0.65           → "strong"
0.45 ≤ score < 0.65    → "good"
0.30 ≤ score < 0.45    → "moderate"
score < 0.30            → "weak"
```

Và `dim_scores` cho 4 chiều: `skill_fit`, `experience_fit`, `seniority_fit`, `domain_fit`.

**Files:**
- `backend/apps/matching/services/matching_service.py`
- `backend/apps/matching/serializers.py`
- Admin UI: badge màu sắc theo match_level

---

## Ranking quality — kết quả thực tế

| CV Profile | Score range | Intern issue | Quality |
|------------|-------------|-------------|---------|
| Junior Frontend (2yr, seniority=1) | 0.77–0.80 | OK (Junior→Intern diff=1) | Good |
| Senior Frontend (5yr) | 0.80–0.94 | 0 intern ✓ | Excellent |
| Senior Backend (6yr) | 0.41–0.55 | 0 intern ✓ | Medium* |
| Senior QA (5yr) | 0.65–0.76 | 0 intern ✓ | Excellent |
| Data Scientist (3yr) | 0.44–0.54 | 0 intern ✓ | Weak* |

*Chất lượng thấp do thiếu training data (Backend: 373 jobs, Data ML: 515 jobs so với Frontend: 746). Đây là vấn đề data distribution, không phải model bug.

**Job distribution trong DB:**
```
other    2,749  (PM, Scrum Master, etc.)
fullstack  868
frontend   746  ← đủ data → ranking tốt
qa         630  ← đủ data → ranking tốt
data_ml    515  ← medium
devops     492
backend    373  ← thiếu → ranking noisy
design     252
ba         216
mobile     149  ← rất thiếu
data_eng   147  ← rất thiếu
```

---

## GNN v2 — Checkpoint metrics

| Metric | Giá trị |
|--------|---------|
| Dataset | b89_full (11,565 pairs) |
| CVs / Jobs | 364 / 6,251 |
| Best epoch | 299 |
| Test AUC-ROC | **0.876** |
| Precision@5 | 1.000 |
| NDCG@5 | 1.000 |
| Recall@5 | 0.009* |
| MRR | 1.000 |
| Reranker | Ordinal 3-class, 23 features |
| Calibration | a=1.016, b=−1.078 |

*Recall@5 thấp vì mỗi CV có nhiều positive jobs trong DB nhưng test chỉ đánh giá top-5 retrieval.

---

## Kết quả tổng hợp qua các tuần

| Tuần | AUC-ROC | Labels | Reranker | Highlights |
|------|---------|--------|----------|------------|
| Week 1 | 0.550 | ~2,000 | Không có | Baseline |
| Week 2 | 0.712 | 9,889 | Rule-based | Real data |
| Week 9 | 0.701 | 9,889 | Rule-based | Fix training |
| Week 10 (b89) | 0.790 | 5,206 | Binary BCE | LLM labels |
| Week 10 (v2) | 0.786 | 11,565 | Binary BCE 81.2% | Dataset cân bằng |
| **Week 11 (gnn_v2)** | **0.876** | **11,565** | **Ordinal 3-class** | **Intern fix, 23 features** |

---

## Next steps

1. **Thêm training data cho Backend/Mobile/DataEng** — crawl thêm jobs, đặc biệt các domain ít data
2. **Label hard negatives** — 2000 candidates đã được mine, cần LLM label để đưa vào training
3. **Retrain GNN + Reranker với hard negatives** — sau khi có labeled data
4. **Activate BGE-small** — nếu retraining vì lý do khác, kết hợp luôn embedding upgrade
5. **Experience gap feature** — validate feature 22 có improve ranking cho under-qualified cases không
6. **Real user feedback** — click/apply signal để break ceiling ~0.88 của LLM-only labels
