# Feature Specification: Pipeline Foundation Fixes (Đợt 0)

**Feature Branch**: `021-pipeline-foundation-fixes`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Repair the audited pipeline bugs that corrupt training data, evaluation, and serving — BEFORE the relabel+retrain effort (master plan Đợt 0, items 0.1-0.7; audit codes A1-A9 in docs/codebase-knowledge/09-pipeline-audit.md)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean, consistent training supervision (Priority: P1)

The exported training dataset contains exactly one label per candidate-job pair (the most recent judgment), and the training graph never receives a pair marked simultaneously as both match and no-match.

**Why this priority**: 2,967 duplicate label rows (247-284 contradictory) currently flow into training; 181 pairs carry BOTH positive and negative edges, feeding the model self-contradictory gradients. Every future labeling/training effort (Đợt 1-2) builds on this export — it must be clean first.

**Independent test**: Re-export the dataset → every (cv, job) appears exactly once; build the graph → zero pairs with both edge types reported.

**Acceptance Scenarios**:

1. **Given** a pair labeled multiple times across batches, **When** the dataset is exported, **Then** only the most recent label is included.
2. **Given** the deduplicated export, **When** the training graph is built, **Then** no (cv, job) pair has both a match and a no-match edge, and the build reports the conflict count (0).

---

### User Story 2 - The ranking the user sees is the ranking the system computed (Priority: P1)

The final job list order follows the designed two-stage semantics (learned reranker order, demoted by the documented penalty gates), and the displayed score is monotonic with that order — the #1 job never shows a lower percentage than the #2 job.

**Why this priority**: Today the last sorting step silently discards the reranker's order, so stage 2 of the architecture effectively does nothing for ordering, and displayed scores can disagree with positions. This misleads HR and invalidates the system's own design claims.

**Independent test**: Run a match → the returned list is sorted by the final (penalty-adjusted reranker) score; displayed scores are non-increasing down the list.

**Acceptance Scenarios**:

1. **Given** a CV matched against the catalog, **When** results are returned, **Then** their order reflects the reranker score adjusted by the penalty gates, and displayed scores are non-increasing.
2. **Given** a candidate hit by an experience/seniority gate, **When** results are returned, **Then** that candidate is demoted in the final order (the gate still matters).

---

### User Story 3 - The experience requirement matters again (Priority: P1)

A job requiring 5 years of experience no longer ranks an 1-year-experience employee as if the requirement didn't exist: the under-qualification penalty applies, and the experience-fit dimension reflects the deficit.

**Why this priority**: A verified bug drops the experience fields when building the live job pool, silently disabling the experience gate and the experience-fit diagnostic for 100% of live jobs. One missing line corrupts ranking quality everywhere.

**Independent test**: Rebuild the pool → a known job with experience_min=5 vs a 1-year CV shows a reduced score and experience_fit < 1.0.

**Acceptance Scenarios**:

1. **Given** a live job with a stated minimum experience, **When** the pool is rebuilt and a low-experience CV is matched, **Then** the under-qualification penalty applies and experience_fit < 1.0.
2. **Given** a job with no stated experience requirement, **When** matched, **Then** behavior is unchanged (neutral).

---

### User Story 4 - Honest, interpretable model metrics (Priority: P2)

Training/test ranking metrics are computed per-CV (each CV ranks its own labeled jobs; results averaged), so reported precision/NDCG/MRR describe real recommendation quality instead of a global-ranking artifact that yields meaningless perfect scores.

**Why this priority**: The current checkpoint reports precision@5 = NDCG@5 = MRR = 1.0 — artifacts of ranking all test pairs in one global list. Decisions based on these numbers are unreliable; Đợt 2's retrain must be measured with a correct ruler.

**Independent test**: Re-evaluate the existing checkpoint → per-CV metrics produce plausible (non-1.0) values, labeled as per-CV means.

**Acceptance Scenarios**:

1. **Given** the existing checkpoint and test split, **When** evaluation runs with the fixed metrics, **Then** ranking metrics are per-CV averages and no longer saturate at 1.0 artificially.

---

### User Story 5 - A labeling rubric ready for relabeling (Priority: P2)

The pair-scoring rubric used by the (LLM/agent) labeler closes its three audited gaps: cross-field pairs with strong skill overlap are explicitly not-suitable; transferable skills (e.g. Flask↔Django) earn partial skill credit instead of forced zero; and every role category (including mobile and BA) can score a same-field match.

**Why this priority**: Đợt 1 will generate thousands of new labels with this rubric. Labeling with the current rubric would reproduce the exact noise (43% of the critical slice mislabeled) and keep the ground truth blind to related-skill matches — the GNN's core advantage.

**Independent test**: Three written test cases (one per gap) score correctly under the patched rubric.

**Acceptance Scenarios**:

1. **Given** a pair with skill_fit=2 and domain_fit=0, **When** scored, **Then** overall=0 by explicit rule.
2. **Given** a CV with Flask/Celery vs a job requiring Django, **When** scored, **Then** skill coverage receives partial transferable-skill credit (not forced 0).
3. **Given** a mobile CV vs a mobile job, **When** scored, **Then** domain_fit=2.

---

### User Story 6 - No duplicate jobs in the catalog or in results (Priority: P3)

HR never sees the same posting (same title + company) listed multiple times in one suggestion list, and the catalog keeps a single active row per real-world posting — without losing any job an HR has already engaged with.

