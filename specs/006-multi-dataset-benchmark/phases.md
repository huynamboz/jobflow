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

### Phase 1 — Duplicate service (0.5 ngày)
- [ ] `cp -r backend/ml_service backend/ml_benchmark`
- [ ] Xóa module không cần: `verifier/`, `crawler/`, `cv_parser/`, `inference/`, `reranker/`, `api/`
- [ ] Đổi import `ml_service.*` → `ml_benchmark.*` trong bản copy
- [ ] Tách checkpoint dir: `backend/checkpoints_benchmark/`
- [ ] Commit riêng: `chore: duplicate ml_service → ml_benchmark for thesis benchmarking`
- **Output:** Bản copy chạy được lại trên data hiện tại

### Phase 2 — MovieLens-1M integration (2–3 ngày) *(song song với Phase 3)*
- [ ] Script tự download `ml-1m.zip` → `Dataset/movielens-1m/`
- [ ] Viết `ml_benchmark/data/movielens_loader.py`
  - Bipartite: `user ↔ rated ↔ movie`
  - Rating ≥ 4 → positive interaction
  - Optional: thêm node `genre` cho hetero variant
- [ ] Generalize `HeteroGraphSAGE` cho metadata động (bỏ hardcode 386/385/6)
- [ ] Thêm `nn.Embedding` cho user/movie (không có rich features)
- [ ] Script `scripts/train_movielens.py`
- [ ] **Sanity check:** reproduce LightGCN paper số (Recall@20 ≈ 0.26, NDCG@20 ≈ 0.22)
- **Output:** Kết quả 4 model trên MovieLens-1M

### Phase 3 — CareerBuilder12 integration (3–4 ngày) *(song song với Phase 2)*
- [ ] Download từ Kaggle (`careerbuilder-job-recommendation`)
- [ ] Viết `ml_benchmark/data/careerbuilder_loader.py`
  - Map `users.tsv` → `cv` node
  - Map `jobs.tsv` → `job` node
  - Map `apps.tsv` → `match` edge
  - Job description → sentence-embedding (reuse `ml_benchmark/embedding/`)
- [ ] Subsample nếu cần (1.6M apps có thể quá lớn)
- [ ] Mini-batch sampling với `NeighborLoader` của PyG
- [ ] Script `scripts/train_careerbuilder.py`
- **Output:** Kết quả 4 model trên CareerBuilder12

### Phase 4 — Implement LightGCN baseline (1 ngày)
- [ ] Wrap `torch_geometric.nn.models.LightGCN` thành `ml_benchmark/baselines/lightgcn.py`
- [ ] Tích hợp với trainer chung
- [ ] Test trên cả 3 dataset
- **Output:** LightGCN chạy được trên cả 3 dataset

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
