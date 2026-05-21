# Feature Specification: LightGCN Baseline for Fair Comparison

**Feature Branch**: `010-lightgcn-baseline`

**Created**: 2026-05-21

**Status**: Draft

**Input**: User description: "Phase 4: implement LightGCN baseline thực tế trong sandbox ml_benchmark, train trên MovieLens-1M + CareerBuilder12 để fair-compare với HeteroGraphSAGE."

## Clarifications

### Session 2026-05-21 (auto-resolved per Phase 3 best practices)

User instruction: tự quyết theo best practice.

- Q: Source LightGCN implementation? → A: **`torch_geometric.nn.models.LightGCN`** built-in (PyG 2.7.0). Đã verified work trên RTX 3090 server từ Phase 1-3. Tránh copy code paper hoặc fork repo GitHub bên thứ ba (rủi ro version mismatch).
- Q: Hyperparameters LightGCN? → A: **Theo paper §4.3** — hidden_channels=64, num_layers=3, lr=1e-3, weight_decay=1e-4, BPR loss với 1 random negative. Fix giá trị này cho cả 2 dataset để comparable, không tune per-dataset.
- Q: Reuse Trainer.train_generic() hay viết loop riêng? → A: **Viết train loop riêng** trong `train_lightgcn.py`. Lý do: LightGCN có forward signature khác HeteroGraphSAGE (PyG built-in nhận edge_index trực tiếp, return embeddings + recommendation score), không fit `Trainer.train_generic()` mà không refactor lớn. Loop riêng đơn giản hơn (~50 lines) và rõ ràng hơn. Reuse: BPR loss, GPU eval helper, JSON result schema, loader datasets.
- Q: Train trên dataset nào trong Phase 4? → A: **2 dataset: MovieLens-1M (Phase 2) + CareerBuilder12 (Phase 3)**. KHÔNG bao gồm JobFlow (Phase 4b riêng vì cần JobFlow loader adapter mới). Multi-seed 3 seeds cho cả 2 dataset.
- Q: Layer combination strategy (LightGCN paper §3.2)? → A: **α_k = 1/(K+1) uniform** (default PyG, chuẩn paper). Không tune α weights.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Researcher có baseline LightGCN trên cùng dataset + cùng eval (Priority: P1) 🎯 MVP

Sau Phase 2 (MovieLens) + Phase 3 (CareerBuilder12), researcher có metric HeteroGraphSAGE nhưng KHÔNG có baseline LightGCN **thực sự chạy** trong sandbox — chỉ so với paper number. Để argument luận văn thuyết phục, cần **train LightGCN trên cùng dataset (cùng preprocessing, cùng split, cùng eval methodology) ngay trong sandbox** — apples-to-apples fair comparison.

Researcher cần: chạy 1 lệnh trên mỗi dataset → có metric LightGCN ở cùng schema JSON như HeteroGraphSAGE, sẵn sàng đưa vào bảng so sánh.

**Why this priority**: Thiếu LightGCN baseline thực, mọi argument "model ta tốt/kém so với baseline" đều dùng paper number (không fair vì khác hyperparams, khác preprocessing, khác eval). Có LightGCN baseline trong sandbox → bảng benchmark luận văn solid.

**Independent Test**: Sau Phase 4, có 2 file `results/lightgcn/{movielens,careerbuilder}_summary.json` với mean ± std qua 3 seed. Compare row-by-row với `results/{movielens,careerbuilder}/summary.json` của HeteroGraphSAGE (đã có).

**Acceptance Scenarios**:

1. **Given** sandbox đã có Phase 2 + Phase 3, **When** chạy `train_lightgcn.py --dataset movielens --seed 42`, **Then** sinh file kết quả JSON với metric NDCG@20, Recall@20, HR@20, MRR theo cùng schema Phase 2.
2. **Given** chạy với `--dataset careerbuilder`, **Then** sinh file tương tự cho CB12.
3. **Given** chạy multi-seed (3 seed), **Then** có summary JSON với mean ± std.
4. **Given** chạy 2 lần cùng seed, **Then** metric chệch < 0.05 (tolerance theo Phase 3 SC-003).
5. **Given** smoke test 5 epoch trên subset, **Then** chạy xong < 10 phút trên CPU/GPU, exit 0, không NaN.
6. **Given** full train, **Then** wall time < 1h GPU per seed per dataset.

---

### Edge Cases

