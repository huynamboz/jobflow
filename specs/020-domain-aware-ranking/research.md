# Phase 0 Research: Domain-Aware Match Scoring & Role-Aware Tuning

All resolved against the current source (continues feature 019). No open NEEDS CLARIFICATION.

## R1. The domain term in the score

**Decision**: `score = α·GNN + β·skill + γ·seniority + δ·domain`, added at BOTH blend sites in the engine (`_score_pair_fast` engine.py:738, `_gnn_score_fast` engine.py:920). `domain` = role match in `[0,1]`: `1.0` if `infer_role(cv.skills, cv.text) == job.role_category`, `0.5` if the job has no role label, else `0.0` — exactly the `domain_fit` from `_dimension_scores` (feature 019). `α+β+γ+δ=1`.

**Rationale**: The domain signal already exists (transparent, role-based) but was display-only. Promoting it to the score is the minimal, principled fix for the cross-domain leak. Reusing the same `domain_fit` definition keeps scoring and the per-dimension UI consistent.

**Alternatives**: Hard category filter — rejected (FR-002: over-prunes legit cross-role matches, e.g. fullstack→frontend). Re-weight toward GNN only — rejected (doesn't add the missing signal; still a magic number).

## R2. Why a SOFT term, not a filter

**Decision**: δ·domain down-weights mismatches but never removes them. A role mismatch costs `δ·1.0` of score; a strong skill+GNN match can still rank a sensible cross-role job.

**Rationale**: Roles overlap (fullstack ↔ frontend/backend; data ↔ ML). A hard filter on `role_category` equality would wrongly drop valid matches. Soft is standard in IR (category as a feature, not a gate).

## R3. Role-aware ranking metric (the tuning objective)

**Decision**: Treat each CV (cv_idx) as a query over its labeled validation jobs. A job is **relevant** to the CV if `infer_role(cv) == job.role_category`. Compute **precision@k** and **NDCG@k** (k=10) per CV, averaged over CVs with ≥1 relevant job. Select the 4-weight combo maximizing role-aware **NDCG@10** (precision@10 reported alongside).

**Rationale**: This metric rewards putting same-field jobs on top — exactly the user-visible goal the label-AUC missed. NDCG is the standard top-heavy ranking metric; precision@k is the intuitive companion.

**Alternatives**: Keep label-AUC as the objective — rejected (it caused the bug). MAP — comparable; NDCG chosen as the conventional default + already available.

## R4. The dual ablation (honesty / circularity mitigation)

**Decision**: For every weight combo report THREE numbers: label-AUC (independent of domain labels), role-aware NDCG@10, role-aware P@10. The winner is the role-aware-NDCG max; the table also flags the label-AUC max (feature-019 winner) and the legacy `(0.55,0.30,0.15,0)` row.

**Rationale**: The circularity worry — "domain is in both the score and the metric" — is mitigated by ALSO reporting label-AUC (which does not use role labels) and by the qualitative 20-CV eval (R6). The thesis story: optimizing label-AUC alone (β-heavy, δ=0) gives bad real ranking; the role-aware objective restores GNN weight and on-domain quality. Both objectives shown side-by-side = honest evidence (FR-009).

## R5. Per-pair components for tuning

**Decision**: Extend `engine.labeled_pair_components()` to also return, per labeled pair, the `domain` component (role match) and `(cv_role, job_role)`. The GNN/skill/seniority components stay as in feature 019. The role-aware metric uses `cv_role`/`job_role`; the 4-term score uses all four components.

**Rationale**: Components computed once; both objectives derive from the same per-pair record. `infer_role` runs on the checkpoint CV/job (engine loaded WITHOUT the live snapshot, `job_pool_dir` absent — identical to feature 019, so labels' training jobs stay in `self._jobs`).

## R6. Evaluation harness (face validity)

**Decision**: `eval_matching` command runs a FIXED set of ~20 diverse IT CVs (frontend/backend/devops/data/ML/mobile/QA/Java/.NET/Go/...) with realistic catalog skills through `match_cv_data` against the LIVE engine, printing per-CV top-K (title, score, dim_scores) and an **on-domain@k** rate = fraction of CVs whose #1 (and top-k) job is on-domain (`domain_fit ≥ 0.5`). A summary line gives the overall rate. Reproducible (CV set hard-coded in the command).

**Rationale**: The bug was found this way; making it first-class gives a regression guard + a reproducible thesis figure (before vs after). It judges face-validity independently of the tuned number (SC-001/002/006).

## R7. infer_role consistency

**Decision**: Use the SAME `ml_service.inference.role_classifier.infer_role` in (a) the score's domain term, (b) the role-aware metric, and (c) the eval's on-domain check. No second role definition.

**Rationale**: If scoring and the metric used different role logic, the optimization would chase an inconsistent target. One function = internally consistent.

## R8. Weight config (unchanged mechanism, now 4 numbers)

**Decision**: `metadata.json hybrid_weights` becomes `{alpha, beta, gamma, delta}`; `from_checkpoint` reads all four (delta defaults 0.0 if absent → backward compatible with feature-019 3-weight checkpoints). Single source of truth preserved (FR-008).

**Rationale**: Reuses the feature-019 loading path; `delta=0` makes old checkpoints behave exactly as before until re-tuned.
