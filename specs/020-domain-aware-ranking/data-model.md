# Phase 1 Data Model: Domain-Aware Match Scoring & Role-Aware Tuning

No database schema changes. Touches the weight record (metadata), the tuner's in-memory pair record, and two new artifacts.

## Entity 1 — Hybrid weight record (now four weights)

`checkpoints/latest/metadata.json`:
```json
{ "hybrid_weights": { "alpha": 0.40, "beta": 0.25, "gamma": 0.10, "delta": 0.25 },
  "hybrid_weights_meta": { "objective": "role_ndcg@10", "role_ndcg": 0.0, "role_p@10": 0.0,
                           "label_auc": 0.0, "grid_step": 0.05 } }
```
**Rules**: `alpha+beta+gamma+delta == 1.0` (tolerance); each `≥ 0`. `from_checkpoint` reads all four; `delta` defaults `0.0` when absent (feature-019 checkpoints behave unchanged). Single source of truth.

## Entity 2 — Labeled pair record (extended)

`engine.labeled_pair_components()` returns per labeled pair:

| Field | Meaning |
|---|---|
| `cv_idx`, `job_idx`, `label` | as feature 019 (label = match/no_match) |
| `gnn`, `skill`, `seniority` | the three components (feature 019) |
| `domain` | **NEW**: role match `1.0/0.5/0.0` = `infer_role(cv)` vs `job.role_category` |
| `cv_role`, `job_role` | **NEW**: the inferred CV role + the job role label (for the role-aware metric) |

Computed once; both objectives derive from it.

## Entity 3 — Dual ablation table (thesis artifact)

`specs/020-domain-aware-ranking/ablation.md`. One row per `(α,β,γ,δ)` combo:

| α | β | γ | δ | label-AUC | role-NDCG@10 | role-P@10 | note |
|---|---|---|---|-----------|--------------|-----------|------|

Sorted by role-NDCG@10 desc. Flags: **chosen** (role-NDCG max), the **label-AUC max** (feature-019 winner, contrast), and the **legacy** `(0.55,0.30,0.15,0)` row.

## Entity 4 — On-domain evaluation report

Produced by `eval_matching`. Per CV in the fixed set:

| Field | Meaning |
|---|---|
| `cv_role` | the CV's field (frontend/backend/devops/…) |
| `top_k` | list of (job title, score, domain_fit) |
| `top1_on_domain` | bool — is the #1 job on-domain (`domain_fit ≥ 0.5`)? |
| `on_domain@k` | fraction of the top-k that is on-domain |

Summary: overall `top1_on_domain` rate + mean `on_domain@k` across CVs (SC-001/002).

## Entity 5 — Four-term score (runtime)

At both blend sites: `display_score = α·gnn + β·skill + γ·seniority + δ·domain`, where `domain = _dimension_scores(...)['domain_fit']` (or the same role-match computed inline). Soft — no candidate is removed for a low `domain`. The penalty/gates (experience/seniority) still apply afterwards, unchanged.

## Flow

```text
labeled pairs (+domain, +roles)              fixed 20-CV set
   │ sweep α+β+γ+δ=1 (0.05)                      │ match_cv_data (live engine, 4-term score)
   ▼                                             ▼
dual ablation (label-AUC, role-NDCG, role-P)   per-CV top-K + on-domain@k
   │ winner → metadata.json (4 weights)          │ summary on-domain rate
   ▼                                             ▼
engine loads 4 weights → δ·domain in score → eval confirms cross-domain noise gone
```
