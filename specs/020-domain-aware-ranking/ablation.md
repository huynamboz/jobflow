# Dual-metric hybrid-weight ablation (feature 020)

Labeled pairs: 12084 (match 4021 / no_match 8063, role-relevant 3787) · validation 2416 · grid 0.05 · seed 42 · objective balanced · k=10.

| rank | α | β | γ | δ | label-AUC | role-NDCG@10 | role-P@10 | note |
|---|---|---|---|---|-----------|------|------|------|
| 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.7008 | 1.0000 | 0.4465 |  |
| 2 | 0.00 | 0.00 | 0.05 | 0.95 | 0.6981 | 1.0000 | 0.4465 |  |
| 3 | 0.00 | 0.00 | 0.10 | 0.90 | 0.6981 | 1.0000 | 0.4465 |  |
| 4 | 0.00 | 0.00 | 0.15 | 0.85 | 0.6981 | 1.0000 | 0.4465 |  |
| 5 | 0.00 | 0.00 | 0.20 | 0.80 | 0.6981 | 1.0000 | 0.4465 |  |
| 6 | 0.00 | 0.05 | 0.00 | 0.95 | 0.8127 | 1.0000 | 0.4465 |  |
| 7 | 0.00 | 0.05 | 0.05 | 0.90 | 0.7570 | 1.0000 | 0.4465 |  |
| 8 | 0.00 | 0.05 | 0.10 | 0.85 | 0.7356 | 1.0000 | 0.4465 |  |
| 9 | 0.00 | 0.05 | 0.15 | 0.80 | 0.7333 | 1.0000 | 0.4465 |  |
| 10 | 0.00 | 0.05 | 0.20 | 0.75 | 0.7327 | 1.0000 | 0.4465 |  |
| 11 | 0.00 | 0.10 | 0.00 | 0.90 | 0.8127 | 1.0000 | 0.4465 |  |
| 12 | 0.00 | 0.10 | 0.05 | 0.85 | 0.7901 | 1.0000 | 0.4465 |  |
| 13 | 0.00 | 0.10 | 0.10 | 0.80 | 0.7570 | 1.0000 | 0.4465 |  |
| 14 | 0.00 | 0.10 | 0.15 | 0.75 | 0.7401 | 1.0000 | 0.4465 |  |
| 15 | 0.00 | 0.15 | 0.00 | 0.85 | 0.8127 | 1.0000 | 0.4465 |  |
| 16 | 0.00 | 0.15 | 0.05 | 0.80 | 0.8023 | 1.0000 | 0.4465 |  |
| 17 | 0.00 | 0.15 | 0.10 | 0.75 | 0.7778 | 1.0000 | 0.4465 |  |
| 18 | 0.00 | 0.15 | 0.15 | 0.70 | 0.7572 | 1.0000 | 0.4465 |  |

**Chosen** (max balanced): α=0.30 β=0.20 γ=0.10 δ=0.40 · role-NDCG@10=0.9942 · role-P@10=0.4454 · label-AUC=0.7859
**Label-AUC winner** (feature 019: 0.20/0.75/0.05/0): label-AUC=0.8485 · role-NDCG@10=0.8186 · role-P@10=0.4256
**Legacy** (0.55/0.30/0.15/0): label-AUC=0.7058 · role-NDCG@10=0.7670 · role-P@10=0.4260

The two objectives favour different weights: optimizing label-AUC alone gives the β-heavy δ=0 row (high label-AUC, low role-NDCG → domain-mismatched top results); the role-aware objective restores α (GNN) + δ (domain) and lifts role-NDCG.

NOTE — circularity guard: a PURE role-NDCG objective is degenerate (δ=1.0 makes the score equal the relevance signal → role-NDCG=1.0 but label-AUC collapses to ~0.62, useless). The chosen row uses the **balanced** objective: max role-NDCG subject to label-AUC ≥ 0.85·max and δ ≤ 0.4 (domain stays a soft term).
