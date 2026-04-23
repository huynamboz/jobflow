# Week 10 — Findings & Report

## Overview

Mục tiêu week 10: thay thế proxy labels (rule-based skill overlap từ Week 9) bằng **LLM human labels** để cải thiện chất lượng training signal. Pipeline đầy đủ được thiết kế tại [`plan/data-pipeline.md`](plan/data-pipeline.md).

**Kết quả:**
- AUC-ROC: **0.790** — tốt nhất từ trước đến nay (+11% vs Week 9 baseline 0.714)
- 5,206 LLM-labeled pairs (batch 8 + 9), positive rate 61.8%
- Checkpoint saved: `checkpoints/week10-b89-auc0790/`

---

## Kết quả so sánh qua các tuần

| Tuần | AUC-ROC | Labels | Loại label | Ghi chú |
|------|---------|--------|-----------|---------|
| Week 1 | 0.550 | ~2,000 | Synthetic | Dữ liệu giả, baseline đầu tiên |
| Week 2 | 0.712 | 9,889 | Rule-based (Jaccard overlap) | Real data, 5 critical fixes |
| Week 3 | 0.714 | 9,889 | Rule-based | Revert education feature |
| Week 9 | 0.701 | 9,889 | Rule-based | Fix early stopping bug |
| **Week 10** | **0.790** | **5,206** | **LLM labels** | **Best ever (+11% vs W9)** |

Cải thiện đến từ **chất lượng label**, không phải số lượng. 5,206 LLM labels đã bù đắp được 9,889 proxy labels.

---

## Pipeline Week 10

Toàn bộ pipeline được thiết kế trước tại [`plan/data-pipeline.md`](plan/data-pipeline.md). Dưới đây là các tasks đã thực hiện:

### Task 1 — JD Re-extraction

Re-run toàn bộ JD extraction với format mới: canonical skill names, importance scale chuẩn, `role_category` từ LLM thay vì heuristic. Output: `JDExtractionRecord.result` được cập nhật cho tất cả records.

**Verify:**
- Skill names: canonical identifiers (không còn free-text)
- Importance: scale 1–5, distribution hợp lý (không phải tất cả = 5)
- `role_category`: phân loại đúng thay vì default "other"

### Task 2 — CV Batch Extraction

Build pipeline extract structured data từ CV text:
- **Backend:** `CVExtractionBatch` + `CVExtractionRecord` models, `cv_batch_processor.py` (background thread, cancel support)
- **Frontend:** `/admin/cv-batch` với HeroUI modal 2 cột (raw text | extracted result)
- **Fix role inference:** fallback to `combined_text` khi title-only cho `role_category = "other"` → tỉ lệ phân loại đúng từ 45% → 54%

### Task 3 — Jobs Deduplication (`rebuild_jobs`)

Phát hiện 4,769 jobs có 386 unique LinkedIn IDs → tỉ lệ duplicate 12x. Xây dựng management command `rebuild_jobs`:

1. **Dedup:** extract LinkedIn job ID từ URL bằng regex (`/jobs/view/ID/`), giữ job có nhiều skills nhất, xóa duplicates (–4,383 records)
2. **Apply extractions:** map `JDExtractionRecord` → `Job` qua URL key, cập nhật fields từ extraction result (+318 jobs)
3. **Import new:** tạo `Job` mới từ extraction records chưa có match (+6,749 jobs)

```python
def _url_key(url: str) -> str | None:
    m = re.search(r"/jobs/view/(\d+)", url or "")
    return m.group(1) if m else None
```

### Task 4 — Pair Generation

Generate `PairQueue` với stratified sampling:

| Strategy | Mục đích |
|----------|----------|
| `high_overlap` | Pairs nhiều khả năng phù hợp (Jaccard cao, cùng role) |
| `medium_overlap` | Ambiguous cases — training signal giá trị nhất |
| `hard_negative` | Cùng role nhưng skills rất khác — phân biệt khó |
| `random` | Tránh bias, đảm bảo coverage |

**Fix bug:** `generate_pairs` thu thập tất cả compatible pairs trước khi áp dụng `max_per_cv` cap, tránh bias CV đầu tiên được quá nhiều pairs.

### Task 5 — LLM Labeling Pipeline

Build từ đầu:

**`llm_label_extractor.py`** — gọi Claude API với prompt 4 dimensions:

```
skill_fit:       0 = thiếu >50% required skills / 1 = có 30–70% / 2 = có >70%
seniority_fit:   0 = lệch ≥2 bậc / 1 = lệch 1 bậc / 2 = khớp hoặc CV cao hơn
experience_fit:  0 = exp < 50% yêu cầu / 1 = đạt 50–90% / 2 = đạt >90%
domain_fit:      0 = khác role_category / 1 = liên quan / 2 = khớp chính xác
overall:         0 = không phù hợp / 1 = phù hợp / 2 = rất phù hợp
```

