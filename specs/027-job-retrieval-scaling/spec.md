# Feature Specification: Scalable Job-Pool Retrieval

**Feature Branch**: `027-job-retrieval-scaling`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Scale the GNN matcher's job-pool retrieval for a growing catalog — make serving production-correct as job count grows from ~8k toward hundreds of thousands, without retraining the model. Three staged sub-features: (A) vectorize stage-1 retrieval, (B) pgvector ANN index, (C) incremental job-pool rebuild."

## Overview

The matcher ranks every employee/CV against the live job catalog. Today, each match scores **every job in the pool one-by-one in a Python loop** before keeping the top candidates. At ~8k jobs this is fine; as daily crawling pushes the catalog toward tens and hundreds of thousands of jobs, match latency degrades linearly and the nightly pool rebuild re-encodes the entire catalog from scratch. This feature makes retrieval scale **without retraining** the model (weights stay frozen; jobs are encoded inductively) and **without changing the quality** of results (the displayed calibrated match probability must stay identical on the fixed evaluation set).

The work is split into three independently shippable, independently testable stages, in priority order. Stage A alone delivers the bulk of the value and is a viable increment.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast matching that stays correct as the catalog grows (Priority: P1)

HR opens an employee and the system ranks them against the whole job catalog. As the catalog grows from thousands to hundreds of thousands of jobs, this ranking must stay fast (no perceptible wait) and return the **same quality** of matches it does today — the same top jobs, the same displayed match probabilities.

**Why this priority**: This is the core scaling fix and the biggest, lowest-risk win. The current per-job Python loop is the actual bottleneck; replacing it with a vectorized retrieve→rerank split removes it for catalogs up to ~1M jobs with no extra infrastructure. Delivers value on its own.

**Independent Test**: Run the fixed evaluation set (`eval_matching`, 20-CV) before and after; on-domain@k must be ≥ the current value and the displayed calibrated probabilities unchanged within tolerance. Measure match latency at the current catalog and at a synthetically inflated catalog (e.g. 100k jobs) — latency must drop sharply and stay roughly flat as the catalog grows.

**Acceptance Scenarios**:

1. **Given** the current ~8k-job catalog, **When** an employee is matched before and after the change, **Then** the top-k results and their calibrated match probabilities are identical within tolerance.
2. **Given** a catalog inflated to ~100k jobs, **When** an employee is matched, **Then** the match completes within an interactive latency budget and the result quality (on-domain@k) does not regress.
3. **Given** the new retriever is enabled, **When** an operator flips a configuration switch back to the exact (old) path, **Then** both paths can be compared on the same inputs (A/B), and the exact path reproduces today's results.

---

### User Story 2 - Sub-linear retrieval at hundreds of thousands of jobs (Priority: P2)

As the catalog reaches the scale where even a vectorized full scan is heavy, retrieval moves into an index so the system only examines a small set of nearest candidates per match instead of the whole catalog, and newly added jobs become searchable by being added to the index rather than reloading everything.

**Why this priority**: Needed only once the catalog is large enough that scanning every job per match — even vectorized — becomes a cost. Builds on Story 1's retrieve→rerank split.

**Independent Test**: At a synthetic catalog of 200k+ jobs, measure retrieval latency with the index versus the full scan; the index must be materially faster and scale sub-linearly. Confirm a single newly added job becomes retrievable without a full pool reload, and that `eval_matching` parity holds.

**Acceptance Scenarios**:

1. **Given** a catalog of 200k+ jobs, **When** an employee is matched, **Then** retrieval examines only a bounded candidate set and latency is materially lower than a full scan.
2. **Given** a single new job is added, **When** it is inserted into the index, **Then** it becomes retrievable in subsequent matches without rebuilding the whole pool.
3. **Given** the index is unavailable or incompatible, **When** a match runs, **Then** the system falls back to a working retrieval path rather than failing.

---

### User Story 3 - Incremental pool refresh after crawling (Priority: P3)

After the daily crawl adds N new jobs, refreshing the searchable pool should encode only those N new (or changed) jobs and reuse existing encodings for everything else, instead of re-encoding the entire catalog every run. A full from-scratch refresh remains available on demand.

**Why this priority**: An operational efficiency: it keeps the post-crawl refresh cheap as the catalog grows. Not required for correct matching, but avoids a refresh time that grows with total catalog size.

**Independent Test**: After adding N new jobs, run the incremental refresh and confirm only those N are encoded (not the whole catalog), the resulting pool is identical to a full rebuild, and the explicit full-refresh option reproduces a from-scratch result.

**Acceptance Scenarios**:

1. **Given** N new jobs were crawled into the catalog, **When** the incremental refresh runs, **Then** only those N jobs are encoded and the rest reuse existing encodings.
2. **Given** an existing job's content changed, **When** the incremental refresh runs, **Then** that job is re-encoded and stale encodings are not served.
3. **Given** the operator requests a full refresh, **When** it runs, **Then** the entire pool is rebuilt from scratch and matches the incremental result for an unchanged catalog.

---

### Edge Cases

