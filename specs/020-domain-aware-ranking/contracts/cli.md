# Contract: tune_hybrid_weights (4-weight, dual metric) + eval_matching

## `tune_hybrid_weights` (extended)

`python manage.py tune_hybrid_weights [--grid 0.05] [--val-frac 0.2] [--seed 42] [--objective role_ndcg] [--write] [--out specs/020-domain-aware-ranking/ablation.md]`

**Behaviour**:
1. Load engine without the live snapshot; `labeled_pair_components()` now also returns `domain` + roles.
2. Sweep `α+β+γ+δ=1` on the `--grid` lattice.
3. Per combo compute: **label-AUC** (match/no_match), **role-NDCG@10** + **role-P@10** (relevant = `infer_role(cv)==job.role_category`, grouped by cv over the val split).
4. Select the combo maximizing the `--objective` (default `role_ndcg`); tie-break toward a balanced/closer-to-legacy combo.
5. Write the **dual ablation table** (`--out`); flag chosen / label-AUC-max / legacy rows.
6. `--write` persists the winner's 4 weights + the three metrics to `metadata.json`.

**New flags**: `--objective` (`role_ndcg` default | `role_p` | `label_auc`), `--k` (default 10). Existing `--grid/--val-frac/--seed/--write/--out` unchanged.

**Exit**: non-zero on single-class label split or no role-labeled jobs in validation.

## `eval_matching` (NEW)

`python manage.py eval_matching [--k 5]`

**Behaviour**: run a FIXED, hard-coded set of ~20 diverse IT CVs through `match_cv_data(top_k=k)` against the LIVE engine; print per-CV the role + top-k (title, score, dim_scores) + whether the #1 is on-domain; print a summary: `top1_on_domain` rate and mean `on_domain@k`. Reproducible (CV set in code).

**Output (example)**:
```
Backend (Python/Django)  | Senior Backend Engineer (0.81·dm1.0) || ...   on-domain
...
SUMMARY: top1_on_domain = 19/20 (95%) · mean on_domain@5 = 0.86
```

**Use**: run before (δ=0) and after (tuned δ) to evidence SC-001/002/006.

## Weight config

`metadata.json hybrid_weights` = `{alpha, beta, gamma, delta}` (delta defaults 0.0 if absent). `from_checkpoint` reads all four; single source of truth (feature 019). No second definition.
