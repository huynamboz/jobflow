# Week 10 — Data Pipeline: Chuẩn bị dữ liệu training

> **Mục tiêu:** Có đủ dữ liệu sạch, nhất quán, và đủ labels để train GNN đạt kết quả tốt hơn baseline Week 9 (AUC-ROC 0.71).
>
> **Trạng thái đầu tuần:**
> - JD batch extraction: ✅ done (pipeline clean, skill canonical, importance chuẩn)
> - CV batch extraction: ✅ backend + frontend done, **chưa chạy**
> - PairQueue: 300 pairs (299 pending, 1 labeled) — quá ít để train
> - HumanLabel: 1 record — cần LLM auto-label toàn bộ queue
> - Labeled pairs cuối Week 9: ~9,889 (proxy labels từ skill-overlap)
>
> **⚠️ Blockers phát hiện:**
> - 365/365 CVs có `role_category = "other"` — field mới thêm, chưa extract lại
> - 64% CVs (233/365) có `seniority = Mid (2)` — nghi ngờ là default, chưa extract lại
> - `skill_proficiency = 3` cho toàn bộ skills — không có variation, vô dụng làm feature
> - Dataset LinkedIn có HR (115) + PM (105) + BA (76) CVs không có JD matching trong IT dataset
> → **Pair generation không thể hoạt động đúng** cho đến khi CV batch extraction hoàn thành.
>
> **Quyết định scope:** Tập trung vào **dev roles** — giữ AI/Software Engineer/Devops/Tester/UX_UI, bỏ HR/PM/BA.
> LLM extract `role_category` từ text thực tế thay vì dùng folder name dataset.

---

## Task 1 — Re-run JD extraction batch trên toàn bộ jobs ✅ (user tự chạy)

**Mục tiêu:** Thay thế toàn bộ `result` trong `JDExtractionRecord` bằng format mới (có `is_remote`, `role_category`, `salary_usd_annual_*`, importance scale đã fix).

**Output:** Export JSON file từ admin UI → dùng làm input cho graph builder.

**Format export mỗi record:**
```json
{
  "job_id": 45,
  "title": "Senior Frontend Developer",
  "role_category": "frontend",
  "seniority": 3,
  "is_remote": false,
  "salary_usd_annual_min": 0,
  "salary_usd_annual_max": 0,
  "experience_min": 5.0,
  "experience_max": null,
  "degree_requirement": 3,
  "skills": [
    { "name": "react", "importance": 5 },
    { "name": "typescript", "importance": 4 }
  ]
}
```

**Verify sau khi chạy:**
- Tất cả records có `role_category` != null
- Importance distribution: không có record nào với >30% skills ở importance=5
- Skill names đều là canonical identifiers

---

## Task 2 — CV Batch Extraction ✅ (backend + frontend done)

**Lý do:** CV hiện tại chưa có pipeline xử lý hàng loạt. Cần extract structured data (skills, seniority, role_category, experience_years) từ tất cả CVs.

**Đã build:**
- `CVExtractionBatch` + `CVExtractionRecord` models + migration
- `cv_batch_processor.py` — background thread, cancel support, progress tracking
- Admin views: list, detail, record detail (raw_text + result), cancel
- Frontend: `/admin/cv-batch` — overview + detail với HeroUI Modal 2 cột (raw text | extracted)

**Cần chạy:**
- Tạo batch với categories: AI, Devops, Software Engineer, Tester, UX_UI (~338 CVs)
- Verify distribution sau khi xong: `role_category` không còn "other" chiếm đa số

**Verify sau khi chạy:**
- `role_category` distribution: backend/frontend/fullstack/data_ml hợp lý
- Skills: canonical names, proficiency 1–5 có variation
- `experience_years` vs `seniority` không có contradiction

---

## Task 3 — Build LLM Labeling Pipeline

**Lý do:** 300 pairs hiện tại quá ít. Cần auto-label bằng LLM.

**Chi phí LLM:** ~150đ/1M tokens. 3,500 pairs × 5,000 tokens = ~17.5M tokens ≈ **2,600đ — gần như free**.
→ Cost không phải bottleneck. Bottleneck là CV batch phải xong trước để có `role_category` đúng.

### 3.1. Prompt: `backend/apps/labeling/prompts/pair_scoring.md`

Input: CV summary + skills + seniority / Job summary + skills + seniority

Output format:
```json
{
  "skill_fit": 2,
  "seniority_fit": 1,
  "experience_fit": 2,
  "domain_fit": 2,
  "overall": 1
}
```

Scale cho mỗi dimension:
- `skill_fit`: 0 = CV thiếu >50% required skills, 1 = có 30–70%, 2 = có >70%
- `seniority_fit`: 0 = lệch ≥2 bậc, 1 = lệch 1 bậc, 2 = khớp hoặc CV cao hơn 1 bậc
- `experience_fit`: 0 = exp_years < 50% job yêu cầu, 1 = đạt 50–90%, 2 = đạt >90%
- `domain_fit`: 0 = khác role_category, 1 = liên quan (fullstack↔backend), 2 = khớp chính xác
- `overall`: 0 = không phù hợp, 1 = phù hợp, 2 = rất phù hợp

### 3.2. `backend/apps/labeling/services/llm_label_extractor.py`