- **Recall miss**: the cheap retriever may shortlist the wrong jobs and drop a candidate the full scoring would have ranked highly → mitigated by a generously sized shortlist and validated against the evaluation set; a configurable exact/A-B path stays available.
- **Empty or tiny catalog**: retrieval and refresh must behave correctly when the pool is smaller than the shortlist size.
- **Pool/model mismatch**: a stored index or snapshot built against a different model must be detected and ignored in favor of the frozen fallback, never served as if valid.
- **Change-detection gap**: incremental refresh must not miss an edited job (stale encoding served) → content-based change detection plus a periodic full refresh as a safety net.
- **Ineligible jobs**: jobs that don't meet the pool-eligibility rule (fewer than two recognized skills) must continue to be excluded everywhere — retrieval, index, and refresh.
- **Calibration drift**: any retrieval change that shifts the displayed match probability on the fixed evaluation set is a regression, even if ordering looks similar.

## Requirements *(mandatory)*

### Functional Requirements

**Cross-cutting**

- **FR-001**: Matching MUST continue to use frozen model weights — no retraining is performed by any stage of this feature.
- **FR-002**: The set of jobs eligible for ranking MUST remain unchanged (jobs with at least two recognized skills); ineligible jobs stay excluded from retrieval, index, and refresh.
- **FR-003**: The four-term hybrid score, the reranker, and the calibrated probability mapping MUST remain unchanged; this feature changes only **which** candidates are scored and **how** they are stored/retrieved, not how a scored pair is valued.
- **FR-004**: Every stage MUST be validated against the fixed evaluation set; on-domain@k MUST NOT regress and displayed calibrated probabilities MUST stay within a defined tolerance.

**Story 1 — vectorized retrieval**

- **FR-005**: The system MUST retrieve a candidate shortlist using a single batched similarity computation over the pool, replacing the per-job Python loop.
- **FR-006**: The exact composite scoring and reranking MUST run only on the shortlist, not the whole pool.
- **FR-007**: The shortlist size MUST be configurable and default to a value large enough that result quality is preserved on the evaluation set.
- **FR-008**: An operator MUST be able to switch between the new retriever and the exact (old) full-scan path for A/B comparison.

**Story 2 — indexed retrieval**

- **FR-009**: The system MUST support retrieving the candidate shortlist from a nearest-neighbor index instead of scanning the full pool.
- **FR-010**: A single new or updated job MUST be insertable into the index without rebuilding the entire pool.
- **FR-011**: When the index is missing or incompatible, the system MUST fall back to a working retrieval path rather than erroring.
- **FR-012**: Indexed retrieval MUST preserve the shortlist semantics established in Story 1 (same candidates fed to scoring, within recall tolerance).

**Story 3 — incremental refresh**

- **FR-013**: The pool refresh MUST encode only new or changed jobs and reuse existing encodings for unchanged jobs.
- **FR-014**: The refresh MUST detect changed jobs by content (not just presence) so edits are re-encoded.
- **FR-015**: A full from-scratch refresh MUST remain available as an explicit option and as a periodic safety net.
- **FR-016**: An incremental refresh of an unchanged catalog MUST produce a pool identical to a full rebuild.

### Key Entities *(include if feature involves data)*

- **Job pool entry**: a ranking-eligible job with its frozen-model encoding(s) and the content fingerprint used to detect changes.
- **Candidate shortlist**: the bounded set of jobs returned by retrieval and handed to exact scoring + reranking for a single match.
- **Retrieval index**: the store of per-job encodings that answers "nearest jobs to this CV" without scanning the whole pool (Story 2).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the fixed evaluation set, on-domain@10 is greater than or equal to the pre-change value for every stage.
- **SC-002**: Displayed calibrated match probabilities for the fixed evaluation set change by no more than a defined tolerance after each stage.
- **SC-003**: At a 100k-job catalog, a single match completes within an interactive latency budget (sub-second for retrieval), versus a measurably worse time on the current per-job loop.
- **SC-004**: Match latency stays roughly flat (not linear in catalog size) as the catalog grows from 8k to 100k jobs after Story 1, and from 100k to 200k+ after Story 2.
- **SC-005**: After Story 3, a post-crawl refresh that adds N new jobs encodes only those N jobs; refresh time scales with new-job count, not total catalog size.
- **SC-006**: Each stage can be enabled, disabled, or rolled back independently without affecting the others.

## Assumptions

- The matcher continues to serve from a single process; multi-node/sharded serving is out of scope.
- The existing relational database is available for an in-database index option (Story 2); no new datastore is introduced.
- The existing evaluation harness and fixed CV set are the source of truth for "no quality regression."
- Synthetic catalog inflation (duplicating/perturbing existing jobs) is acceptable for latency/scale testing where a real large catalog isn't yet available.
- "Interactive latency budget" means retrieval fast enough that HR perceives matching as instant (target: retrieval well under one second at 100k jobs).
- The embedding model and the inductive job-encoding mechanism are unchanged; only how encodings are stored, retrieved, and refreshed changes.

## Out of Scope

- Retraining the GNN or the reranker; changing the hybrid formula, the calibration, or the two-skill eligibility rule.
- Replacing the embedding model.
- Multi-node / horizontally sharded serving.
- Cross-platform job de-duplication (a separate concern).
