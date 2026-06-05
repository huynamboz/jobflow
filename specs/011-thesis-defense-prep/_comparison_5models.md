# 5-Model Comparison on CareerBuilder12 (committed evidence)

**Generated**: 2026-05-22
**Dataset**: CareerBuilder12, 50k active users (k-core ≥10, leave-one-out split)
**Eval**: Per-user full ranking, 3 seeds (42, 123, 2024), mean ± std
**Hardware**: NVIDIA RTX 3090, GPU-vectorized chunked argsort

## Bảng so sánh

| Model | NDCG@20 | Recall@20 | HR@20 | MRR | Wall/seed |
|---|---|---|---|---|---|
| HeteroSAGE bipartite | 0.1689 ± 0.0056 | 0.4479 ± 0.0096 | 0.4479 ± 0.0096 | 0.1067 ± 0.0046 | ~2.2 min |
| HeteroSAGE hetero (skill+seniority) | 0.1426 ± 0.0148 | 0.3891 ± 0.0286 | 0.3891 ± 0.0286 | 0.0897 ± 0.0106 | ~4.7 min |
| **LightGCN** | **0.2738 ± 0.0011** | **0.6480 ± 0.0046** | **0.6480 ± 0.0046** | **0.1799 ± 0.0003** | ~1.5 min |
| LSTM (sequence) | 0.0763 ± 0.0032 | 0.1985 ± 0.0100 | 0.1985 ± 0.0100 | 0.0529 ± 0.0016 | ~5–7 min |
| BiLSTM (sequence) | 0.0911 ± 0.0087 | 0.2300 ± 0.0194 | 0.2300 ± 0.0194 | 0.0629 ± 0.0058 | ~8–10 min |

## Findings

1. **LightGCN dominates**: NDCG@20 = 0.2738, gấp **3.6× LSTM**, **3.0× BiLSTM**, **1.6× HeteroSAGE bipartite**.
2. **GNN family > Sequence family**: cả 3 GNN đều beat LSTM/BiLSTM với gap > 50% NDCG. Khẳng định collaborative signal quan trọng hơn semantic text trên CB12.
3. **BiLSTM > LSTM** (+19% NDCG): bidirectional context giúp encode user skill list + job description tốt hơn — đúng kỳ vọng từ literature.
4. **Hetero schema THUA bipartite** trên CB12 (NDCG 0.1426 vs 0.1689): skill extraction từ noisy job text (keyword matching) tạo noise signal; chỉ có lợi khi data rich như JobFlow.
5. **Cost / benefit**: LightGCN có wall time thấp nhất (~1.5 min/seed) nhưng metric cao nhất — extremely efficient cho CB12 (pure CF benchmark).

## Variance Analysis

| Model | Std/Mean NDCG@20 | Stability |
|---|---|---|
| LightGCN | 0.4% | Excellent |
| HeteroSAGE bipartite | 3.3% | Good |
| LSTM | 4.2% | Good |
| BiLSTM | 9.5% | Moderate |
| HeteroSAGE hetero | 10.4% | High variance |

LightGCN extremely stable (single hyperparam config, simple loss). HeteroSAGE hetero highest variance — schema noise compounds.

## Reproducibility

```bash
cd backend
.venv/bin/python scripts/train_careerbuilder.py --seed 42 --output results/careerbuilder/seed42.json
.venv/bin/python scripts/train_lightgcn.py --dataset careerbuilder --seed 42 --output results/lightgcn/cb_seed42.json
.venv/bin/python scripts/train_lstm.py --dataset careerbuilder --seed 42 --output results/lstm/seed42.json
.venv/bin/python scripts/train_lstm.py --dataset careerbuilder --seed 42 --bilstm --output results/bilstm/seed42.json
```

Multi-seed:
```bash
.venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_lstm.py \
    --seeds 42 123 2024 \
    --output results/lstm/careerbuilder_summary.json \
    --extra --dataset careerbuilder
```

## Conclusion for Thesis

> **HeteroGraphSAGE là lựa chọn đúng** vì thắng JobFlow data (rich curated schema, NDCG ≈ 0.40); nhưng trên CB12 (pure CF benchmark, sparse keyword skills), **LightGCN baseline mạnh hơn**. Cả 3 GNN đều **vượt LSTM/BiLSTM** — chứng minh collaborative signal > semantic text cho job recommendation trên CB12.
>
> Đây là **negative result có giá trị**: phải có data đủ rich thì hetero arch mới thắng; pure CF tasks → LightGCN simple-and-strong baseline đáng giá.

---

**Source data**: `backend/results/{careerbuilder, lightgcn, lstm, bilstm}/*_summary.json`
**Train scripts**: `backend/scripts/train_{careerbuilder, lightgcn, lstm}.py`
**Baseline modules**: `backend/ml_benchmark/baselines/{lightgcn, lstm}.py`
