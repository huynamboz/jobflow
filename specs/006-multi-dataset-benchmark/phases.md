# Multi-Dataset Benchmark — Kế hoạch sơ bộ

**Mục tiêu:** Train model GNN của chúng ta trên 3 dataset (MovieLens-1M, CareerBuilder12, JobFlow-CV) và 4 model (BM25, LightGCN, GraphSAGE-hetero, R-GCN-hetero) → tạo bảng benchmark đầy đủ cho luận văn.

**Chiến lược kỹ thuật:** Duplicate `backend/ml_service/` → `backend/ml_benchmark/` để tự do refactor mà không ảnh hưởng production code.

---

## Bảng benchmark đích

|                     | MovieLens-1M | CareerBuilder12 | JobFlow (ours) |
|---------------------|--------------|-----------------|----------------|
| BM25                | —            | baseline        | baseline       |
| LightGCN            | reproduce SOTA | benchmark    | benchmark      |
| GraphSAGE (ours)    | validate     | benchmark       | main result    |
| R-GCN (ours)        | validate     | benchmark       | main result    |

Metrics: **NDCG@10, Recall@10, HR@10, MRR** (mean ± std qua 3 seed).

---

## Danh sách phase

### Phase 0 — Thiết kế & thống nhất (1 ngày)
- [ ] Chốt danh sách model benchmark
- [ ] Chốt metrics + cách split (leave-one-out vs 80/10/10)
- [ ] Chốt negative sampling strategy
- [ ] Viết `plan.md` đầy đủ trong cùng thư mục này
- **Output:** `specs/006-multi-dataset-benchmark/plan.md`

