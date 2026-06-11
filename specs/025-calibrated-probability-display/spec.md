# Feature Specification: Calibrated Probability Display

**Feature Branch**: `025-calibrated-probability-display`

**Created**: 2026-06-12

**Status**: Draft

**Input**: User description: "Replace the per-basket relative score remap with an absolute, globally-comparable calibrated probability — completing the calibration layer the codebase already scaffolded but never wired."

## Problem Statement

Today the match percentage shown for each employee↔job pair is **relative to that
employee's own result basket**: the ranking signal is stretched onto the value
range of whatever jobs happen to be in that day's results. Three user-facing
consequences:

1. **Not comparable across employees** — "92% for A" vs "87% for B" carries no
   meaning (documented as a standing caveat that HR must be warned about).
2. **Not stable over time** — the same employee↔job pair can show a different
   percentage tomorrow purely because *other* jobs entered or left the basket.
3. **Not interpretable** — the number answers "where does this job sit inside
   this basket?" rather than "how likely is this a genuine match?", which is
   what HR actually asks.

The system already contains a dormant calibration layer (fitted at training
time, stored with the model, loaded at startup) that was designed to solve
exactly this — it was never connected to the displayed score, and its fitting
procedure does not converge, producing unusable output.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One comparable score scale across all employees (Priority: P1)

As an HR user, when I look at match percentages on two different employees'
pages, I want the numbers to mean the same thing, so I can tell at a glance
which employee↔job pairs across my whole roster are the strongest to pursue.

**Why this priority**: This is the core semantic fix — every other benefit
(stability, interpretability, future per-employee pools) derives from making
the score absolute. It also removes a documented caveat that currently has to
be explained to every new user.

**Independent Test**: Pick the top job of employee A and the top job of
employee B. Confirm with ground-truth-style review (dimension scores, skills)
that the pair shown with the higher percentage is genuinely the stronger match.
Repeat for mid-list jobs.

**Acceptance Scenarios**:

1. **Given** two employees with parsed CVs, **When** HR views both match lists,
   **Then** percentages across the two lists sit on one scale (a higher number
   anywhere means a higher likelihood of genuine match).
2. **Given** the same employee↔job pair evaluated on two different days with no
   change to the CV, the job, or the model, **When** HR compares the displayed
   percentage, **Then** it is identical (no drift from unrelated catalog
   changes).
3. **Given** a match list, **When** HR opens "How this score is computed",
   **Then** the explanation chain accounts for the displayed number exactly
   (no unexplained final stretch step).

### User Story 2 - Ranking order is preserved exactly (Priority: P1)

As the system owner, I need the new display to change **only the numbers, not
the order** — the ranking quality achieved (100% on-domain across four
evaluation suites) must be provably untouched.

**Why this priority**: The ranking pipeline is verified and in production;
a display-layer change must not be able to regress it.

**Independent Test**: For every employee, capture the ranked job-ID sequence
before and after the change; the sequences must be identical.

**Acceptance Scenarios**:

1. **Given** the pre-change ranked job list for each employee, **When** the new
   display is enabled and matches are recomputed, **Then** the job order is
   identical for every employee.
2. **Given** the four existing evaluation suites, **When** they are re-run
   after the change, **Then** all remain at 100% on-domain.

### User Story 3 - Meaningful "eligible" cutoff (Priority: P2)

As an HR user, I want the "eligible" flag on a match to reflect an absolute
quality bar, not a position relative to the best job in the basket, so that a
weak basket doesn't dress up poor matches as eligible.

**Why this priority**: Follows directly from the absolute scale; lower impact
than P1 because the flag is secondary UI, but leaving it relative would
contradict the new semantics.

**Independent Test**: Construct an employee whose best match is objectively
weak; verify that weak matches are not marked eligible merely for being "top of
a bad basket".

**Acceptance Scenarios**:

1. **Given** a basket whose best match is weak, **When** HR views it, **Then**
   matches below the absolute bar are not flagged eligible.
2. **Given** the four current employees, **When** the new cutoff is applied,
   **Then** the share of eligible matches stays in the same ballpark as today
   (no mass flip in either direction).

### Edge Cases

- **Older model package without a usable calibration component**: the system
  must not silently revert to the old relative display; it surfaces a clear
  warning and shows the raw ranking signal until a calibrated component is
  available.
- **Calibration fitted for a different model version than the one serving**
  (stale pairing): detected and surfaced as a warning at startup, mirroring the
  existing weight-sync guard.
- **Score ties at the top** (the ranker saturates for clearly-strong jobs):
  several top jobs may display near-identical probabilities — accepted and
  honest; the order among ties remains deterministic.
