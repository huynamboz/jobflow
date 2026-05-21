# Implementation Plan: LightGCN Baseline

**Branch**: `010-lightgcn-baseline` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

## Summary

Wrap `torch_geometric.nn.models.LightGCN` thành module baseline `ml_benchmark/baselines/lightgcn.py`. Train script `scripts/train_lightgcn.py` chấp nhận `--dataset {movielens, careerbuilder}` switch. Reuse loader Phase 2/3, BPR sampling, GPU eval helper, multi-seed `benchmark_compare.py`. Hyperparams theo paper (hidden=64, layers=3). Multi-seed 3 trên cả 2 dataset.

**Confirmed PyG 2.7.0 API**:
- `LightGCN(num_nodes, embedding_dim, num_layers, alpha=None)` — single ID space (user [0,Nu), item shifted [Nu, Nu+Nm))
- `get_embedding(edge_index)` → tensor `[num_nodes, embedding_dim]`
- `recommendation_loss(pos_rank, neg_rank, node_id, lambda_reg=1e-4)` → BPR + L2

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: PyTorch 2.x, PyTorch Geometric 2.7.0 (has built-in LightGCN). KHÔNG thêm dep mới.
**Storage**: `backend/results/lightgcn/{movielens,careerbuilder}_seed*.json` + `_summary.json` (committed)
**Testing**: Smoke 5 epoch < 10 phút. Regression: Phase 2 + 3 smoke vẫn PASS.
**Target Platform**: RTX 3090 server (cùng Phase 2/3)
**Performance**: Full train < 1h GPU per seed per dataset (SC-006)
**Constraints**: KHÔNG đụng ml_service, KHÔNG sửa code Phase 2/3 trainer/gnn/loaders
**Scale**: MovieLens 5949+2810=8759 nodes; CB12 ~3K+3K=6K nodes (sau subsample+k-core)

## Constitution Check

- Separation: PASS — only adds new baseline file + script
- Reversibility: PASS — 1 commit
- Isolation: PASS — `baselines/` subdir only
- Reproducibility: PASS — seed fix + tolerance per Phase 3
- Comparability: PASS — same eval methodology, same datasets, same K

## Project Structure

```
backend/
├── ml_benchmark/
│   └── baselines/
│       ├── __init__.py            (existing)
│       ├── bm25.py                (existing)
│       ├── cosine.py              (existing)
│       ├── skill_overlap.py       (existing)
│       └── lightgcn.py            ← NEW (wrapper, ~80 lines)
├── scripts/
│   └── train_lightgcn.py          ← NEW (~180 lines)
└── results/
    └── lightgcn/                  ← NEW dir
        ├── movielens_seed{42,123,2024}.json
        ├── movielens_summary.json
        ├── careerbuilder_seed{42,123,2024}.json
        └── careerbuilder_summary.json
```

## Phase 0 — Research

Đã verified PyG API. Quyết định:

| ID | Topic | Decision |
|---|---|---|
| R1 | LightGCN source | PyG `torch_geometric.nn.models.LightGCN` (verified import). |
| R2 | ID space mapping | Single namespace: user_idx → user_idx, item_idx → item_idx + num_users. Convert ở train script trước khi đưa vào model. |
| R3 | Training loop | Riêng (không reuse `Trainer.train_generic`) vì forward signature khác. ~150 lines. |
| R4 | Loss function | `model.recommendation_loss(pos_rank, neg_rank, node_id, lambda_reg=1e-4)` — built-in BPR + L2. |
| R5 | Eval — score computation | `model.get_embedding(edge_index)` → `[N, d]`. Per user score = `embed[user] @ embed[items_shifted].T`. Reuse mask/topk logic từ Phase 2 GPU eval. |
| R6 | Hyperparameters | Paper §4.3: hidden=64, layers=3, lr=1e-3, weight_decay=1e-4, BPR 1 neg, alpha=uniform 1/(K+1) (PyG default). |
| R7 | Multi-seed | Reuse `benchmark_compare.py --train-script scripts/train_lightgcn.py --extra --dataset movielens`. |
| R8 | Dataset switch | `--dataset {movielens, careerbuilder}` flag → call appropriate loader. |

## Phase 1 — Design

Đã hoàn tất artifacts:
- [data-model.md](data-model.md): LightGCN entity + ID mapping rules
- [contracts/lightgcn_api.md](contracts/lightgcn_api.md): wrapper API + script CLI
- [quickstart.md](quickstart.md): verify procedure

## Phase 2 — Tasks

`/speckit-tasks` sinh tasks.md. Dự kiến ~12-15 tasks:

1. Phase 1 Setup: results dir, baseline assertion file
2. Phase 2 Foundational: lightgcn.py wrapper + train_lightgcn.py script
3. Phase 3 US1: sync + smoke + run MovieLens + CB12 (×3 seed each) + verify
4. Phase 4 Polish: phases.md update + comparison table
5. Phase 5 Commit

## Re-evaluation post-design

All gates PASS.