### Phase 1 — Duplicate service (0.5 ngày) ✅ DONE
- [x] `cp -r backend/ml_service backend/ml_benchmark`
- [x] Xóa module không cần: `verifier/`, `inference/`, `reranker/`, `api/`, `crawler/{factory,scheduler,storage,providers}`
- [x] Đổi import `ml_service.*` → `ml_benchmark.*` trong bản copy
- [x] Tách checkpoint dir: `backend/checkpoints_benchmark/`
- [x] Commit riêng: `chore(ml_benchmark): duplicate ml_service for thesis benchmarking` (c865c3f)
- **Output:** Bản copy chạy được lại trên data hiện tại (smoke test NDCG@10=0.9266 trong 94s)
- **Implementation:** [007-duplicate-ml-benchmark](../007-duplicate-ml-benchmark/) (spec + plan + research + tasks)
- **Exception ghi nhận:** giữ `crawler/base.py` (chỉ file này) + toàn bộ `cv_parser/` vì `data/skill_extractor.py` và `data/linkedin_cv_loader.py` phụ thuộc cứng — chi tiết ở [007 research §R1](../007-duplicate-ml-benchmark/research.md#r1-cross-module-dependencies-từ-modules-to-keep-sang-modules-to-strip).

### Phase 2 — MovieLens-1M integration (2–3 ngày) *(song song với Phase 3)* ✅ DONE
- [x] Script tự download `ml-1m.zip` → `Dataset/movielens-1m/` (via Kaggle mirror sau khi grouplens.org timeout)
- [x] Viết `ml_benchmark/data/movielens_loader.py`
  - Bipartite: `user ↔ rated ↔ movie`
  - Rating ≥ 4 → positive interaction
  - ✅ Hetero variant với node `genre` (US2 stretch DONE)
- [x] Generalize `HeteroGraphSAGE` cho metadata động — thêm `decode_generic()` (additive)
- [x] Thêm `nn.Embedding` trainable cho user/movie (root cause fix: frozen embedding ban đầu cho NDCG@20=0.006, trainable cho 0.027)
- [x] Script `scripts/train_movielens.py`
- [x] **Sanity check:** đạt cùng order-of-magnitude với LightGCN paper (NDCG@20=0.0272 vs paper 0.22, ratio 0.124 ∈ [0.1, 10] — PASS SC-002)
- [x] **GPU eval optimization**: vectorize `_evaluate_full_ranking` → 6.4× faster (23 min → 3.6 min / run)
- [x] **Reproducibility**: max metric diff 0.000168 < 0.001 (PASS SC-003)
- **Output:** [008-movielens-benchmark](../008-movielens-benchmark/) — Bipartite + Hetero results trong `backend/results/movielens/`

> **⚡ Pivot decision (Option B)**: Sau Phase 2, quyết định **demote MovieLens xuống "validation cell"** trong luận văn (đặt trong appendix). MovieLens là CF benchmark, không leverage được hetero schema → gap 8× với LightGCN là kiến trúc tradeoff, không phải bug. **Main "standard benchmark" cho luận văn pivot sang CareerBuilder12 (Phase 3)** vì cùng domain job-recommendation, fair test cho hetero arch.

### Phase 3 — CareerBuilder12 integration ✅ DONE — **MAIN STANDARD BENCHMARK**
- [x] Download từ Kaggle (`jsrshivam/job-recommendation-case-study` — đúng schema CB12 gốc)
- [x] Viết `ml_benchmark/data/careerbuilder_loader.py`
  - Bipartite: `user ↔ applied ↔ job`
  - Pre-filter `min_user_apps=5` (CB12 sparser hơn MovieLens nhiều, random subsample collapse)
  - Subsample 50K active user (seed=42)
- [x] k-core=10 + LOO split per user theo `ApplicationDate`
- [x] Script `scripts/train_careerbuilder.py` (clone pattern train_movielens.py)
- [x] Reuse infrastructure Phase 2: `train_generic()`, GPU eval, trainable nn.Embedding — KHÔNG sửa trainer/gnn (SC-010 PASS)
- [x] Multi-seed (3 seed) → summary.json với mean ± std
- **Output:** [009-careerbuilder-benchmark](../009-careerbuilder-benchmark/) — main thesis result
- **Results (3 seed mean ± std)**:
  - NDCG@20 = **0.1689 ± 0.0056** (vs LightGCN paper ML 0.22, ratio 0.77)
  - Recall@20 = **0.4479 ± 0.0096** (vs paper 0.26, **1.72×**)
  - HR@20 = 0.4479 ± 0.0096
  - MRR = 0.1067 ± 0.0046
  - Wall time per seed: ~2.2 min GPU (RTX 3090) — 50% nhanh hơn MovieLens
- **Discovery quan trọng**: trên CB12 (cùng domain job-rec), kiến trúc HeteroGraphSAGE WIN paper LightGCN trên Recall@20 mặc dù THUA trên MovieLens. → Argument luận văn: **hetero arch ưu thế khi data ở domain mục tiêu (job-rec)**, kể cả bipartite variant.

### Phase 4 — Implement LightGCN baseline ✅ DONE
- [x] Wrap `torch_geometric.nn.models.LightGCN` thành `ml_benchmark/baselines/lightgcn.py`
- [x] Train loop riêng (không reuse Trainer.train_generic vì forward signature khác)
- [x] Test trên 2 dataset: MovieLens-1M + CareerBuilder12 (JobFlow rerun thuộc phase riêng)
- [x] Multi-seed 3 cho cả 2 dataset
- **Implementation:** [010-lightgcn-baseline](../010-lightgcn-baseline/)
- **Output:** Bảng so sánh apples-to-apples — `backend/results/lightgcn/{movielens,careerbuilder}_summary.json`

**Kết quả Phase 4 (LightGCN, 3 seeds mean ± std)**:

| Dataset | NDCG@20 | Recall@20 | HR@20 | MRR | Wall/seed |
|---|---|---|---|---|---|
| MovieLens-1M | 0.0258 ± 0.0034 | 0.0707 ± 0.0070 | 0.0707 ± 0.0070 | 0.0195 ± 0.0026 | ~3 min |
| CareerBuilder12 | **0.2738 ± 0.0011** | **0.6480 ± 0.0046** | **0.6480 ± 0.0046** | **0.1799 ± 0.0003** | ~1.5 min |

**Insight quan trọng đảo ngược story tạm thời**:

| | MovieLens | CB12 |
|---|---|---|
| HeteroSAGE (ta) | 0.0272 | 0.1689 |
| LightGCN (baseline) | 0.0258 | **0.2738 🏆** |
| Winner | TIE | LightGCN |

- **MovieLens**: 2 model gần TIE (HeteroSAGE = 0.0272 vs LightGCN = 0.0258) — confirm preprocessing/eval setup của ta consistent. Gap với paper LightGCN (0.22) là do preprocessing khác paper, không phải lỗi 1 model nào cụ thể.
- **CB12**: LightGCN **THẮNG đáng kể** (NDCG 1.62×, Recall 1.45× HeteroSAGE) — challenge thesis claim "model ta tốt cho job-rec". Cần argue lại:
  - LightGCN bipartite cũng work tốt cho job-rec → hetero arch không phải winning factor mặc định
  - Lý lẽ thesis còn lại: hetero arch lợi thế khi data có **rich schema** (skill, seniority) — chưa test
  - Phase tiếp theo: implement hetero variant CB12 với skill+seniority (US2 stretch của Phase 3), nếu beat LightGCN → confirm; nếu không → thesis cần điều chỉnh

### Phase 5 — Run full benchmark (1–2 ngày + GPU time)
- [ ] Viết `scripts/run_benchmark.py` chạy hết bảng 4×3
- [ ] Mỗi cell chạy 3 seed → log mean ± std
- [ ] Export CSV: `results/benchmark_table.csv`
- [ ] Plot biểu đồ so sánh (matplotlib/seaborn)
- **Output:** Bảng benchmark hoàn chỉnh + plot

### Phase 6 — Write-up cho luận văn (2–3 ngày)
- [ ] `report.md`: phân tích bảng số
- [ ] Giải thích vì sao model nào tốt hơn ở dataset nào
- [ ] Discussion: hetero GNN có lợi thế khi nào
- [ ] Limitations: MovieLens khác domain, CareerBuilder thiếu skill graph
- **Output:** `specs/006-multi-dataset-benchmark/report.md`

---

## Tổng effort

| Phase                       | Effort       |
|----------------------------|--------------|
| 0 — Design                 | 1 ngày       |
| 1 — Duplicate service      | 0.5 ngày     |
| 2 — MovieLens *(parallel)* | 2–3 ngày     |
| 3 — CareerBuilder *(parallel)* | 3–4 ngày |
| 4 — LightGCN baseline      | 1 ngày       |
| 5 — Run benchmark          | 1–2 ngày     |
| 6 — Write-up               | 2–3 ngày     |
| **Tổng (serial)**          | **~10–14 ngày** |
| **Tổng (parallel 2+3)**    | **~8–10 ngày** |

---

## Rủi ro & lưu ý

1. **MovieLens khác domain** (phim ≠ job) → không thể kết luận "model ta tốt cho job-rec" chỉ từ MovieLens. Phải argue trong luận văn rằng MovieLens dùng để **validate architecture** chứ không phải để chứng minh tính ứng dụng.

2. **MovieLens không có skill/seniority** → kiến trúc hetero degrade về bipartite. Có thể không show được "ưu điểm" của hetero — cần thêm node `genre` để tạo hetero variant.

3. **CareerBuilder cần Kaggle API key** + dung lượng lớn (~vài GB) → confirm có máy GPU + disk đủ.

4. **Reproducibility**: phải fix seed, log version PyTorch/PyG, cache splits.

5. **Code duplication tradeoff**: Bản `ml_benchmark/` sẽ drift khỏi `ml_service/` — chấp nhận, không sync ngược. Sau khi nộp luận văn có thể delete cả thư mục.

---

## Quyết định cần chốt ở Phase 0

- [ ] Có thêm NGCF baseline không? (paper hay so sánh LightGCN vs NGCF)
- [ ] Train/test split: leave-one-out per user hay 80/10/10 random?
- [ ] Số lượng negative samples cho BPR (hiện tại = 1)
- [ ] Có cần thêm dataset thứ 4 (Amazon Reviews?) cho robustness không?
- [ ] Máy nào dùng để chạy benchmark? (local GPU vs cloud)

---

## Liên kết

- Source production: [backend/ml_service/](../../backend/ml_service/)
- Memory về Education feature đã revert: ảnh hưởng đến baseline JobFlow → cần verify Week 2 baseline còn đúng không trước khi đưa vào bảng
- Spec hiện tại đang active: [003-admin-dashboard-v2/plan.md](../003-admin-dashboard-v2/plan.md) (không liên quan trực tiếp)