```python
@dataclass
class LabelResult:
    skill_fit: int = 0       # 0/1/2
    seniority_fit: int = 0
    experience_fit: int = 0
    domain_fit: int = 0
    overall: int = 0

def extract_label(cv_summary, cv_skills, cv_seniority,
                  job_summary, job_skills, job_seniority) -> LabelResult: ...
```

### 3.3. `backend/apps/labeling/services/label_batch_processor.py`

- Đọc `PairQueue` pending theo priority: high_overlap → medium → hard_negative → random
- Gọi `extract_label()` cho mỗi pair
- Tạo `HumanLabel` với `labeled_by=None` (system label)
- Update `PairQueue.status = "labeled"`

### 3.4. Admin endpoints + frontend monitor
- `POST /api/admin/labeling/batches/` — start labeling batch
- `GET /api/admin/labeling/batches/:id/` — progress
- Frontend `/admin/labeling` — monitor progress

---

## Task 4 — Generate thêm PairQueue pairs

**Lý do:** 300 pairs quá ít. Cần ít nhất 3,000–5,000 pairs.

**Strategy:**

| Selection reason | Số lượng | Cách generate |
|-----------------|----------|---------------|
| `high_overlap` | 500 | Skill Jaccard ≥ 0.5 + same role_category |
| `medium_overlap` | 1,500 | Skill Jaccard 0.2–0.5 + same/related role_category |
| `hard_negative` | 1,000 | Same role_category nhưng Jaccard < 0.1 |
| `random` | 500 | Random across all CVs × Jobs |
| **Total** | **3,500** | |

**Script:** `python manage.py generate_pairs --high=500 --medium=1500 --hard=1000 --random=500`

---

## Task 5 — Export Training Dataset

**Script:** `python export_dataset.py --output data/processed/v2/`

**Output:**
```
data/processed/v2/
├── jobs.json       # Job nodes + features
├── cvs.json        # CV nodes + features
├── skills.json     # Skill nodes
├── job_skills.json # Edges: job_id, skill_name, importance
├── cv_skills.json  # Edges: cv_id, skill_name, proficiency
├── labels.json     # (cv_id, job_id, overall, skill_fit, seniority_fit, ...)
└── metadata.json   # counts, split sizes
```

---

## Task 6 — Train XGBoost Reranker

> **Quan trọng — đây là mục tiêu cuối cùng của toàn bộ pipeline.**

**Lý do cần labeled pairs:**
- Hệ thống có 2 stage:
  - **Stage 1 (Retrieve):** `0.55 × GNN + 0.30 × skill_overlap + 0.15 × seniority` — trọng số **hardcode**, chỉ lọc top 50
  - **Stage 2 (Rerank):** XGBoost với 20 features — trọng số **học từ data**, quyết định thứ tự cuối
- Nếu không có labeled pairs → Stage 2 bị skip → hệ thống chỉ dùng Stage 1 hardcode

**Flow train reranker:**
```
labeled pairs (cv_id, job_id, overall 0/1/2)
    ↓
FeatureExtractor.extract(cv, job) → 20-dim vector
    ↓
XGBoost.fit(X, y) → model.pt
    ↓
Stage 2 hoạt động → ranking chính xác
```

**Target sau train:** AUC-ROC > 0.71 (baseline Week 9)

---

## Task 7 — Data Quality Validation

**Các check cần pass trước khi train:**

```
# Skill coverage
% jobs có ≥ 5 skills → cần ≥ 90%
% cvs có ≥ 3 skills → cần ≥ 85%

# Label distribution
overall=0: 40–50%
overall=1: 30–40%
overall=2: 10–20%

# Role coverage
≥ 5 CV categories, tất cả 11 job categories đều có ≥ 10 jobs
```

---

## Thứ tự thực hiện

```
[HIỆN TẠI] CV batch extraction (fix role_category + seniority + skills)
    ↓
JD re-run (song song hoặc sau)
    ↓
Generate pairs từ data sạch (role_category đúng)
    ↓
LLM label pairs (~2,600đ cho 3,500 pairs)
    ↓
Export dataset → Train GNN + XGBoost reranker
    ↓
AUC-ROC > 0.71
```

---

## Điều kiện "Done" của Week 10

| Checkpoint | Target |
|-----------|--------|
| CV extraction | ≥ 300 CVs có structured data (skills, role_category, seniority) |
| JD extraction re-run | ≥ 4,000 jobs có result với format mới |
| LLM-labeled pairs | ≥ 3,000 HumanLabel records |
| Label balance | positive rate (overall ≥ 1) trong khoảng 40–60% |
| Dataset export | v2/ folder đủ 7 files, pass validate checks |
| Training test run | GNN + reranker train không crash, AUC-ROC > 0.71 |

---

## Rủi ro

| Rủi ro | Mitigation |
|--------|-----------|
| LLM labeling bias (luôn cho overall=1) | Kiểm tra distribution sau 50 labels đầu |
| CV extraction chất lượng thấp | Verify 20 CVs random bằng tay qua modal detail |
| Quá ít high_overlap pairs | Hạ threshold Jaccard xuống 0.3 |
| Export dataset chậm | Precompute text embeddings 1 lần, cache vào file |
