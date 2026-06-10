# Contracts: commands & changed behaviors (021)

## NEW: `python manage.py dedup_jobs [--dry-run]`

Deduplicate active catalog rows by exact `(title, company_id)`.

- `--dry-run`: print the full plan (groups, keeper, rows to deactivate, manual-review groups) — NO writes.
- Keeper rule: HR-engaged row (status ∈ pursuing/applied/won/in_progress/completed/lost) > newest `created_at`. ≥2 engaged rows → all engaged kept, group reported for manual review.
- Writes: losers `is_active=False` only (reversible). Never deletes; never touches engaged rows.
- Output: groups processed, rows deactivated, kept-engaged count, manual-review list.
- Follow-up required: `rebuild_job_pool` (pool still contains deactivated jobs until rebuilt).

## CHANGED: `python backend/export_dataset.py …`

- Labels now deduplicated per pair (latest `created_at`, tie `id`). Output `labels.json` has UNIQUE `(cv_idx, job_idx)`.
- metadata.json gains `"dedup": "latest_per_pair"` and reports `num_dropped_duplicates`.

## CHANGED: `GraphBuilder.build(...)`

- Raises `ValueError("N conflicting (cv,job) label pairs …")` if any pair would get both match and no_match edges. Training scripts fail fast instead of training on contradictions.

## CHANGED: `engine.match_cv(...)` result contract

- Order: `rank_score = (reranker_score | stage1) × penalty_product` DESC.
- `JobMatchResult.score`: monotonic non-increasing with list order (display == order).
- No same-(title,company) repeats in the list returned by `match_cv_*` service wrappers (guard post-enrich).
- Reranker untrained → identical to previous behavior.

## CHANGED: trainer `_evaluate_split`

- Ranking metrics per-CV means (`num_cvs_evaluated` reported); AUC global; metadata `metrics_mode: "per_cv"`.

## CHANGED: `apps/labeling/prompts/pair_scoring.md`

- overall rule grid completed (skill=2 & domain=0 → 0); transferable-skill partial credit; full domain table (mobile/ba/other).
- Validation fixture: [rubric-tests.md](../rubric-tests.md) — 3 cases every labeler must pass before mass labeling.
