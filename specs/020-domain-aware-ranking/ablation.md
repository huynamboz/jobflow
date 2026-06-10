# Dual-metric hybrid-weight ablation (feature 020)

Labeled pairs: 13509 (match 3563 / no_match 9946, role-relevant 3280) · validation 2701 · grid 0.05 · seed 42 · objective balanced · k=10.

| rank | α | β | γ | δ | label-AUC | role-NDCG@10 | role-P@10 | note |
|---|---|---|---|---|-----------|------|------|------|
| 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.6218 | 1.0000 | 0.4796 |  |
| 2 | 0.00 | 0.00 | 0.05 | 0.95 | 0.6534 | 1.0000 | 0.4796 |  |
| 3 | 0.00 | 0.00 | 0.10 | 0.90 | 0.6534 | 1.0000 | 0.4796 |  |
| 4 | 0.00 | 0.00 | 0.15 | 0.85 | 0.6534 | 1.0000 | 0.4796 |  |
| 5 | 0.00 | 0.00 | 0.20 | 0.80 | 0.6534 | 1.0000 | 0.4796 |  |
| 6 | 0.00 | 0.00 | 0.25 | 0.75 | 0.6534 | 1.0000 | 0.4796 |  |
| 7 | 0.00 | 0.00 | 0.30 | 0.70 | 0.6534 | 1.0000 | 0.4796 |  |
| 8 | 0.00 | 0.00 | 0.35 | 0.65 | 0.6534 | 1.0000 | 0.4796 |  |
| 9 | 0.00 | 0.00 | 0.40 | 0.60 | 0.6534 | 1.0000 | 0.4796 |  |
| 10 | 0.00 | 0.00 | 0.45 | 0.55 | 0.6534 | 1.0000 | 0.4796 |  |
| 11 | 0.00 | 0.05 | 0.00 | 0.95 | 0.8319 | 1.0000 | 0.4796 |  |
| 12 | 0.00 | 0.05 | 0.05 | 0.90 | 0.7641 | 1.0000 | 0.4796 |  |
| 13 | 0.00 | 0.05 | 0.10 | 0.85 | 0.7219 | 1.0000 | 0.4796 |  |
| 14 | 0.00 | 0.05 | 0.15 | 0.80 | 0.7168 | 1.0000 | 0.4796 |  |
| 15 | 0.00 | 0.05 | 0.20 | 0.75 | 0.7151 | 1.0000 | 0.4796 |  |
| 16 | 0.00 | 0.05 | 0.25 | 0.70 | 0.7143 | 1.0000 | 0.4796 |  |
| 17 | 0.00 | 0.05 | 0.30 | 0.65 | 0.7141 | 1.0000 | 0.4796 |  |
| 18 | 0.00 | 0.05 | 0.35 | 0.60 | 0.7141 | 1.0000 | 0.4796 |  |

**Chosen** (max balanced): α=0.10 β=0.25 γ=0.25 δ=0.40 · role-NDCG@10=0.9980 · role-P@10=0.4796 · label-AUC=0.7979
**Label-AUC winner** (feature 019: 0.20/0.75/0.05/0): label-AUC=0.9172 · role-NDCG@10=0.8314 · role-P@10=0.4521
**Legacy** (0.55/0.30/0.15/0): label-AUC=0.8614 · role-NDCG@10=0.8365 · role-P@10=0.4499

The two objectives favour different weights: optimizing label-AUC alone gives the β-heavy δ=0 row (high label-AUC, low role-NDCG → domain-mismatched top results); the role-aware objective restores α (GNN) + δ (domain) and lifts role-NDCG.

NOTE — circularity guard: a PURE role-NDCG objective is degenerate (δ=1.0 makes the score equal the relevance signal → role-NDCG=1.0 but label-AUC collapses to ~0.62, useless). The chosen row uses the **balanced** objective: max role-NDCG subject to label-AUC ≥ 0.85·max and δ ≤ 0.4 (domain stays a soft term).
