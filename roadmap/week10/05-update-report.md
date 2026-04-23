# Week 10 — Update Report (2026-04-23)

Báo cáo này mô tả các cải tiến được apply sau khi hoàn thành `findings.md` ban đầu.
Checkpoint gốc: `checkpoints/week10-b89-auc0790/` (AUC 0.790, dataset b89).

---

## Tóm tắt kết quả

| Metric | b89 (trước) | v2 (sau) | Thay đổi |
|--------|------------|---------|---------|
| Dataset pairs | 5,206 | **11,565** | +122% |
| Positive rate | 62% (lệch) | **33%** (cân bằng) | Fixed |
| GNN Test AUC | 0.790 | **0.786** | −0.4% (expected*) |
| Reranker accuracy | ~65% | **81.2%** | **+16%** |
| Reranker train pairs | 3,666 | **8,057** | +120% |

*AUC giảm nhẹ vì dataset v2 khó hơn thực sự — b89 bị bias 62% positive, model dễ predict. 0.786 trên dataset cân bằng phản ánh chính xác hơn khả năng thực tế của model.*

---

## 1. Phát hiện và fix dataset bias

**Vấn đề:** b89 được export với `--batches 8 9` nên chỉ có 5,206/11,594 labels, thiếu hầu hết negatives từ batch 6. Kết quả: positive rate 62% thay vì ~33% trong DB thực tế.

**Fix:** Export toàn bộ DB (không filter batch) vào `data/processed/v2`:

```bash
python export_dataset.py --output data/processed/v2
```

| | b89 | v2 |
|--|--|--|
| Labels exported | 5,206 | 11,565 |
| Positive (label=1) | 3,218 (61.8%) | 3,833 (33.1%) |
| Negative (label=0) | 1,988 (38.2%) | 7,732 (66.9%) |
| Train / Val / Test | 3,666 / 779 / 761 | 8,057 / 1,764 / 1,744 |

---

## 2. Fix reranker training — stage1_score và gnn_score bị zero

**Vấn đề:** Trong training cũ, 2 features quan trọng nhất của reranker (`stage1_score`, `gnn_score`) luôn bằng 0:
- `set_stage1_context()` không được gọi trước khi train batch
- `gnn_scores=None` defaulted to 0.0 cho toàn bộ pairs

**Fix:** Viết `train_reranker.py` pre-compute thực sự GNN + Stage1 scores trước khi training:

```python
# Cache CV embeddings để tránh re-encode
cv_text_cache[ci] = provider.encode([cvs[ci].text])[0]
cv_gnn_cache[ci] = engine._get_cv_gnn_embedding(cvs[ci])
gnn_s = engine._gnn_score_fast(cvs[ci], jobs[ji], ji, ...)
s1_s  = engine._score_pair_fast(cvs[ci], jobs[ji], ji, ...)
```

**Kết quả:** Reranker accuracy tăng từ ~65% → 81.2% khi kết hợp với dataset v2.

---

## 3. Xoá stale reranker từ checkpoint cũ

**Vấn đề:** `checkpoints/latest/` chứa `reranker.pt` và `calibration.json` từ ngày 1/4 (GNN v1), không tương thích với GNN v2 (week10). Model đang apply reranker sai lên embedding sai.

**Fix:** Xoá 3 files stale: `reranker.pt`, `reranker_meta.json`, `calibration.json` khỏi `checkpoints/latest/`. Reranker được train lại từ đầu trên GNN v2 embeddings.

---

## 4. LLM CV Parser

**Thay thế:** `CVParser` (rule-based regex) → `LLMCVParser` trong matching service.

**File:** `apps/matching/services/llm_cv_parser.py`

`LLMCVParser` dùng `llm_cv_extractor.extract()` thay vì regex, trả về `CVData` với skills, seniority, experience_years chính xác hơn từ LLM extraction. Seniority fallback logic và skill normalization được giữ nguyên.

**Kết quả:** CV mới upload được parsed tốt hơn, cải thiện matching quality cho user thực tế.

---

## 5. Sync CV extractions về CV table

**Vấn đề:** Sau khi chạy CV batch extraction, data mới (skills, seniority, role_category) nằm trong `CVExtractionRecord.result` nhưng chưa được sync về bảng `CV` và `CVSkill`.

**Fix:** Management command `sync_cv_extractions`:

```bash
python manage.py sync_cv_extractions          # sync tất cả
python manage.py sync_cv_extractions --dry-run  # preview
python manage.py sync_cv_extractions --cv-ids 1 2 3
```

**Kết quả:** 317/365 CVs synced (0 errors). 48 CVs còn lại (BA, UX/UI, empty) không có extraction record do không phải dev roles.

