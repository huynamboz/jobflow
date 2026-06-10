# GNN v2 Proposal — tăng "độ thông minh" thật của GNN

> **Handoff document**: file này đủ thông tin để bất kỳ session nào (kể cả mới) triển khai tiếp mà không cần context cũ. Viết: 2026-06-10. Trạng thái: **Vòng 1 ĐÃ CHẠY — negative (bảng mục 6)**; Vòng 2 (pretrain) là bước kế tiếp; code Vòng 1 ở branch `024-gnn-v2`.

## 1. Vì sao cần GNN v2 — chẩn đoán đã chốt (đừng chẩn đoán lại)

3 phép đo độc lập hội tụ (chi tiết: [07-evaluation-tuning](07-evaluation-tuning.md), [11-project-journey](11-project-journey.md)):
- GNN decode AUC = **0.512** trên slice related-skill 760 cặp (ngang đoán mò) vs semantic-skill thủ công **0.861**
- Tune 3 lần đều ra **α = 0.05–0.20** (GNN là tín hiệu phụ trong blend tuyến tính)
- Oversample data thô ×3 không đổi (0.517) — lỗi không nằm ở tỉ lệ data thô

**Nguyên nhân gốc (đã xác minh):**
1. **Supervision nhỏ**: 366 CV → ~12k nhãn cặp; BPR gradient bị cặp overlap-dễ nuốt
2. **Embedding text 384-dim chi phối** node features; CV thiếu role one-hot (job có 11-dim)
3. **GraphSAGE qua `to_hetero` BỎ QUA edge weights** (proficiency/importance 1-5)
4. Decode = MLP trên concat — tương tác yếu
5. Early-stop theo **val-AUC toàn cục** → model "đạt" mà slice khó vẫn random
6. Cạnh `relates_to` (Flask–Django) chỉ là đường message-passing, không phải tín hiệu train

## 2. Mục tiêu & thước đo (đo TRƯỚC-SAU mỗi vòng, không bịa)

| Metric | Hiện tại | Vòng 1 target | Vòng 2 target |
|---|---|---|---|
| **Slice related-skill AUC** (GNN decode, 760 cặp) | 0.512 | ≥ 0.60 | ≥ 0.70 |
| Label-AUC toàn cục (GNN component) | ~0.61 | không giảm | tăng |
| Test per-CV NDCG@10 (toàn pipeline) | 0.894 | không giảm | ≥ 0.894 |
| eval 20-CV on-domain | 100% | giữ 100% | giữ 100% |
| **α sau re-tune** (bằng chứng "thông minh lên") | 0.05 | quan sát | kỳ vọng tăng |

Cách đo slice AUC (script đã chạy ở Đợt 2, tái lập): load engine `job_pool_dir="/nonexistent"` → `engine.labeled_pair_components()` → map (cv_id, job_id) → lọc `labels.json` bucket `related_skill_positive` → `roc_auc_score(label, gnn)`. Xem transcript lệnh trong /tmp/gnn_adv.log hoặc viết lại theo mô tả này (~40 dòng).

## 3. Lộ trình 3 vòng

### VÒNG 1 — rẻ, làm trước (~1 buổi, mỗi train 5 phút trên Neptune)
| # | Việc | File đụng | Chi tiết |
|---|---|---|---|
| 1.1 | **CV node + role one-hot** (386→397, đối xứng với job) | `ml_service/graph/builder.py` (~L92-101 CV features; tái dùng `ROLE_CATEGORIES` + `infer_role` từ `ml_service/inference/role_classifier.py` — đã canonical 023) | concat one-hot 11-dim; cập nhật node_dims metadata (tự động qua builder) |
| 1.2 | **Auxiliary role head**: dự đoán role_category của CV+job từ embedding | `ml_service/models/gnn.py` (thêm head Linear(hidden→11)), `ml_service/training/trainer.py` (aux CE loss, weight ~0.3; nhãn role lấy từ CVData/JobData.role_category — JobData có sẵn; CVData cần thêm field hoặc infer lúc build) | ép embedding phân cụm theo nghề |
| 1.3 | **Bucket-aware BPR**: trong `_sample_bpr_pairs` ưu tiên positive related-skill làm anchor khó + negative từ cross_domain bucket | `ml_service/training/trainer.py` (L74-174) + cần truyền bucket: `LabeledPair` thêm field `bucket` (schema.py L116) + `run_train_save.load_dataset` đọc `lbl["bucket"]` (labels.json v4 ĐÃ có field này) | thay cho oversample thô đã fail |
| 1.4 | **Early-stop theo slice AUC**: thêm "related-slice val AUC" vào eval mỗi epoch, early-stop theo nó (hoặc mean với val-AUC) | `trainer.py` `_evaluate_split`/train loop | tối ưu đúng đích |

