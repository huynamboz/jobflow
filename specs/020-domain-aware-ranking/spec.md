# Feature Specification: Domain-Aware Match Scoring & Role-Aware Weight Tuning

**Feature Branch**: `020-domain-aware-ranking`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Top matches surface domain-mismatched jobs (a backend CV ranked against VFX jobs that merely list 'python'). Bring the role/domain signal into the score, tune the weights on a metric that reflects real ranking quality, and prove it with an evaluation harness."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - On-domain matches at the top (Priority: P1)

HR opening an employee's job list sees jobs that fit the employee's **field**, not jobs that merely share a stray keyword. A backend engineer's top matches are backend/software roles — never animation or VFX jobs that happen to require "python".

**Why this priority**: This is the visible quality bug. A 20-CV evaluation showed IT CVs surfacing VFX/animation/social-media jobs at the top (coincidental skill overlap, wrong field). HR loses trust the moment they see an obviously-irrelevant job ranked #1. Everything else is in service of this.

**Independent test**: Run a fixed diverse set of IT CVs through the matcher → for each, the top-K jobs share the CV's field; the cross-domain noise (VFX/animation for software CVs) is gone.

**Acceptance Scenarios**:

1. **Given** a backend/software CV, **When** it is matched, **Then** its top results are software/engineering roles, not animation/VFX/non-tech roles that only share a keyword.
2. **Given** a job that shares a skill with the CV but is in a different field, **When** ranking is computed, **Then** that job is ranked below same-field jobs (down-weighted, not necessarily removed).
3. **Given** a legitimately cross-role match (e.g. a fullstack engineer for a frontend role), **When** ranking is computed, **Then** it is NOT removed — domain is a soft signal, not a hard filter.

---

### User Story 2 - Weights chosen on a metric that reflects real quality (Priority: P2)

The candidate can show that the score weights were selected to maximize a metric aligned with the real goal — relevant top-K results per CV — not just a pairwise label statistic that misses domain relevance, and can present a side-by-side comparison of the two.

**Why this priority**: The earlier weights were tuned on a metric (label-AUC) that did not penalize domain mismatch, which is exactly why the bug appeared. Selecting weights on a role-aware ranking metric fixes the root cause and gives the thesis a rigorous, honest story.

**Independent test**: The tuner reports BOTH a label-separation metric and a role-aware ranking metric across weight combinations; the chosen weights maximize the role-aware metric, and the comparison shows the two metrics favor different weights.

**Acceptance Scenarios**:

1. **Given** the labeled data + role information, **When** tuning runs, **Then** it outputs a dual-metric ablation table (label-separation AND role-aware ranking) across weight combinations.
2. **Given** the dual ablation, **When** the candidate compares, **Then** the role-aware objective assigns a meaningfully non-trivial weight to the semantic (graph) signal, unlike the label-AUC-only objective.

---

### User Story 3 - A repeatable matching-quality evaluation (Priority: P3)

There is a repeatable way to run a fixed, diverse set of representative CVs through the live matcher and read a quality report (per-CV top results + an on-domain rate), so quality regressions are caught and the thesis has reproducible evidence.

**Why this priority**: The bug was only found because of an ad-hoc 20-CV test. Making that a first-class, repeatable evaluation turns a one-off into an ongoing guardrail and a citable artifact.

**Independent test**: Run the evaluation → it prints, for each representative CV, its top-K jobs and whether they are on-domain, plus a summary on-domain rate; re-running reproduces the same report.

**Acceptance Scenarios**:

1. **Given** the evaluation harness, **When** it runs, **Then** it reports per-CV top-K jobs + an on-domain@K rate and a summary.
2. **Given** the harness after the scoring fix, **When** compared to before, **Then** the on-domain rate is materially higher.

---

### Edge Cases

- **Job with no role/domain label**: domain contributes a neutral value (neither rewards nor penalizes), so unlabeled jobs aren't unfairly buried.
- **Genuinely cross-role candidate** (fullstack ↔ frontend/backend): soft down-weight only, never removed.
- **CV whose role can't be inferred**: domain term degrades to neutral; ranking still works on the other signals.
- **Weights that ignore domain** appearing best on label-AUC: surfaced in the dual table as the cautionary contrast, not adopted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The overall match score MUST incorporate the role/domain match as a contributing signal (a soft term), alongside the existing semantic, skill, and seniority signals.
- **FR-002**: Domain MUST be a soft signal that down-weights field-mismatched jobs, NOT a hard filter that removes them (legitimate cross-role matches must survive).
- **FR-003**: The score weights MUST be selected to maximize a role-aware ranking-quality metric (relevant = shares the CV's field), on held-out data.
- **FR-004**: Weight selection MUST produce a dual-metric ablation table reporting BOTH the label-separation metric and the role-aware ranking metric across weight combinations.
- **FR-005**: There MUST be a repeatable evaluation that runs a fixed, diverse set of representative CVs through the matcher and reports per-CV top-K results + a summary on-domain rate.
- **FR-006**: After the change, a software/IT CV's top results MUST be on-domain (no animation/VFX/non-tech jobs ranked top from coincidental keyword overlap).
- **FR-007**: The selected weights MUST keep a meaningfully non-trivial contribution from the semantic (graph) signal (i.e. the role-aware objective restores it relative to the label-AUC-only result).
- **FR-008**: The change MUST remain weight-config consistent (single source of truth, from the prior feature) and MUST NOT retrain the learned models.
- **FR-009**: The honesty caveats MUST be documented: the role-aware relevance is a heuristic ground-truth; the independent label-separation metric and the qualitative CV evaluation are reported alongside to mitigate circularity.

### Key Entities *(include if feature involves data)*

- **Domain/role signal**: the field-match between a CV's inferred role and a job's role/domain — promoted from a display-only diagnostic to a scoring contributor.
- **Role-aware ranking metric**: precision@k / NDCG@k where a job is relevant to a CV if they share a field; the tuning objective.
- **Dual ablation table**: weight combination → (label-separation metric, role-aware ranking metric) — the thesis artifact contrasting the two objectives.
- **Evaluation CV set**: a fixed, diverse set of representative IT CVs used by the repeatable quality evaluation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the fixed evaluation CV set, the on-domain rate of top-K results increases materially after the change (target: ≥90% of CVs have an on-domain top result, up from the pre-change baseline).
- **SC-002**: Zero software/IT CVs in the evaluation set return an animation/VFX/non-tech job as their #1 match.
- **SC-003**: The selected weights assign a non-trivial weight to the semantic (graph) signal (target: clearly above the label-AUC-only result's near-zero).
- **SC-004**: The dual-metric ablation table exists and shows the label-only and role-aware objectives favoring different weights.
- **SC-005**: The evaluation is reproducible — re-running yields the same report.
- **SC-006**: Legitimate cross-role matches are retained (a fullstack CV still matches frontend/backend roles) — domain did not act as a hard filter.

## Assumptions

- Jobs carry a role/domain label sufficient to judge field-match (the existing `role_category`); CV role is inferable from skills/text.
- The learned models (graph encoder + reranker) stay frozen; only the combination weights and the scoring formula change.
- A held-out split of the labeled data + the role labels are enough to compute and optimize the role-aware metric.
- "On-domain" for the evaluation is judged by role/field agreement between CV and job.
- The penalty/gate business rules and the single-source weight config from the prior feature remain in place.

## Dependencies

- The transparent per-dimension role/domain diagnostic from the prior feature (now promoted into the score).
- The existing weight-tuning + single-source-config mechanism from the prior feature (extended to four weights + the new metric).
- The labeled pairs + role labels used for tuning and evaluation.
