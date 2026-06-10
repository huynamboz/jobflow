# Implementation Plan: Pipeline Foundation Fixes (Đợt 0)

**Branch**: `021-pipeline-foundation-fixes` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/021-pipeline-foundation-fixes/spec.md`

## Summary

Fix the seven audited foundation bugs (master plan Đợt 0, audit A1-A9 in [09-pipeline-audit.md](../../docs/codebase-knowledge/09-pipeline-audit.md)) before the Đợt-1 relabel and Đợt-2 retrain:

1. **0.1/A1** — pass `experience_min/max` into the live `JobData` pool (gate + experience_fit revive).
2. **0.2/A2** — dedup labels at export (latest-wins per pair) + a conflict guard in `GraphBuilder.build`.
3. **0.3/A3** — final order = **reranker score × penalty factors**; displayed score monotonic with order.
4. **0.4/A7** — per-CV ranking metrics in the trainer (AUC stays global); re-evaluate the checkpoint once for honest numbers.
5. **0.5/A4-A6** — patch the labeling rubric (overall rule gap, transferable-skill credit, complete domain table) + 3 rubric test cases.
6. **0.6/A9** — `dedup_jobs` command (guarded, reversible) + serving-time (title, company) dedup guard.
7. **0.7** — rebuild pool, run eval + tests, record the post-fix baseline in the docs.

## Technical Context

**Language/Version**: Python 3.11 (backend `.venv`), Django 5.2

**Primary Dependencies**: PyTorch/PyG (engine), numpy; no new dependencies

**Storage**: PostgreSQL (Job.is_active soft-deactivation; HumanLabel read-only here); `checkpoints/job_pool/` snapshot (rebuilt); `checkpoints/latest` untouched (no retrain)

**Testing**: `manage.py test apps.matching apps.employees apps.jobs` + new unit tests (export dedup, graph guard, ordering monotonicity, per-CV metrics, serving dedup)

**Target Platform**: backend only — no frontend changes (UI already renders score/dims; only ordering/score semantics improve)

**Project Type**: Django backend + ml_service library

**Performance Goals**: no measurable serving slowdown (dedup guard is O(k) on the returned list; final-order change is arithmetic already computed)

**Constraints**: no retrain/relabel here; checkpoint stays frozen; Job deactivation must never orphan HR-engaged matches; ordering change is intended and documented

**Scale/Scope**: 6.5k active jobs (731 rows to deactivate), 11.6k labels → ~8.6k after dedup, ~20 touched-file edits + 1 new management command

## Constitution Check

Constitution is an unfilled template → **PASS**. Guardrails: destructive DB op behind `--dry-run` + engagement check + reversible `is_active`; loud failure (raise) on conflicting label edges; behavior changes covered by tests; docs updated in the same feature.

## Project Structure

### Documentation (this feature)

```text
specs/021-pipeline-foundation-fixes/
├── plan.md
├── research.md          # decisions: dedup policy, final-order semantics, dup-job keeper rule
├── data-model.md        # label record after dedup, result-order contract, job dedup states
├── quickstart.md        # run order + verification commands per fix
├── contracts/cli.md     # dedup_jobs command + changed export/eval behavior
├── rubric-tests.md      # 3 written rubric test cases (validation fixture for Đợt-1 labeler)
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── apps/matching/services/matching_service.py   # 0.1 JobData exp fields · 0.6 serving dedup guard (post-enrich)
├── export_dataset.py                             # 0.2 per-pair latest-wins dedup
├── ml_service/graph/builder.py                   # 0.2 conflict guard (raise on match∧no_match)
├── ml_service/inference/engine.py                # 0.3 final_rank_score = reranker×penalties; monotonic score
├── ml_service/training/trainer.py                # 0.4 per-CV _evaluate_split
├── apps/labeling/prompts/pair_scoring.md         # 0.5 rubric patches (a)(b)(c)
├── apps/jobs/management/commands/dedup_jobs.py   # 0.6 NEW: guarded catalog dedup (--dry-run)
└── apps/*/tests.py                               # new unit tests per fix
docs/codebase-knowledge/                          # 06 ordering semantics · 09 mark fixed · 10 baseline
```

**Structure Decision**: Backend-only surgical fixes; one new management command; no schema migration (uses existing `is_active`). The serving dedup guard lives in `matching_service` (post-`_enrich`, where company name is available — the engine only knows titles).

## Key Design Decisions (summary — full rationale in research.md)

1. **Label dedup policy**: per `pair_id`, keep the LATEST HumanLabel (`created_at` desc, `id` desc). Newer judgment supersedes — matches Đợt-1 relabel semantics. Builder still guards (raise) so dirty inputs can never silently corrupt a graph again.
2. **Final-order semantics**: collect each candidate's penalty product (exp ×0.40/×0.85, sen ×0.70, overqual ×0.75) once; `final_rank_score = (reranker_score if trained else stage1_score) × penalty_product`; sort by it; **displayed score = stage-1 display_score** as today BUT emitted list re-scored to be monotonic by construction — we set `score = final_rank_score` rescaled via the existing Platt calibration range so UI percentages stay comparable. Fallback (no reranker) = current behavior.
3. **Duplicate-job keeper rule**: per (title, company_id) active group — keeper = row with HR-engaged matches (pursuing/applied/won/in_progress/completed/lost), else newest `created_at`; >1 engaged rows → keep all engaged, report for manual review. Deactivation only (`is_active=False`), reversible.
4. **Per-CV metrics**: group by cv; CVs with ≥1 positive and ≥2 labeled pairs enter ranking means; AUC global; metric keys unchanged but metadata gains `"metrics_mode": "per_cv"` and docs note the semantics change (old numbers not comparable).

## Complexity Tracking

No constitution violations. The only behavioral risk is 0.3 (ordering change) — mitigated by: monotonicity unit test, eval_matching before/after comparison in 0.7, and the documented decision in docs 06.