### VÒNG 2 — sau khi Vòng 1 có số
| # | Việc | Ghi chú |
|---|---|---|
| 2.1 | **Self-supervised pretrain**: link-prediction trên cạnh requires_skill/has_skill (che 15%, đoán lại) trên TOÀN BỘ graph (6.2k jobs không cần nhãn) → fine-tune BPR | script train mới `run_pretrain.py`; load state_dict vào Trainer |
| 2.2 | **Skill-relation loss**: kéo embedding các skill có cạnh relates_to lại gần (cosine/margin loss) | trainer aux loss |
| 2.3 | **Edge-aware conv**: GATv2/TransformerConv dùng edge_attr (proficiency/importance) thay SAGE | `ml_service/models/gnn.py`; node_dims giữ nguyên |
| 2.4 | Decode bilinear/dot + MLP | gnn.py MLPDecoder |

### VÒNG 3 — dài hạn
- Tăng CV: import dataset public (CV model có sẵn `source`/`source_category`) + augmentation; re-label cặp mới bằng pipeline agent (022)
- **3.4 embedding đa ngữ** (BGE-m3/multilingual) — gộp vào lần retrain này

## 4. Quy trình mỗi vòng (BẮT BUỘC — đã thành nếp)

```
1. Sửa code local → test unit → commit
2. Sync lên Neptune (sshpass; xem .claude/commands/sync-and-train.md — dana@10.9.0.4, pass DanaServer!)
3. Train vào checkpoint THỬ NGHIỆM riêng (--checkpoint-dir checkpoints/exp_v2_round1) — KHÔNG đè latest
4. Sync checkpoint exp về local → đo: slice AUC + label-AUC + (nếu khá) re-tune + eval 20-CV
5. ĐẠT target → promote thành latest (backup latest trước) → retrain reranker (QUY TẮC A14:
   weights vào metadata TRƯỚC, reranker SAU) → rebuild pool → rematch → eval cuối
6. KHÔNG đạt → ghi số vào doc này (mục 6), thử biến thể hoặc dừng vòng — negative result cũng là kết quả
```

## 5. Bẫy đã biết (đọc kỹ trước khi code)

- **Đổi CV node dims (1.1) = checkpoint cũ không load được** → luôn train vào exp dir, giữ `backup_pre022` + `latest` nguyên vẹn tới khi promote
- `to_hetero` + symbolic trace từng crash transient trên server — retry là hết
- PyG circular import khi import trainer trước engine trong test — warm `from ml_service.inference import engine` trước
- Nhãn role cho aux head: dùng `infer_role` ĐÃ CANONICAL (023) cho CV; job dùng `role_category` có sẵn (1.484 job "other" thật — để nguyên lớp "other" trong CE 11 lớp)
- labels.json v4 tại `data/processed/v4_relabel` — trên server ĐÃ có sẵn
- Sau mọi thay đổi weights/model: **A14 guard sẽ tự warn** nếu quên retrain reranker

## 6. Kết quả các vòng (điền khi chạy)

| Vòng | Ngày | Slice AUC | Global AUC | NDCG@10 | eval 20-CV | α re-tune | Verdict |
|---|---|---|---|---|---|---|---|
| baseline | 2026-06-10 | 0.512 | ~0.61 | 0.894 | 100% | 0.05 | — |
| 1a (signal 0.5/0.5) | 2026-06-10 | 0.552 | 0.547 | 0.838 | — | — | ❌ best epoch 22, undertrained |
| 1b (signal 0.8/0.2 + warmup 40) | 2026-06-10 | 0.550 | 0.618* | 0.833 | — | — | ❌ best epoch 19 rồi thoái hoá |
| 2 | | | | | | | |

**Phân tích Vòng 1 (2 biến thể)**: slice chỉ nhích +0.04 trong khi pipeline test AUC tụt mạnh
(0.813 → ~0.62) và NDCG@10 giảm (0.894 → 0.83x); cả 2 lần "best epoch" rất sớm (19-22) rồi
signal thoái hoá → **aux role loss XUNG ĐỘT với BPR** thay vì bổ trợ (role-clustering kéo
embedding khỏi cấu trúc match-discrimination), không phải lỗi early-stop. KHÔNG promote —
`checkpoints/latest` (v1) giữ production. Code Vòng 1 nằm nguyên trên branch `024-gnn-v2`
(commit b09047b + r1b patch) — KHÔNG merge main.

**Khuyến nghị cho Vòng 2** (rút từ Vòng 1): bỏ/giảm mạnh aux role head (hoặc weight ≤0.05,
chỉ bật sau warmup); trọng tâm đặt vào **self-supervised pretrain** (link-prediction trên
requires_skill/has_skill — không đụng BPR) + **skill-relation loss** (mục 3 Vòng 2) — các
hướng bồi đắp cấu trúc TRƯỚC khi supervised, thay vì tranh chấp gradient trong lúc BPR.
(*global ở dòng 1b là test-AUC pipeline; dòng 1a là GNN-component AUC — thước hơi khác, đều kém.)

## 7. Liên quan

[07-evaluation-tuning](07-evaluation-tuning.md) (số liệu + negative result) · [05-training-pipeline](05-training-pipeline.md) (trainer/BPR chi tiết) · [02-graph-features](02-graph-features.md) (node features hiện tại) · [10-master-plan](10-master-plan.md) (3.4 gộp vào Vòng 3) · memory `train-server-neptune`