**Why this priority**: 343 duplicate groups (731 redundant rows) exist and the serving path has no dedup — observed as "JavaScript Tutor ×3" in a top-5. Wastes HR time and inflates metrics; cleanup is guarded so engaged matches are never orphaned.

**Independent test**: After cleanup + serving guard, the evaluation harness shows no repeated title+company in any top-5; the catalog has zero active duplicate groups; all HR-engaged matches still point at active jobs.

**Acceptance Scenarios**:

1. **Given** duplicate active rows of the same title+company, **When** cleanup runs, **Then** one row stays active (preferring any row with HR-engaged matches, else the newest) and the rest are deactivated reversibly.
2. **Given** the serving path, **When** results are assembled, **Then** repeats of the same title+company beyond the first are dropped.

---

### Edge Cases

- **Pair relabeled with the same value**: dedup keeps one row — no behavior change.
- **All labels for a pair are conflicting but one is clearly latest**: latest wins (documented tie-break: created_at, then id).
- **Reranker untrained/unavailable**: final order falls back to stage-1 score (current degraded behavior preserved); monotonicity still holds.
- **Duplicate jobs where BOTH rows have engaged matches**: keep both active (never orphan engagement); exclude from auto-dedup and report for manual review.
- **Job with experience_min present but 0**: treated as "no requirement" (neutral) — unchanged.
- **CVs with zero positives in test**: excluded from per-CV ranking averages (documented), counted separately.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The live job pool MUST carry each job's experience requirement fields so the experience gate and experience-fit diagnostic operate on live data.
- **FR-002**: Dataset export MUST emit at most one label per (cv, job) pair, selecting the most recent judgment; the selection rule MUST be deterministic.
- **FR-003**: Graph construction MUST detect (and fail loudly or visibly report) any pair that would receive both match and no-match edges; after FR-002, the count MUST be zero.
- **FR-004**: The final result order MUST follow the stage-2 reranker score adjusted by the documented penalty gates; the displayed score MUST be monotonic non-increasing with the final order.
- **FR-005**: Training/test ranking metrics (precision@k, recall@k, NDCG@k, MRR, hit-rate) MUST be computed per-CV and averaged; the overall separation metric (AUC) stays global. Reported names MUST say "per-CV".
- **FR-006**: The labeling rubric MUST: (a) rule skill_fit=2 & domain_fit=0 → overall=0; (b) grant partial skill-coverage credit for transferable/equivalent skills with concrete examples; (c) cover ALL role categories in the domain table (mobile↔mobile=2, ba↔ba=2, plus sensible related entries).
- **FR-007**: Catalog cleanup MUST deactivate duplicate (title, company) rows keeping exactly one active — preferring a row with HR-engaged matches, else the newest — reversibly (soft), and MUST NOT deactivate any row carrying engaged matches.
- **FR-008**: The serving path MUST NOT return more than one result with the same (title, company) in a single match response.
- **FR-009**: After all fixes, a post-fix baseline (eval harness + test suite) MUST be recorded in the project docs as the reference point for Đợt 1-2.
- **FR-010**: All changes MUST be covered by automated tests where applicable (export dedup, graph guard, ordering monotonicity, per-CV metrics, serving dedup).

### Key Entities *(include if feature involves data)*

- **Label record**: one judgment per (cv, job) pair after dedup — the unit of training supervision.
- **Match result list**: the ordered jobs returned for a CV — order + displayed score now contractually consistent.
- **Job catalog row**: one active row per real posting (title+company) after cleanup; deactivation is soft/reversible.
- **Post-fix baseline**: the recorded quality numbers (on-domain rate, test results) against which Đợt 1-2 are measured.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-export yields 0 duplicate (cv, job) label rows (from 2,967) and graph build reports 0 match/no-match conflicts (from 181).
- **SC-002**: 100% of returned match lists are monotonic in displayed score and ordered by the penalty-adjusted reranker score.
- **SC-003**: A job requiring 5y vs a 1y CV is demoted and shows experience_fit < 1.0 (gate verified working on live pool).
- **SC-004**: Re-evaluated checkpoint metrics report plausible per-CV values (no 1.0 saturation artifacts).
- **SC-005**: The three rubric test cases score correctly under the patched rubric.
- **SC-006**: 0 active duplicate (title, company) groups remain (from 343); no top-5 in the eval harness contains a repeated title+company; 0 engaged matches orphaned.
- **SC-007**: A post-fix baseline is recorded (eval on-domain rate + full test suite green) in the master plan docs.

## Assumptions

- "Most recent label wins" is the agreed dedup policy (latest created_at, tie-break id) — consistent with relabeling semantics (newer judgment supersedes).
- Final-order semantics: reranker score × the same gate factors (penalties demote within the reranker's ordering); when the reranker is unavailable, stage-1 order is the fallback. The decision is documented in the knowledge docs.
- Duplicate definition for jobs is exact (title, company) match among active rows; URL/fingerprint variants beyond that are out of scope here.
- The rubric patch changes FUTURE labeling only; existing labels are re-labeled in Đợt 1 (not here).
- Deactivation (is_active=False) is reversible and is the established soft-delete convention in this codebase.

## Dependencies

- Audit findings and verification in docs/codebase-knowledge/09-pipeline-audit.md (A1, A2, A3, A7, A4-A6, A9).
- Master plan Đợt 0 (docs/codebase-knowledge/10-master-plan.md items 0.1-0.7).
- Existing eval harness (`eval_matching`) and test suite as the baseline instruments.
