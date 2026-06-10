# Dual-metric hybrid-weight ablation (feature 020)

Labeled pairs: 12084 (match 4021 / no_match 8063, role-relevant 3114) · validation 2416 · grid 0.05 · seed 42 · objective balanced · k=10.

| rank | α | β | γ | δ | label-AUC | role-NDCG@10 | role-P@10 | note |
|---|---|---|---|---|-----------|------|------|------|
| 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.5990 | 1.0000 | 0.4627 |  |
| 2 | 0.00 | 0.00 | 0.05 | 0.95 | 0.5958 | 1.0000 | 0.4627 |  |
| 3 | 0.00 | 0.00 | 0.10 | 0.90 | 0.5958 | 1.0000 | 0.4627 |  |
| 4 | 0.00 | 0.00 | 0.15 | 0.85 | 0.5958 | 1.0000 | 0.4627 |  |
| 5 | 0.00 | 0.00 | 0.20 | 0.80 | 0.5958 | 1.0000 | 0.4627 |  |
| 6 | 0.00 | 0.00 | 0.25 | 0.75 | 0.5958 | 1.0000 | 0.4627 |  |
| 7 | 0.00 | 0.00 | 0.30 | 0.70 | 0.5958 | 1.0000 | 0.4627 |  |
| 8 | 0.00 | 0.00 | 0.35 | 0.65 | 0.5958 | 1.0000 | 0.4627 |  |
| 9 | 0.00 | 0.00 | 0.40 | 0.60 | 0.5958 | 1.0000 | 0.4627 |  |
| 10 | 0.00 | 0.00 | 0.45 | 0.55 | 0.5958 | 1.0000 | 0.4627 |  |
| 11 | 0.00 | 0.05 | 0.00 | 0.95 | 0.7888 | 1.0000 | 0.4627 |  |
| 12 | 0.00 | 0.05 | 0.05 | 0.90 | 0.6954 | 1.0000 | 0.4627 |  |
| 13 | 0.00 | 0.05 | 0.10 | 0.85 | 0.6586 | 1.0000 | 0.4627 |  |
| 14 | 0.00 | 0.05 | 0.15 | 0.80 | 0.6548 | 1.0000 | 0.4627 |  |
| 15 | 0.00 | 0.05 | 0.20 | 0.75 | 0.6536 | 1.0000 | 0.4627 |  |
| 16 | 0.00 | 0.05 | 0.25 | 0.70 | 0.6534 | 1.0000 | 0.4627 |  |
| 17 | 0.00 | 0.05 | 0.30 | 0.65 | 0.6534 | 1.0000 | 0.4627 |  |
| 18 | 0.00 | 0.05 | 0.35 | 0.60 | 0.6534 | 1.0000 | 0.4627 |  |

**Chosen** (max balanced): α=0.05 β=0.35 γ=0.20 δ=0.40 · role-NDCG@10=1.0000 · role-P@10=0.4627 · label-AUC=0.7495
**Label-AUC winner** (feature 019: 0.20/0.75/0.05/0): label-AUC=0.8373 · role-NDCG@10=0.7882 · role-P@10=0.4317
**Legacy** (0.55/0.30/0.15/0): label-AUC=0.7461 · role-NDCG@10=0.7945 · role-P@10=0.4322

The two objectives favour different weights: optimizing label-AUC alone gives the β-heavy δ=0 row (high label-AUC, low role-NDCG → domain-mismatched top results); the role-aware objective restores α (GNN) + δ (domain) and lifts role-NDCG.

NOTE — circularity guard: a PURE role-NDCG objective is degenerate (δ=1.0 makes the score equal the relevance signal → role-NDCG=1.0 but label-AUC collapses to ~0.62, useless). The chosen row uses the **balanced** objective: max role-NDCG subject to label-AUC ≥ 0.85·max and δ ≤ 0.4 (domain stays a soft term).