**`label_batch_processor.py`** — background `ThreadPoolExecutor` (3 workers):
- Đọc `PairQueue` pending theo priority
- Gọi `extract_label()` parallel
- Tạo `HumanLabel` records, update `PairQueue.status`
- Progress tracking qua `LabelingBatch.done_count`

**Frontend:** `/admin/label-batch` — monitor progress realtime, start/cancel batch

### Task 6 — Bug Fixes Critical

**Bug 1: `django.setup()` trong background thread**

```
Triệu chứng: batch luôn error ngay khi start
Root cause: _run() gọi django.setup() → trigger AppConfig.ready() → reset
            LabelingBatch đang chạy về status="cancelled"
Fix: xóa django.setup() khỏi _run() — Django đã initialized bởi web server
```

**Bug 2: `LabelingBatch.total` mismatch khi resume**

```
Triệu chứng: done_count vượt quá total, UI hiện sai progress
Root cause: khi restart, _run() ghi total = len(pending_ids) — không tính
            labels đã tạo từ lần chạy trước
Fix: sync cả hai counter khi batch start:
    already_done = HumanLabel.objects.filter(batch_id=batch_id).count()
    total = already_done + len(pending_ids)
    done_count = already_done
```

### Task 7 — Export & Train

```bash
python export_dataset.py --output data/processed/b89 --batches 8 9
python run_train_save.py --data data/processed/b89
```

Dataset: 364 CVs, 6,251 Jobs, 218 Skills, 5,206 pairs (3,666/779/761 split)

---

## Training Results

| Metric | Giá trị |
|--------|---------|
| Best epoch | 25 / 105 (early stop) |
| Final train loss | 0.212 |
| Val AUC (peak) | 0.795 |
| **Test AUC-ROC** | **0.790** |
| Precision@10 | 1.000 |
| NDCG@10 | 1.000 |
| MRR | 1.000 |
| Training time | 153.6s |

**Lưu ý về Precision@K / NDCG / MRR = 1.0:** Test set có rất ít labeled pairs per CV (recall@10 = 2.1%) nên model dễ rank các known positives lên đầu. AUC-ROC là metric đáng tin cậy nhất ở đây vì đánh giá khả năng phân biệt trên toàn bộ test set.

---

## Tại sao LLM labels tốt hơn rule-based?

| Khía cạnh | Rule-based (overlap) | LLM labels |
|-----------|---------------------|-----------|
| Skill matching | Jaccard ≥ threshold | Semantic + context-aware |
| Seniority | Không xét | Xét 4 dimensions riêng biệt |
| Domain fit | Không xét | `domain_fit` dimension |
| Experience | Không xét | `experience_fit` dimension |
| False positives | Cao (chỉ dựa skill count) | Thấp (multi-dimensional) |
| Label noise | Có (threshold-based) | Thấp (LLM reasoning) |

Rule-based labels bị **circular bias**: model học từ Jaccard overlap → Stage 1 scoring cũng dùng skill overlap → không thể tách biệt GNN contribution thực sự.

---

## Artifact

| Artifact | Path |
|---------|------|
| Dataset (b89) | `backend/data/processed/b89/` |
| Model checkpoint | `backend/checkpoints/week10-b89-auc0790/` |
| Live checkpoint | `backend/checkpoints/latest/` (symlink equivalent) |

Checkpoint bao gồm: `model.pt` (18MB), `graph.pt` (12MB), `cvs.json` + `jobs.json` (364 CVs + 6,251 Jobs embedded), `reranker.pt`.

---

## Limitations & Next Steps

| Limitation | Impact | Hướng giải quyết |
|-----------|--------|-----------------|
| Chỉ 364 CVs | Generalization hạn chế với CV mới | Crawl thêm CV đa dạng hơn |
| LLM labeling có thể biased | Mô hình học bias của LLM | Thêm human review cho 10% labels |
| Recall@10 thấp (2.1%) | Không đủ positive pairs per CV để đánh giá ranking | Cần nhiều labels per CV hơn |
| `overall=0/1/2` → binary 0/1 | Mất signal "fit mạnh" | Thử ordinal regression hoặc 3-class |

**Priority tiếp theo:**
1. Crawl thêm CVs (đặc biệt Frontend, Backend, Fullstack để balance dataset)
2. Label thêm pairs để có ≥10 positives per CV trong test set
3. Thử dùng `overall` 3-class (0/1/2) thay vì binary để cải thiện ranking quality
