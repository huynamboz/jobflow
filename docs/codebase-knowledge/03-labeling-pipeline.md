# Labeling Pipeline (LLM-based)

Pipeline tạo ground truth cho training. **100% nhãn do LLM chấm** (`HumanLabel.labeled_by=None` toàn bộ), con người chỉ vận hành batch. Đây là nơi "định nghĩa thế nào là match" được mã hoá — chất lượng mọi thứ downstream (GNN, reranker, tuning) phụ thuộc vào đây.

## Sơ đồ

```
CV (apps/cvs) + JDExtractionRecord (apps/jobs)
   │  generate_pairs.py  (chọn cặp đáng label — role-aware)
   ▼
LabelingCV / LabelingJob / PairQueue   (snapshot + hàng đợi cặp, split 70/15/15 gán sẵn)
   │  LabelingBatch (admin UI POST /api/admin/labeling/batches/, 3-20 worker threads)
   │  → label_batch_processor._label_one → llm_label_extractor.extract_label
   │  → LLMService.complete(temperature=0, prompt=pair_scoring.md)
   ▼
HumanLabel  (skill_fit/seniority_fit/experience_fit/domain_fit/overall — mỗi cái 0/1/2)
   │  export_dataset.py --batches 6 8 9 10
   ▼
data/processed/b89_full  (labels.json: binary label = 0 nếu overall==0 else 1, + 4 dims)
   │  run_train_save.py
   ▼
checkpoints/latest  (GNN + reranker)
```

## Các model (apps/labeling/models.py)

| Model | Vai trò | Field chính |
|---|---|---|
| `LabelingCV` (L4) | snapshot CV | cv_id→CV.id, role_category, skills[{name,proficiency}], seniority, experience_years, text_summary(600c), pdf_path |
| `LabelingJob` (L23) | snapshot job | job_id→**JDExtractionRecord.id**, title, role_category (suy từ title/text), skills[{name,importance}], seniority, exp/salary min-max |
| `PairQueue` (L92) | hàng đợi cặp | skill_overlap_score (Jaccard), bm25_score, selection_reason, priority, status (pending/labeled/skipped), **split (train/val/test gán lúc sinh cặp)**, unique(cv,job) |
| `LabelingBatch` (L43) | run LLM | status running/done/error/cancelled, total/done_count/error_count, workers |
| `HumanLabel` (L124) | nhãn | 4 dim (0/1/2) + `overall` (0/1/2) + note + labeled_by(None=LLM); `binary_label` = 1 nếu overall≥1 |

## Chọn cặp — `generate_pairs.py`

- Nguồn: CV `is_active=True` (≥3 skills), JDExtractionRecord `status=done` (≥3 skills). Role job suy từ **title rules → text fallback** (L62-73).
- **Role-aware selection** (L245-266): nếu role CV ↔ role job **tương thích** (cùng role hoặc trong `RELATED_ROLES`: backend↔fullstack, frontend↔fullstack, data_ml↔data_eng):
  - overlap ≥ 0.20 → HIGH_OVERLAP · ≥ 0.08 → MEDIUM_OVERLAP · < 0.08 → HARD_NEGATIVE
  - role **không tương thích** → RANDOM
- **Tỉ lệ lấy mẫu** (L275-280): HIGH 30% · MEDIUM 40% · HARD_NEG 20% · **RANDOM (cross-domain) chỉ 10%**
- Split 70/15/15 gán ngẫu nhiên **theo cặp ngay lúc sinh** (L300-305).
- Priority label: MEDIUM(1) < HIGH(2) < HARD_NEG(3) < RANDOM(4).

⚠️ **Hệ quả thiết kế**: cặp "skill cao × khác nghề" (hard cross-domain negative — pattern bug Compositor) gần như không được chọn — bucket RANDOM 10% là cross-domain nhưng phần lớn overlap thấp (negative dễ). Xem [04-label-data-analysis.md](04-label-data-analysis.md): slice này chỉ 2% tập nhãn.

## LLM chấm — `prompts/pair_scoring.md` + `llm_label_extractor.py`

- Vai: "HR recruiter". Input: CV (role, seniority, exp, top-15 skills, text 5000c) × Job (title, role, seniority, skills required/nice-to-have, JD 5000c). `temperature=0`, max_tokens=256, feature="pair_scoring" (log vào LLMCallLog).
- Output JSON 5 điểm 0/1/2. **Rules trong prompt**:
  - `skill_fit`: % required skills phủ — 0: <30% · 1: 30-70% · 2: >70%
  - `seniority_fit`: lệch ≥2 → 0 · lệch 1 → 1 · khớp/trên 1 → 2
  - `experience_fit`: <50% min → 0 · 50-90% → 1 · đủ/không yêu cầu → 2
  - `domain_fit`: **bảng cứng** — cùng nghề → 2 · related (fullstack↔BE/FE, data_ml↔data_eng) → 1 · khác → 0
  - `overall` (rule cứng): skill=0 → 0 · skill=1 & domain=0 → 0 · skill=2 & domain≥1 & seniority≥1 → 2 · skill=1 & domain≥1 → 1 · **còn lại: "judgment call"**

⚠️ **LỖ HỔNG PROMPT** (nguồn nhiễu đã đo được): rule overall **không phủ case `skill_fit=2 & domain_fit=0`** → rơi vào "judgment call" → LLM chấm tuỳ hứng: thực tế 100/232 cặp slice này bị chấm overall=1 (phù hợp dù khác nghề). Fix một dòng prompt: `skill=2 & domain=0 → overall=0` (hoặc tối đa 1) sẽ khử nhiễu này.

## Batch processor — `services/label_batch_processor.py`

- 1 batch = 1 daemon thread + ThreadPool N workers (mặc định 3, max 20), chunk = 2×workers (L132-223).
- `_label_one` (L82): load **full text** từ CV.parsed_text / JDExtractionRecord.combined_text (không dùng summary 600c) → `extract_label` → tạo HumanLabel + pair.status=LABELED.
- Cancel qua cancel_event; resume được batch ERROR/CANCELLED (re-fetch pending).
- Admin UI: list/detail/cancel/resume tại `/api/admin/labeling/batches/`.

## Export — `export_dataset.py`

- `--batches 6 8 9 10` → chỉ lấy nhãn các batch đó (= dataset `b89_full` của checkpoint production).
- Filter: CV/job < min skills (mặc định 2) bị loại; skill ngoài catalog bị bỏ.
- **Map nhãn**: `binary_label = 0 if overall==0 else 1` (overall 1 và 2 đều thành positive).
- Xuất: cvs.json, jobs.json, skills.json, cv_skills.json, job_skills.json, labels.json (kèm 4 dims + split), metadata.json.
- Text xuất là **full text** (parsed_text/combined_text), không phải summary.

## API labeling (người dùng — ít dùng vì LLM label hết)

`/api/labeling/queue/` (CV pending + pairs) · `/{pair_id}/submit/` · `/{pair_id}/skip/` · `/stats/` · `/export/` · `/cvs/{id}/pdf/`

## Trạng thái data hiện tại (2026-06-10)

11.611 nhãn LLM / 8.617 cặp labeled / 365 CV × 6.251 job. Batch có nhãn: 6 (3.499), 7 (56), 8 (3.031), 9 (4.950), 10 (75). Chi tiết phân phối + crosstab: [04-label-data-analysis.md](04-label-data-analysis.md).
