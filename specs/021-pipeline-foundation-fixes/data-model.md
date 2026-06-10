# Phase 1 Data Model: Pipeline Foundation Fixes

No DB schema changes. Contracts over existing data + in-memory structures.

## Entity 1 — Deduplicated label record (export gate)

`labels.json` row, post-0.2:

| Field | Rule |
|---|---|
| `(cv_idx, job_idx)` | **UNIQUE** across the file (was: 2,967 duplicates) |
| `label`, `overall`, dims, `split` | from the **latest** HumanLabel of that pair (`created_at` DESC, `id` DESC) |

Invariant enforced downstream: `GraphBuilder.build` raises if any (cv, job) would receive both `match` and `no_match` edges. DB `HumanLabel` rows are untouched (history kept).

## Entity 2 — Match result list (ordering contract)

`JobMatchResult` list returned by `engine.match_cv`:

| Property | Contract (post-0.3) |
|---|---|
| order | `rank_score = (reranker_score \| stage1_raw) × penalty_product` DESC |
| `score` (displayed) | monotonic non-increasing with order (rank_score normalized to display range per request) |
| `penalty_product` | exp gate ×0.40/×0.85 · sen gate ×0.70 · sen overqual ×0.75 (unchanged values, now applied to ORDER too) |
| fallback | reranker untrained → stage1 × P (today's exact behavior) |
| dedup (post-0.6) | at most one row per normalized (title, company) — guard in matching_service post-enrich |

## Entity 3 — JobData (live pool, post-0.1)

Adds previously-dropped fields from `Job`:

| Field | Source | Effect restored |
|---|---|---|
| `experience_min` | `Job.experience_min or 0.0` | under-qual gate (×0.40), over-qual (×0.85), `experience_fit` dim |
| `experience_max` | `Job.experience_max` | (carried for completeness) |

Note (A13): 48% of jobs have no experience data → neutral for those; the gate works for the other half.

## Entity 4 — Job catalog dedup states (0.6)

Per active (title, company_id) group with >1 rows:

```
engaged_rows = rows with EmployeeJobMatch.status ∈ {pursuing, applied, won, in_progress, completed, lost}
├─ 0 engaged → keeper = newest created_at; others is_active=False
├─ 1 engaged → keeper = that row;          others is_active=False
└─ ≥2 engaged → ALL engaged stay active; non-engaged deactivated; group logged for manual review
```
`dismissed`/`suggested` matches do NOT count as engagement (suggested are re-pruned on next rematch). Reversible: re-activate by setting `is_active=True`.

## Entity 5 — Per-CV evaluation record (0.4)

`_evaluate_split` output:

| Key | Semantics |
|---|---|
| `auc_roc` | global (all pairs) — unchanged |
| `precision@k, recall@k, ndcg@k, mrr, hit_rate@k` | **mean over CVs** with ≥1 positive and ≥2 labeled pairs, each computed within that CV's labeled set |
| `num_cvs_evaluated` | NEW — contributing CV count |
| metadata `metrics_mode` | `"per_cv"` — marks old numbers non-comparable |

## Entity 6 — Rubric (0.5) — patched scoring contract

- overall hard rules now total-cover the (skill_fit, domain_fit) grid: skill=0→0 · skill≥1&domain=0→0 · skill=2&domain≥1&sen≥1→2 · skill=1&domain≥1→1 · else judgment.
- skill coverage counts equivalent/transferable skills at partial (≈half) credit, with named examples.
- domain table covers all 11 role values (mobile↔mobile=2, ba↔ba=2, other↔other=1, mobile↔frontend=1 added).
- 3 canonical test cases in [rubric-tests.md](rubric-tests.md) — must pass for any labeler (LLM or agent) before mass labeling.

## Entity 7 — Post-fix baseline (0.7)

Recorded in `docs/codebase-knowledge/10-master-plan.md` (Đợt 0 section): eval_matching `top1_on_domain` + `mean on_domain@5`, test-suite counts, honest per-CV checkpoint metrics, date. Reference point for Đợt 1-2.
