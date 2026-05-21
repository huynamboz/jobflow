# Quickstart — Verify LSTM/BiLSTM Baseline + Thesis Docs

**Date**: 2026-05-21

## Prerequisites

- Phase 1-4 merged
- `jobs_filtered.tsv` ở `Dataset/careerbuilder-12/` (Phase 4c output)
- GPU server (RTX 3090)

## Step 1 — Smoke LSTM

```bash
cd backend && .venv/bin/python scripts/train_lstm.py \
    --dataset careerbuilder --seed 42 --max-epochs 5 \
    --output /tmp/lstm_smoke.json
```

Expect: < 5 min, exit 0, NDCG@20 > 0, no NaN.

## Step 2 — Smoke BiLSTM

```bash
cd backend && .venv/bin/python scripts/train_lstm.py \
    --dataset careerbuilder --seed 42 --max-epochs 5 --bilstm \
    --output /tmp/bilstm_smoke.json
```

## Step 3 — Phase 2-4 regression

```bash
cd backend
.venv/bin/python scripts/smoke_test_movielens.py
.venv/bin/python scripts/smoke_test_careerbuilder.py
```

Both must PASS.

## Step 4 — Full LSTM (3 seeds)

```bash
cd backend && .venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_lstm.py \
    --seeds 42 123 2024 \
    --output results/lstm/careerbuilder_summary.json \
    --extra --dataset careerbuilder
```

Expect: NDCG@20 ∈ [0.01, 0.20] (SC-002).

## Step 5 — Full BiLSTM (3 seeds)

```bash
cd backend && .venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_lstm.py \
    --seeds 42 123 2024 \
    --output results/bilstm/careerbuilder_summary.json \
    --extra --dataset careerbuilder --bilstm
```

## Step 6 — Comparison table 5 models

```bash
python -c "
import json
print(f'{\"Model\":<30} NDCG@20            Recall@20')
for label, path in [
    ('HeteroSAGE bipartite', 'backend/results/careerbuilder/summary.json'),
    ('HeteroSAGE hetero',    'backend/results/careerbuilder/hetero_summary.json'),
    ('LightGCN',             'backend/results/lightgcn/careerbuilder_summary.json'),
    ('LSTM',                 'backend/results/lstm/careerbuilder_summary.json'),
    ('BiLSTM',               'backend/results/bilstm/careerbuilder_summary.json'),
]:
    r = json.load(open(path))['metrics']
    print(f'{label:<30} {r[\"ndcg@20\"][\"mean\"]:.4f}±{r[\"ndcg@20\"][\"std\"]:.4f}  {r[\"recall@20\"][\"mean\"]:.4f}±{r[\"recall@20\"][\"std\"]:.4f}')
"
```

## Step 7 — Thesis docs ready

```bash
test -f specs/011-thesis-defense-prep/thesis_notes.md && \
echo "thesis_notes.md exists, size: $(wc -c < specs/011-thesis-defense-prep/thesis_notes.md) bytes"
```

## PASS table

| Step | Tiêu chí | |
|---|---|---|
| 1, 2 | Smoke LSTM + BiLSTM < 5 min, no NaN | ☐ |
| 3 | Phase 2-4 regression PASS | ☐ |
| 4 | LSTM 3 seeds, NDCG@20 ∈ [0.01, 0.20] | ☐ |
| 5 | BiLSTM 3 seeds, similar range | ☐ |
| 6 | 5-row comparison table | ☐ |
| 7 | thesis_notes.md ≥ 5KB Vietnamese | ☐ |
