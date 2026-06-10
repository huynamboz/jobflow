# Feature Specification: Defense-Ready Match-Weight Calibration & Transparent Dimension Scores

**Feature Branch**: `019-match-weight-calibration`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Make every number in the matcher justifiable to a thesis committee — tune the hybrid weights on a labeled validation set, unify the weight config, and make the per-dimension fit scores transparent formulas."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Weights chosen by evidence, not by hand (Priority: P1)

The candidate must justify the relative importance given to the GNN signal vs skill overlap vs seniority when combining them into the overall match score. Instead of "I picked these numbers", they can show that the weights were **selected on a held-out labeled validation set** to maximize a stated ranking metric, and present an **ablation table** comparing weight combinations.

**Why this priority**: A thesis committee's first attack on a scoring formula is "where do those weights come from?". Hand-set weights are the single biggest defense liability; a documented, reproducible selection procedure converts it into a strength. Everything else is secondary.

**Independent test**: Re-run the calibration procedure on the labeled data → it outputs a chosen weight combination plus an ablation table (each combination → metric), and the chosen one is the metric-maximizing entry.

**Acceptance Scenarios**:

1. **Given** the labeled match/no-match pairs, **When** the calibration runs, **Then** it reports a chosen (GNN, skill, seniority) weight set and the validation metric it achieves.
2. **Given** the calibration output, **When** the candidate opens the ablation table, **Then** they can see how the metric changes across weight combinations and that the chosen set is the best.
3. **Given** the chosen weights, **When** ranking quality is measured on the validation set, **Then** it is at least as good as the previous hand-set weights.

---

### User Story 2 - One consistent source for the weights (Priority: P2)

There is exactly one place the matcher's combination weights are defined, and the running system uses precisely those values — no second, contradictory definition anywhere in the codebase.

**Why this priority**: Today two different weight values exist in the code (an ignored config vs the engine's own defaults). If a committee member reads the code, the contradiction undermines credibility. Resolving it is cheap and removes a clear vulnerability.

**Independent test**: Search the codebase for the combination weights → there is a single authoritative definition, and the value the engine actually applies equals it.

**Acceptance Scenarios**:

1. **Given** the codebase, **When** one inspects where the combination weights are set, **Then** there is a single source of truth.
2. **Given** the running matcher, **When** it computes the overall score, **Then** the weights it uses equal the single authoritative (tuned) values.

---

### User Story 3 - Every dimension score is explainable by hand (Priority: P3)

The four per-dimension fit scores shown to HR (skill / experience / seniority / domain) are each computed by a **transparent, documented formula** from the match's own data — so the candidate can reproduce any displayed number on paper and explain exactly what it measures, with no dependency on an unexplained learned label.

**Why this priority**: The per-dimension bars are an *explainability* feature. If they come from a learned component whose ground-truth labels can't be sourced, the committee question "what is the ground truth for skill fit?" is unanswerable. Transparent formulas make the diagnostics fully defensible while leaving the learned GNN+reranker as the ranking core.

**Independent test**: For a displayed match, take its matched/required skills, experience gap, seniority distance, and role match, apply the documented formulas by hand → the four numbers equal those shown in the UI.

**Acceptance Scenarios**:

1. **Given** a match's skills/seniority/experience/role data, **When** the documented dimension formulas are applied by hand, **Then** the results equal the four per-dimension scores shown in the UI.
2. **Given** the matcher, **When** it produces per-dimension scores, **Then** none of them depends on the previously-learned auxiliary labels of unknown provenance.

---

### Edge Cases

- **A job lists no required skills**: skill fit is defined (e.g. treated as full or neutral) rather than dividing by zero.
- **Experience requirement unknown on the job**: experience fit falls back to a neutral value rather than penalizing.
- **Role/domain not labeled on the job**: domain fit falls back to neutral.
- **Tie in the weight search**: a deterministic tie-break yields the same chosen weights on every run.
- **Tuned weights equal the old ones**: acceptable — the value is the evidenced selection process, not necessarily a different number.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The combination weights (GNN / skill / seniority) MUST be selected by a documented, reproducible procedure on a held-out labeled validation set that maximizes a stated ranking-quality metric.
- **FR-002**: The procedure MUST output an ablation table (each weight combination → metric) suitable for inclusion in the thesis and slides.
- **FR-003**: There MUST be a single authoritative definition of the combination weights; the matcher MUST use exactly those values, with no contradictory second definition remaining in the codebase.
- **FR-004**: Each per-dimension fit score (skill / experience / seniority / domain) MUST be computed by a transparent, documented formula from the match's own data, reproducible by hand.
- **FR-005**: The admin UI MUST keep showing the four per-dimension percentage bars; the values are now formula-backed (shape/placement unchanged).
- **FR-006**: Ranking quality on the validation set with the selected weights MUST be no worse than with the previous hand-set weights.
- **FR-007**: The calibration MUST be reproducible: re-running it on the same data yields the same chosen weights and metrics (fixed split / deterministic).
- **FR-008**: The per-dimension formulas MUST NOT depend on the previously-learned auxiliary labels whose provenance is unknown.

### Key Entities *(include if feature involves data)*

- **Combination weights**: the three numbers blending the learned GNN score, skill overlap, and seniority alignment into the overall match score. The subject of the tuning + unification.
- **Labeled validation set**: held-out match / no-match pairs used to score weight combinations (the same labels behind model training).
- **Ablation table**: the record of weight combination → validation metric, the defense artifact.
- **Per-dimension diagnostics**: skill fit, experience fit, seniority fit, domain fit — each a transparent function of the match's skills/experience/seniority/role data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The chosen combination weights are backed by an ablation table covering the weight grid, with the selected entry being the metric-maximizing one.
- **SC-002**: Zero contradictory definitions of the combination weights remain in the codebase (single source of truth).
- **SC-003**: Each of the four per-dimension scores for a sample match can be reproduced by hand from the match's displayed data to within rounding.
- **SC-004**: The selected weights achieve a validation ranking metric ≥ that of the previous hand-set weights.
- **SC-005**: Re-running the calibration reproduces the same chosen weights and reported metric (deterministic).
- **SC-006**: A reviewer can answer "where does each number come from?" for the overall weights and all four dimension scores using only the documentation + ablation table.

## Assumptions

- The labeled match/no-match pairs already exist and are representative enough to select weights (same data used for model training).
- The learned GNN and reranker stay frozen — this feature only changes how their outputs are *combined* and how dimensions are *displayed*, not the models.
- The penalty/gate factors (experience/seniority hard guards) remain documented domain business-rules and are out of scope for tuning.
- "Ranking quality metric" defaults to AUC on the validation pairs, optionally complemented by NDCG / precision@k; the exact metric is stated in the procedure.
- The per-dimension formulas use data already available on each match (matched/required skills with importances, experience gap, seniority distance, role/domain match).

## Dependencies

- The existing labeled dataset (match/no-match pairs) and the trained GNN whose scores feed the combination.
- The existing admin "Why it matches" surface that displays the per-dimension bars.