- **PyG LightGCN constructor signature**: phải verify chính xác (num_nodes, embedding_dim, num_layers, alpha) khớp với PyG 2.7.0 (có thể đổi giữa versions).
- **Loss return type**: PyG LightGCN có method `link_pred_loss(pred, edge_label_index)` hay `recommendation_loss(...)`? Cần check API.
- **Negative sampling**: tự sample hay PyG handle? Default tự sample 1 random neg per positive (giống HeteroGraphSAGE).
- **Inductive vs transductive**: LightGCN transductive (cần ID embedding cho mọi node training-time). Nếu eval có node mới (cold-start) → score = 0 hoặc skip.
- **edge_index format**: PyG LightGCN cần bipartite graph ở format gì (concat user/item ID space, hay separate)? Check API.
- **Mini-batch vs full-batch**: paper dùng mini-batch BPR (2048 sample). Trên dataset nhỏ (CB12 ~3K user) full-batch OK. Trên MovieLens (~6K user, 560K train pair) cũng OK on RTX 3090.
- **CUDA non-determinism**: cùng tolerance như Phase 3 (relax).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cung cấp module baseline `ml_benchmark/baselines/lightgcn.py` wrap PyG `torch_geometric.nn.models.LightGCN`.
- **FR-002**: Hệ thống MUST cung cấp script `backend/scripts/train_lightgcn.py` chấp nhận `--dataset {movielens, careerbuilder}` flag, train LightGCN trên dataset chỉ định, output JSON kết quả.
- **FR-003**: Hệ thống MUST sinh metric NDCG@20, Recall@20, HR@20, MRR cho LightGCN theo **cùng phương pháp eval** với HeteroGraphSAGE (per-user full ranking, mask train-seen items).
- **FR-004**: Output JSON MUST theo cùng schema như Phase 2/3 (`feature, dataset, model, config, stats, training, test_metrics, versions`) — đổi `model: "LightGCN"`.
- **FR-005**: Hệ thống MUST hỗ trợ multi-seed (3 seed) trên cả 2 dataset, sinh summary mean ± std.
- **FR-006**: Hyperparameter LightGCN MUST theo paper §4.3: hidden=64, layers=3, lr=1e-3, weight_decay=1e-4, BPR 1 negative.
- **FR-007**: Reuse infrastructure Phase 2 + 3: `movielens_loader`, `careerbuilder_loader`, BPR loss, GPU eval helper, multi-seed `benchmark_compare.py`.
- **FR-008**: Hệ thống MUST hỗ trợ smoke test (5 epoch subsample) chạy < 10 phút.
- **FR-009**: Hệ thống MUST tự pick device (GPU/CPU).
- **FR-010**: Hệ thống MUST fix random seed. Reproducibility tolerance khớp Phase 3 (< 0.05 absolute cho CB12, < 0.001 cho MovieLens).
- **FR-011**: Mọi thay đổi code MUST nằm trong `backend/ml_benchmark/baselines/` + `backend/scripts/`. KHÔNG sửa Phase 2/3 code.
- **FR-012**: Regression check: smoke test Phase 2 (MovieLens) và Phase 3 (CareerBuilder) MUST vẫn pass sau merge.

### Key Entities

- **LightGCN Model**: Wrap class quanh `torch_geometric.nn.models.LightGCN`. Constructor cần `num_nodes` (user + item total), `embedding_dim`, `num_layers`. Forward trả về embeddings; có helper `recommend(src, dst_index)` cho scoring.
- **Bipartite EdgeIndex**: LightGCN dùng 1 namespace ID — user_ids ∈ [0, N_u), item_ids shifted to [N_u, N_u + N_m). Cần helper convert từ MovieLens/CareerBuilder format sang bipartite ID space.
- **LightGCN Result JSON**: cùng schema Phase 2/3, `model: "LightGCN"`, không có hetero variant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Researcher có thể chạy 1 lệnh per dataset per seed → có metric LightGCN.
- **SC-002**: LightGCN MovieLens đạt NDCG@20 trong khoảng **[0.10, 0.30]** — gần với paper number 0.22 (chứng minh implementation đúng).
- **SC-003**: LightGCN CareerBuilder12 đạt NDCG@20 trong khoảng **[0.05, 0.30]** — chứng minh chạy được, không paper reference (CB12 không có paper LightGCN).
- **SC-004**: Reproducibility tolerance khớp Phase 3 (< 0.001 MovieLens, < 0.05 CB12).
- **SC-005**: Smoke test < 10 phút.
- **SC-006**: Full train < 1h GPU per seed per dataset.
- **SC-007**: 100% file trong `backend/ml_service/` không đổi.
- **SC-008**: Phase 2 + Phase 3 smoke test vẫn pass sau merge (regression).
- **SC-009**: Phase 4 hoàn thành trong ≤ 1 ngày làm việc.
- **SC-010**: Cuối phase, có bảng so sánh **HeteroGraphSAGE vs LightGCN trên cả MovieLens + CB12** — 8 cell (4 model variant × 2 dataset, nếu tính bipartite + multi-seed).

## Assumptions

- Sandbox `backend/ml_benchmark/` có đủ infra Phase 2 + 3.
- PyG 2.7.0 trên server có `torch_geometric.nn.models.LightGCN` (verified import được).
- Cùng GPU server + Kaggle credentials Phase 2 setup.
- LightGCN paper hyperparams default work tốt — không cần tune cho thesis benchmark.
- Eval methodology Phase 2/3 (per-user full ranking với train-seen mask) là fair cho LightGCN — cần verify (mặc dù paper LightGCN cũng dùng full ranking).
- LightGCN với num_layers=3 không OOM trên 50K user CB12 (test bằng smoke).

## Dependencies

- Sandbox Phase 2 (008): `movielens_loader`, GPU eval helper trong trainer
- Sandbox Phase 3 (009): `careerbuilder_loader`, `benchmark_compare` đã support `--train-script`
- PyG 2.7.0: `torch_geometric.nn.models.LightGCN`
- Parent plan: [phases.md Phase 4](../006-multi-dataset-benchmark/phases.md)

## Out of Scope

- JobFlow rerun (làm sau khi LightGCN xong — Phase 4b)
- Full benchmark table 4×3 (Phase 5)
- Hyperparameter tuning LightGCN — dùng paper default
- NGCF / PinSage / GAT baseline (defer)
- LightGCN variants (LightGCN+, simplified GCN) — defer
- LightGCN trên hetero schema — LightGCN bản chất bipartite, không có hetero variant
