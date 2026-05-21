# Quickstart — Verify LightGCN Baseline

**Date**: 2026-05-21

Mất ~30-60 phút (2 dataset × 3 seed × ~5 min each + verify).

## Prerequisites

- Phase 2 (008) + Phase 3 (009) merged
- Cùng GPU server
- Datasets cached: `Dataset/movielens-1m/`, `Dataset/careerbuilder-12/`

## Step 1 — Smoke test (subsample, 5 epoch)

```bash
cd backend && .venv/bin/python scripts/train_lightgcn.py \
    --dataset movielens --seed 42 --max-epochs 5 \
    --subsample-users 1000 --k-core 5 \
    --output /tmp/smoke_lgcn.json
```

Expect: < 5 min, exit 0, NDCG@20 > 0.

## Step 2 — Phase 2/3 regression

```bash
cd backend
.venv/bin/python scripts/smoke_test_movielens.py
.venv/bin/python scripts/smoke_test_careerbuilder.py
```

Expect: both PASS (cùng metric trước).

## Step 3 — Full train MovieLens (3 seeds)

```bash
cd backend && .venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_lightgcn.py \
    --seeds 42 123 2024 \
    --output results/lightgcn/movielens_summary.json \
    --extra --dataset movielens
```

Expect: NDCG@20 ∈ [0.10, 0.30] (gần paper 0.22), mỗi seed ~5-15 min GPU.

## Step 4 — Full train CareerBuilder12 (3 seeds)

```bash
cd backend && .venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_lightgcn.py \
    --seeds 42 123 2024 \
    --output results/lightgcn/careerbuilder_summary.json \
    --extra --dataset careerbuilder
```

Expect: NDCG@20 ∈ [0.05, 0.30], mỗi seed ~2-5 min GPU.

## Step 5 — Comparison table

```bash
python -c "
import json
for ds in ['movielens', 'careerbuilder']:
    them = json.load(open(f'backend/results/lightgcn/{ds}_summary.json'))
    us = json.load(open(f'backend/results/{ds}/summary.json'))
    print(f'\\n{ds}:')
    for k in ['ndcg@20', 'recall@20', 'hr@20', 'mrr']:
        print(f'  {k:10} LightGCN={them[\"metrics\"][k][\"mean\"]:.4f}±{them[\"metrics\"][k][\"std\"]:.4f}  HeteroSAGE={us[\"metrics\"][k][\"mean\"]:.4f}±{us[\"metrics\"][k][\"std\"]:.4f}')
"
```

## Step 6 — Production untouched

```bash
git diff --stat backend/ml_service/
```

Expect: empty.

## PASS table

| Step | Tiêu chí | |
|---|---|---|
| 1 | Smoke < 5 min, no NaN | ☐ |
| 2 | Phase 2 + 3 regression PASS | ☐ |
| 3 | LightGCN MovieLens 3 seeds, NDCG@20 ∈ [0.10, 0.30] | ☐ |
| 4 | LightGCN CB12 3 seeds, NDCG@20 ∈ [0.05, 0.30] | ☐ |
| 5 | Comparison table generated | ☐ |
| 6 | Production untouched | ☐ |
