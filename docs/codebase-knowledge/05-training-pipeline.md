# Training Pipeline (GNN + Reranker)

## Đường train PRODUCTION (đã tạo `checkpoints/latest`)

```
data/processed/b89_full  (export từ nhãn LLM — xem 03-labeling-pipeline.md)
   │  run_train_save.py
   ├─ load_dataset: cvs.json/jobs.json/labels.json/skills.json → CVData/JobData/LabeledPair
   ├─ GraphBuilder.build → HeteroData (xem 02-graph-features.md)
   ├─ Trainer.train (BPR + hard negatives + curriculum)
   └─ save: model.pt · graph.pt · cvs.json · jobs.json · metadata.json
        + (riêng) train_reranker.py → reranker.pt/reranker_meta.json · calibration.json
```

Config production (`run_train_save.py:53-65`): graphsage, hidden=256, layers=3, lr=1e-3, epochs=300, patience=80, seed=500. `metadata.json` ghi `data_dir=data/processed/b89_full`, test AUC=0.876.

⚠️ Có **2 đường train** — đừng nhầm:
| | Production | In-app (TrainRun) |
|---|---|---|
| Script | `run_train_save.py` | `apps/matching/services/train_service.py` |
| Nhãn | **LLM labels** (b89_full) | `PairLabeler` rule tự sinh (overlap≥0.4 & Δsen≤1 → pos; <0.15 hoặc Δsen≥3 → neg; noise 10%) |
| Trạng thái | nguồn checkpoint hiện tại | **không dùng cho production** |

## Trainer (`ml_service/training/trainer.py`)

- **Loss**: BPR — `-log(sigmoid(pos_score - neg_score))` (losses.py:7). Tối ưu ranking positive > negative per CV.
- **`_strip_label_edges`** (L64): bỏ cạnh match/no_match khỏi graph khi message-passing → tránh label leakage; nhãn chỉ dùng để sample triplet.
- **Hard negative sampling** (`_sample_bpr_pairs` L74-174): negative "hard" = labeled-negative có overlap ≥ 0.15 **và** Δsen ≤ 1 (trông giống positive). `full_space_neg=True`: negative còn lại sample từ **toàn bộ** job space.
- **Curriculum** (L201-208): epoch 0-4 hard_ratio=0 → 5-19: 0.3 → 20+: **0.7**.
- Early stopping theo **val AUC**, val triplets cố định seed 99 (deterministic).
- Eval trong train dùng **hybrid score** `0.55·gnn_norm + 0.30·skill + 0.15·seniority` (L373-433) — lưu ý: khác trọng số tuned runtime.

⚠️ **Gap đã xác định (liên quan bug domain)**: định nghĩa "hard negative" chỉ dựa overlap+seniority, **không có cross-domain** (skill cao × khác nghề); và tập nhãn vốn chỉ có 2% cặp như vậy → GNN không được ép học ranh giới domain. Xem [08-improvement-opportunities.md](08-improvement-opportunities.md).

## GNN model (`ml_service/models/gnn.py`)

```
HeteroGraphSAGE:
  per-type Linear projection → hidden 256   (CV 386→256, Job 397→256, Skill 385→256, Seniority 6→256)
  GraphSAGE × 3 layers (to_hetero, mean aggregation)
  MLPDecoder: concat(cv_emb, job_emb) → ReLU → Linear → logit
```
Alternative: HeteroRGCN (per-edge-type weights) — không dùng production. `prepare_data_for_gnn` thêm reverse edges (ToUndirected).

## Reranker (`ml_service/reranker/`)

- **Kiến trúc** (ranker.py:25-57): MLP 23→64→64 trunk + **main head** (3-class ordinal: overall 0/1/2) + **4 aux heads** (mỗi dim 3-class).
- **Train** (L77-169): CrossEntropy inverse-freq weighted; aux loss (mask -1) weight 0.3. **dim_labels = 4 dim LLM chấm trong HumanLabel** (nguồn rõ ràng).
- **Inference score** = ordinal expectation `softmax·[0,1,2]/2` ∈ [0,1].
- **23 features** (features.py:20-46): text_sim, jaccard, weighted_overlap, semantic_overlap, missing_required (count+ratio), matched_count, total_job_skills, seniority (dist+score), role_penalty, exp_years, cv_skill_count, skill_specificity, tool_ratio, **stage1_score**, **gnn_score**, **gnn_rank**, must_have_cap, edge_case_flag, coverage_ratio, experience_gap, role_category_match.
- **Calibration**: PlattCalibrator (sigmoid a·s+b, GD 1000 iter) → calibration.json.
- Script: `train_reranker.py` (trên exported labels + dims); `run_train_reranker.py` (pipeline cũ dùng PairLabeler — legacy).

## Checkpoint artifacts (`checkpoints/latest/`)

| File | Nội dung |
|---|---|
| model.pt | GNN state_dict |
| graph.pt | HeteroData đầy đủ (gồm cạnh match/no_match — nguồn cho tuner 019/020) |
| cvs.json / jobs.json | CVData/JobData pool đóng băng (365 CV / 6.251 job) |
| reranker.pt + reranker_meta.json | MLP reranker |
| calibration.json | Platt a,b |
| metadata.json | train_config, test_metrics, node_dims, **hybrid_weights (single source — tuned 019/020)** |

## Metrics (ml_service/evaluation/metrics.py)

auc_roc, recall@5/10, precision@5/10, ndcg@10, hit_rate@5/10, mrr — tính trong val/test mỗi epoch.

## Script phụ

- `run_grid_search.py`: grid hidden×dropout×lr (18 config).
- `run_experiment_*.py`: thí nghiệm LinkedIn/real-CV cũ.
- `ml_benchmark/`: sandbox benchmark (feature 007-010), tách khỏi production.

## Cập nhật GNN v2 (024 — 2026-06-11)

Quy trình train production hiện tại (2 bước, đều `EMBEDDING_PROVIDER=multilingual`):
```bash
# trên Neptune
EMBEDDING_PROVIDER=multilingual python run_pretrain.py --out checkpoints/pretrain_ml/backbone.pt
EMBEDDING_PROVIDER=multilingual PRETRAIN_PATH=checkpoints/pretrain_ml/backbone.pt \
  python run_train_save.py --data data/processed/v4_relabel --checkpoint-dir checkpoints/<exp>
python measure_slice.py --checkpoint checkpoints/<exp>   # slice + global decode AUC
```
- `LabeledPair.bucket` đi từ labels.json vào sampler; BPR boost ×3 anchor related-skill positives
- Early-stop signal = 0.8·val_auc + 0.2·related_slice_auc (slice đo bằng PURE decode mỗi epoch)
- Env gates: AUX_ROLE_WEIGHT=0 (bật = phá BPR — xem doc 12 Vòng 1), SKILL_REL_WEIGHT=0, GNN_MODEL=graphsage
- Sau train: tune weights → ghi metadata → train_reranker (A14) — ĐÚNG THỨ TỰ NÀY