- **Single-job result basket**: previously the relative stretch made one job
  look like the perfect score; with absolute display the number stands on its
  own regardless of basket size.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The displayed match score MUST be an absolute calibrated
  probability of the pair being a genuine match (as defined by the system's
  labeled ground truth), identical for identical inputs regardless of what
  other jobs are in the result set or which employee is viewed.
- **FR-002**: The displayed score MUST be a strictly monotonic function of the
  ranking signal, so display order and ranking order can never disagree.
- **FR-003**: The per-basket relative stretch step MUST be removed entirely
  (not kept as a fallback).
- **FR-004**: The calibration component MUST be fitted with a procedure that
  demonstrably converges, and the fit MUST be quality-checked at training time
  (a reliability summary comparing predicted vs observed match rates across the
  score range is produced in the training log).
- **FR-005**: The calibration MUST be fitted on the same signal that determines
  final ranking order (including penalty gates), computed at fit time by the
  same code path used at serving time.
- **FR-006**: The calibration artifact MUST record which model version it was
  fitted against; at startup the system MUST warn when the serving model does
  not match (same pattern as the existing weight-sync guard).
- **FR-007**: The "eligible" flag MUST use an absolute probability threshold
  (named constant, documented rationale) instead of a fraction of the basket's
  top score.
- **FR-008**: If no usable calibration is available at serving time, the system
  MUST log a clear warning and display the raw ranking signal — never the
  removed relative stretch, and never silently.
- **FR-009**: The score-explanation panel MUST account for the displayed number
  end-to-end (ranking signal → calibration → displayed probability), and the
  user-facing note MUST state the new semantics: absolute, comparable across
  employees, probability relative to the system's labeled ground truth.
- **FR-010**: Project documentation MUST be updated: the "scores are not
  comparable across employees" caveat is removed; the new score semantics and
  its honest framing (probability with respect to the labeled-pair
  distribution, which was selected via decision-boundary buckets) are recorded.

### Key Entities

- **Calibration artifact**: per-model-version mapping from ranking signal to
  probability; stored with the model package; carries a version stamp of the
  model it was fitted against.
- **Match record**: existing per-employee↔job row; its displayed score changes
  semantics from "relative position" to "absolute probability"; its
  score-breakdown gains the calibration step so the chain stays complete.

## Success Criteria *(mandatory)*

- **SC-001 (order invariance)**: For 100% of employees, the ranked job-ID
  sequence after the change is identical to before the change.
- **SC-002 (eval invariance)**: All four evaluation suites (fixed 20-CV
  harness, 20 held-out personas, 30 personas, 15 real-text CVs) remain at 100%
  top-1 on-domain.
- **SC-003 (stability)**: Re-running matching twice for the same employee with
  no data/model change produces bit-identical displayed scores.
- **SC-004 (comparability)**: A ranked union of all employees' matches ordered
  by displayed score is monotone in the underlying ranking signal — no
  cross-employee inversions introduced by display.
- **SC-005 (calibration quality)**: On held-back labeled pairs, the mean
  predicted probability per score-decile tracks the observed match rate within
  ±0.15 in every populated decile (reliability table in the training log), and
  the fitted mapping spans a usable range (max−min predicted probability over
  the observed score range ≥ 0.5 — i.e., visibly better than today's broken fit
  which spans ~0.17).
- **SC-006 (guard works)**: Pairing a calibration artifact from one model
  version with a different serving model produces a startup warning.
- **SC-007 (no silent fallback)**: Removing the calibration artifact produces a
  logged warning and a raw-signal display, verified by test.

## Assumptions

- The probability is defined **with respect to the v4 labeled-pair
  distribution** (12,084 labels, bucket-selected at the decision boundary). It
  is presented as "likelihood this pair would be labeled a match by our ground
  truth", not as a universal probability over all conceivable pairs. This
  framing is documented and is sufficient for the HR use case and the thesis.
- Ranker saturation at the top is accepted: clearly-strong jobs will cluster in
  a narrow high-probability band. No cosmetic rescaling will be applied — a
  deliberate honesty commitment.
- The internal three-level match label (strong/good/weak) keeps its current
  thresholds on the raw ranker score; it is unaffected by this feature.
- Displayed numbers will change magnitude for existing users (e.g., an old
  "92%" may become "~80%"); this is a one-time communication item, mitigated by
  the score-explanation panel.
- Retrieval, gates, ranking weights, and the ranker itself are all unchanged;
  only the calibration component is refit (seconds of compute, no GPU).

## Out of Scope

- Increasing pool depth / "find more jobs" pagination (separate follow-up).
- Any retraining of the GNN or the reranker.
- Changes to ordering logic, gate factors, or stage-1 weights.
- UI redesign beyond the score-semantics note and explanation-panel addition.
- Incremental per-employee scoring architecture.
