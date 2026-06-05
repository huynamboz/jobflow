---
description: "Task list for feature 010 — LightGCN Baseline"
---

# Tasks: LightGCN Baseline

**Input**: Design documents from `/specs/010-lightgcn-baseline/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/lightgcn_api.md, quickstart.md

**Tests**: Spec không yêu cầu TDD. Verify bằng regression Phase 2/3 + sanity metric.

**Organization**: 1 user story (P1 MVP). Hetero variant N/A cho LightGCN.

## Format: `[ID] [P?] [Story?] Description`

## Path Conventions

- Sandbox: `backend/ml_benchmark/baselines/` (mới thêm 1 file)
- Scripts: `backend/scripts/`
- Results: `backend/results/lightgcn/`
- Server: `/home/dana/huynam/jobflow-gnn/backend/`

---

## Phase 1: Setup

- [ ] T001 [P] Tạo `backend/results/lightgcn/` với `.gitkeep`.
- [ ] T002 Verify PyG có `torch_geometric.nn.models.LightGCN` (đã verified local trong research phase) — re-confirm trên server: `sshpass -e ssh dana@10.9.0.4 "/home/dana/huynam/jobflow-gnn/backend/.venv/bin/python -c 'from torch_geometric.nn.models import LightGCN; print(LightGCN.__module__)'"`.

---

## Phase 2: Foundational (BLOCKING)

- [ ] T003 Viết `backend/ml_benchmark/baselines/lightgcn.py`:
  - Class `LightGCNScorer(nn.Module)` theo [contract §2](contracts/lightgcn_api.md#2-lightgcnscorer-class).
  - Wrap `torch_geometric.nn.models.LightGCN(num_nodes=Nu+Ni, embedding_dim, num_layers)`.
  - Methods: `get_user_item_embeddings(edge_index)`, `score_edges(edge_index, src, dst)`, `recommendation_loss(pos_rank, neg_rank, node_id, lambda_reg)`.
  - Helper `shift_items(item_indices, num_users)` để shift item IDs sang bipartite namespace.
- [ ] T004 Viết `backend/scripts/train_lightgcn.py` (~180 lines):
  - sklearn + torch_geometric pre-warm (lessons Phase 2)
  - CLI args: `--dataset {movielens, careerbuilder}`, `--seed`, `--max-epochs 500`, `--patience 50`, `--hidden 64`, `--num-layers 3`, `--lr 1e-3`, `--weight-decay 1e-4`, `--lambda-reg 1e-4`, `--max-epochs`, `--subsample-users`, `--k-core`, `--output`.
  - Switch loader theo `--dataset` (load_movielens_1m hoặc load_careerbuilder_12).
  - Build edge_index bipartite (shift item IDs +num_users).
  - Train loop với BPR + `model.recommendation_loss`.
  - Eval: `model.get_embedding` + per-user full ranking dot product (adapt từ Phase 2 GPU eval). Bypass HeteroGraphSAGE Trainer.
  - Output JSON theo schema Phase 2/3 (đổi model="LightGCN").

---

## Phase 3: User Story 1 — Train LightGCN trên 2 dataset (P1 🎯)

- [ ] T005 [US1] Sync code lên server: `lightgcn.py` + `train_lightgcn.py`.
- [ ] T006 [US1] Smoke test trên server: `python scripts/train_lightgcn.py --dataset movielens --seed 42 --max-epochs 5 --output /tmp/smoke_lgcn.json`. Verify: < 5 min, exit 0, no NaN. Lưu log untracked.
- [ ] T007 [P] [US1] Regression check Phase 2: `python scripts/smoke_test_movielens.py --epochs 5` — verify NDCG@10 ≈ 0.0179 (cùng Phase 2 baseline).
- [ ] T008 [P] [US1] Regression check Phase 3: `python scripts/smoke_test_careerbuilder.py` — verify same NDCG@20 như Phase 3 smoke.
- [ ] T009 [US1] **Full train MovieLens 3 seeds**: `python scripts/benchmark_compare.py --train-script scripts/train_lightgcn.py --seeds 42 123 2024 --output results/lightgcn/movielens_summary.json --extra --dataset movielens`. Wall time ~15-30 min total.
- [ ] T010 [US1] Verify MovieLens metric (SC-002): NDCG@20 ∈ [0.10, 0.30] (gần paper 0.22). Nếu < 0.10 → debug.
- [ ] T011 [US1] **Full train CareerBuilder12 3 seeds**: `python scripts/benchmark_compare.py --train-script scripts/train_lightgcn.py --seeds 42 123 2024 --output results/lightgcn/careerbuilder_summary.json --extra --dataset careerbuilder`. Wall time ~10-20 min total.
- [ ] T012 [US1] Verify CB12 metric (SC-003): NDCG@20 ∈ [0.05, 0.30].
- [ ] T013 [US1] Sync results về local: 8 JSON files (3 seeds + 1 summary mỗi dataset = 8 files).
- [ ] T014 [P] [US1] Verify SC-007 production untouched: `git diff --stat backend/ml_service/` empty.
- [ ] T015 [US1] Generate comparison table: chạy snippet ở quickstart Step 5 — in bảng LightGCN vs HeteroSAGE trên 2 dataset.

---

## Phase 4: Polish

- [ ] T016 [P] Update `specs/006-multi-dataset-benchmark/phases.md` mark Phase 4 DONE + link 010.
- [ ] T017 Save comparison table vào `specs/010-lightgcn-baseline/_comparison_table.md` (untracked) hoặc embed vào tasks polish doc.

---

## Phase 5: Commit

- [ ] T018 Stage feature 010 artifacts:
  ```
  git add backend/ml_benchmark/baselines/lightgcn.py \
          backend/scripts/train_lightgcn.py \
          backend/results/lightgcn/ \
          specs/010-lightgcn-baseline/ \
          specs/006-multi-dataset-benchmark/phases.md \
          CLAUDE.md \
          .specify/feature.json
  ```
  TUYỆT ĐỐI KHÔNG `git add backend/ml_service/`.
- [ ] T019 Verify staged sạch: `git diff --cached --stat | grep ml_service` empty.
- [ ] T020 Commit với heredoc message (sẽ chi tiết khi implement).
- [ ] T021 Verify single commit + production history clean.

---

## Dependencies

- Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
- T007 + T008 + T014 parallel ([P]) trong cùng phase
- T016 parallel ([P]) với T017

## MVP scope

T001-T015 → có metric LightGCN + bảng so sánh → Phase 4 close-able. T016-T021 chỉ polish + commit.

## Notes

- LightGCN training nhanh hơn HeteroGraphSAGE (model nhẹ hơn, dot product decoder thay MLP). Mỗi seed ước ~3-10 min.
- Total Phase 4 GPU: ~40-80 min cho 6 train run (2 dataset × 3 seed).
- Code mới: lightgcn.py (~80 lines) + train_lightgcn.py (~180 lines) = ~260 lines. Còn lại reuse Phase 2/3.