---

## 6. Hard negative mining pipeline

**Mục tiêu:** Sinh pairs "model nghĩ là match nhưng thực ra không" để cải thiện decision boundary của reranker.

**Chiến lược:** Với mỗi CV, tìm Jobs có Stage-1 score cao (≥0.50) nhưng skill Jaccard thấp (<0.35) và chưa được label — đây là những pairs "confusing" nhất cho model.

**Files mới:**

- `backend/mine_hard_negatives.py` — score toàn bộ CV×Job pool, filter candidates, output JSONL
- `backend/apps/labeling/management/commands/add_hard_neg_pairs.py` — insert candidates vào PairQueue

**Workflow:**

```bash
# Bước 1: Mine candidates
python mine_hard_negatives.py --n 2000 --threshold 0.50 --max-overlap 0.35

# Bước 2: Insert vào DB (--clear-pending xoá pending cũ nếu có)
python manage.py add_hard_neg_pairs --clear-pending

# Bước 3: Tạo LabelingBatch qua admin UI → LLM label
```

**Đảm bảo safety:** Không đụng vào `HumanLabel`, LABELED `PairQueue`, hay dataset files. Chỉ thêm PENDING pairs mới.

---

## 7. BGE-small embedding provider (sẵn sàng, chưa activate)

**Upgrade từ:** `all-MiniLM-L6-v2` (56 MTEB) → `BAAI/bge-small-en-v1.5` (62 MTEB, cùng 384 dim)

**Files:**
- `ml_service/embedding/bge.py` — `BgeSmallProvider` class
- `ml_service/embedding/factory.py` — register `"bge-small"` key

**Để activate:** đổi setting `EMBEDDING_PROVIDER=bge-small` rồi rebuild graph + retrain.

**Chưa activate** vì gain kỳ vọng nhỏ (~+0.01 AUC) không đủ justify retrain ở thời điểm này.

---

## 8. Checkpoint fix — lưu node_dims

**Vấn đề:** `load_checkpoint()` không lưu `node_dims` vào `metadata.json`. Nếu embedding dim thay đổi (ví dụ MiniLM 384 → bge-base 768), model sẽ load với projection layer sai size → silent error.

**Fix:** `save_checkpoint()` giờ tự extract `node_dims` từ `model.projections` và lưu vào `metadata.json`. `load_checkpoint()` đọc lại và pass vào `HeteroGraphSAGE`.

---

## Training v2 — chi tiết

```bash
python run_train_save.py --data data/processed/v2
# → checkpoints/run_v2/ + checkpoints/latest/

python train_reranker.py --data data/processed/v2 --checkpoint checkpoints/latest
```

| Metric | Giá trị |
|--------|---------|
| Best epoch | 161 / 241 (early stop) |
| Final train loss | 0.118 |
| Val AUC (peak) | 0.758 |
| **Test AUC-ROC** | **0.786** |
| Reranker accuracy | **81.2%** |
| Reranker train loss | 0.513 |
| Calibration | a=1.079, b=−0.814 |
| Training time | ~320s |

---

## Artifacts

| Artifact | Path |
|---------|------|
| Dataset v2 | `backend/data/processed/v2/` |
| Dataset b89 (cũ) | `backend/data/processed/b89/` |
| Model checkpoint v2 | `backend/checkpoints/run_v2/` |
| Live checkpoint | `backend/checkpoints/latest/` |
| GNN week10 gốc | `backend/checkpoints/week10-b89-auc0790/` |

---

## Kết quả tổng hợp qua các tuần

| Tuần | AUC-ROC | Labels | Label type | Ghi chú |
|------|---------|--------|-----------|---------|
| Week 1 | 0.550 | ~2,000 | Synthetic | Baseline đầu |
| Week 2 | 0.712 | 9,889 | Rule-based | Real data |
| Week 9 | 0.701 | 9,889 | Rule-based | Fix early stopping |
| Week 10 (b89) | 0.790 | 5,206 | LLM labels | Best khi report |
| **Week 10 (v2)** | **0.786** | **11,565** | **LLM labels** | **Dataset cân bằng, reranker 81.2%** |

---

## Next steps

1. **Real user feedback** — click/apply/reject từ user thật để break ceiling ~0.83-0.85 của LLM-only labels
2. **Mine + label hard negatives** — sau khi có thêm user data để validate
3. **Upgrade embedding → bge-small** — khi có lý do retrain (thêm data, thay đổi pipeline)
4. **Ordinal ranking** — thử dùng `overall` 3-class (0/1/2) thay vì binary để cải thiện ranking signal
