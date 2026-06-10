# Phase 0 Research: Pipeline Foundation Fixes

All findings pre-verified in [09-pipeline-audit.md](../../docs/codebase-knowledge/09-pipeline-audit.md). This file records the DECISIONS for the ambiguous points.

## R1. Label dedup policy (0.2)

**Decision**: Per `pair_id`, keep the single latest `HumanLabel` — order `created_at` DESC, tie-break `id` DESC. Implemented at EXPORT (the train-data gate), not by deleting DB rows (history preserved).

**Rationale**: Re-labeling semantics = newer judgment supersedes older (Đợt 1 will re-label bad slices with the patched rubric — those must win). Majority-vote rejected: with 2 labels and a conflict there is no majority, and old-rubric labels shouldn't outvote new-rubric ones.

**Alternatives**: majority vote (rejected above); drop conflicting pairs entirely (wastes ~284 informative pairs; the newest label is the best estimate).

## R2. Conflict guard placement (0.2)

**Decision**: `GraphBuilder.build` raises `ValueError` listing the count of (cv, job) pairs that would receive both `match` and `no_match` edges. Loud failure, not a warning.

**Rationale**: A silent warning was effectively what we had (nothing) — the graph was corrupted invisibly. Post-dedup the count must be 0; any non-zero means an upstream regression and training MUST NOT proceed.

## R3. Final-order semantics (0.3)

**Decision**: For each candidate, collect the penalty product `P` while applying gates (exp under-qual ×0.40, exp over-qual ×0.85, sen gate ×0.70, sen overqual ×0.75 — unchanged values). Then:

```
rank_score = (reranker_score if reranker trained else stage1_raw) × P
final order = sort by rank_score desc
displayed score = rank_score normalized to the display range (existing calibration), so display is monotonic with order BY CONSTRUCTION
```

**Rationale**: This restores the designed two-stage architecture (stage-2 decides order) while keeping the documented business gates effective (they demote within that order). Display==order eliminates the non-monotonic UI confusion. Fallback path (no reranker) = stage-1 × P = exactly today's behavior, so degraded mode is unchanged.

**Alternatives**: (a) keep stage-1 order, drop reranker → abandons the trained component and the architecture claim; (b) apply penalties before rerank as features → requires reranker retrain (Đợt 2, not here); (c) two numbers (order by reranker, display stage-1) → exactly the confusing status quo.

**Display normalization detail**: reranker ordinal scores live in ~[0, 0.6] historically (match_level thresholds 0.22/0.30). To keep UI percentages meaningful, map rank_score through min-max over the returned candidate set onto the stage-1 display range observed in the same set (preserves the familiar 0.4-0.99 spread). Simple, per-request, no global state.

## R4. Per-CV metrics (0.4)

**Decision**: `_evaluate_split` groups by `cv_id`; CVs with ≥1 positive AND ≥2 labeled pairs contribute precision@k/recall@k/NDCG@k/MRR/hit-rate computed within their own labeled candidate set; report the mean over contributing CVs + `num_cvs_evaluated`. AUC stays global (pairwise separation is well-defined globally). Metadata gains `"metrics_mode": "per_cv"`.

**Rationale**: Mirrors production (rank per CV) and the role-aware metric design already used in `tune_hybrid_weights._role_metrics` (consistent methodology). Old checkpoint numbers are declared non-comparable rather than renamed keys everywhere (smaller blast radius).

## R5. Rubric patch contents (0.5)

**Decision**:
- (a) Overall hard rule added: `skill_fit = 2 AND domain_fit = 0 → overall = 0` (cross-field is not a placement match regardless of skill overlap; transferable adjacency is already represented by domain_fit=1).
- (b) skill_fit text: "count a required skill as PARTIALLY covered (≈half credit) when the CV has a clearly equivalent/transferable skill" + examples: Flask≈Django, Vue≈React, MySQL≈PostgreSQL, GCP≈AWS, GitLab CI≈Jenkins. Keeps the 0/1/2 thresholds; changes what counts as coverage.
- (c) Domain table completed: same-domain adds `mobile↔mobile=2, ba↔ba=2, other↔other=1` (other is a grab-bag — same-bag is weak evidence, so 1 not 2); related adds `mobile↔frontend=1`.
- 3 written test cases in `rubric-tests.md` (one per patch) — also the validation fixture for the Đợt-1 agent labeler.

**Rationale**: (a) closes the measured 43%-noise gap; (b) un-blinds the ground truth to related-skill matches (the GNN's core advantage — currently structurally impossible); (c) DB has 3 mobile CVs + 186 mobile jobs and 3 ba CVs that currently CANNOT score domain ≥ 1 against themselves.

## R6. Duplicate-job cleanup (0.6)

**Decision**: Management command `dedup_jobs` over ACTIVE jobs grouped by exact `(title, company_id)`:
- keeper = the row with HR-engaged matches (status ∈ pursuing/applied/won/in_progress/completed/lost); if none → newest `created_at`;
- if MULTIPLE rows engaged → keep all engaged rows active, log group for manual review (never orphan engagement);
- losers: `is_active=False` (reversible), their SUGGESTED matches are pruned naturally on next re-match (persist prune already handles vanished jobs);
- `--dry-run` default-off flag prints the full plan first.

Serving guard: in `matching_service` after `_enrich` (company name available there), drop result rows whose normalized `(title.lower().strip(), company_name.lower().strip())` was already emitted. Engine stays dedup-free (it lacks company info).

**Rationale**: Exact-match definition is conservative (no fuzzy false-merges); engagement check protects HR workflow; soft deactivate is the codebase's existing convention; the guard catches future dupes the cleanup misses (cross-company-spelling variants are out of scope).

## R7. Execution order & blast control

**Decision**: 0.1 → 0.2 → 0.5 (independent, data-side) → 0.3 (biggest behavior change) → 0.4 → 0.6 → 0.7 (rebuild pool once at the end, then eval + tests + baseline docs). Server restart at the very end only.

**Rationale**: Matches master-plan ordering; one pool rebuild instead of two (0.1 and 0.6 both want it); eval comparison done once against the fully fixed pipeline.
