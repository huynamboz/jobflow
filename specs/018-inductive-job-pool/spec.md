# Feature Specification: Inductive Live-Catalog Job Ranking

**Feature Branch**: `018-inductive-job-pool`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Make newly-crawled jobs rankable by the matcher without retraining — rebuild the matcher's job set from the live catalog, embed new jobs on the fly, share it across processes, and reflect it the same morning."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Newly-crawled jobs are matched the same day (Priority: P1)

Each night the system crawls fresh jobs into the catalog. The next morning, HR opens the dashboard / receives the digest and sees genuinely new matching jobs for their employees — including jobs that did not exist when the matching model was trained.

**Why this priority**: This is the whole point of the feature. Today the matcher only scores employees against a frozen set of jobs baked in at model-training time, so jobs crawled afterwards are invisible to matching. Without this, the "crawl → match → morning digest" loop is broken — HR is shown stale options and the daily crawl adds no matching value.

**Independent Test**: Crawl (or insert) a new job that did not exist at training time, run the daily refresh, then open an employee whose skills fit it — the new job appears in that employee's suggested matches and (if recent) in the morning digest's "new jobs".

**Acceptance Scenarios**:

1. **Given** a job crawled after the matching model was trained, **When** the daily refresh runs and an employee with matching skills is re-matched, **Then** that job appears in the employee's ranked matches.
2. **Given** the daily refresh has run, **When** HR opens the dashboard the next morning, **Then** the "employees with new jobs" count reflects jobs that were genuinely new in the last 24h.
3. **Given** an employee with no fitting new jobs, **When** the refresh runs, **Then** no spurious new matches are created for them.

---

### User Story 2 - Live app reflects the latest catalog without a restart (Priority: P2)

When HR clicks "Refresh jobs" on an employee in the running application, the matcher scores against the most recently refreshed job set — not a stale set frozen at server startup — without anyone restarting the server.

**Why this priority**: Realtime visibility on the live app makes the daily refresh trustworthy and lets HR act immediately. Without it, new jobs only appear after a manual restart, which is operationally fragile.

**Independent Test**: With the app already running, trigger a refresh that adds a new job, then click "Refresh jobs" on a matching employee in the live app — the new job appears without restarting the server process.

**Acceptance Scenarios**:

1. **Given** the application is running and a refresh adds new jobs, **When** HR clicks "Refresh jobs", **Then** the returned matches include jobs from the latest refreshed set.
2. **Given** a refresh is in progress, **When** HR uses the app, **Then** matching keeps working against the last good set (no errors, no empty results).

---

### User Story 3 - Every ranked job maps to a real catalog job (Priority: P3)

When the matcher returns ranked jobs, each one corresponds to a real job in the catalog that HR can open, apply to, and track — with no silently dropped or unresolvable results.

**Why this priority**: Today a large share of the matcher's results point to identifiers that do not resolve to a real catalog job and are silently skipped, shrinking and distorting each employee's list. Cleaning this up makes the lists complete and trustworthy.

**Independent Test**: Run matching for an employee and confirm every returned candidate resolves to a real catalog job (zero "skipped" results), and the stored count equals the number returned.

**Acceptance Scenarios**:

1. **Given** an employee is matched, **When** results are persisted, **Then** zero candidates are dropped for failing to resolve to a catalog job.
2. **Given** a job already applied/accepted by HR, **When** a refresh + re-match runs, **Then** its pipeline status is preserved and it is not duplicated.

---

### Edge Cases

- **New job with no extractable skills**: ranked on whatever signal is available (text/seniority) rather than crashing or being silently dropped; if genuinely unusable it is simply absent from results.
- **New job using a skill the model has never seen**: the skill still contributes through text similarity even if it has no learned relationship to other skills.
- **Refresh fails partway**: the previously usable job set remains intact and serving; matching never operates on a half-written set.
- **Refresh runs while the live app is serving**: the app continues returning matches throughout, then picks up the new set.
- **Large catalog**: the refresh completes within the daily maintenance window for the full catalog (~6.5k jobs and growing).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The matcher MUST rank an employee's CV against the current live job catalog, including jobs added after the matching model was trained.
- **FR-002**: The system MUST incorporate newly-crawled jobs into ranking WITHOUT retraining the matching model.
- **FR-003**: The system MUST refresh the rankable job set on the existing daily schedule (after the overnight crawl and skill extraction) and reflect it in the morning digest and dashboard "new jobs" counts.
- **FR-004**: The running application MUST serve rankings against the latest refreshed job set without requiring a manual restart.
- **FR-005**: Every ranked candidate MUST resolve to a real catalog job; the system MUST NOT silently drop unresolvable results.
- **FR-006**: Ranking quality for jobs that were already rankable MUST NOT regress; the refresh MUST be guarded by a ranking sanity-check before it is trusted.
- **FR-007**: Re-ranking MUST remain idempotent — no duplicate job entries per employee — and MUST preserve HR-set pipeline statuses (applied / accepted / in progress / completed / rejected).
- **FR-008**: A job lacking extractable skills MUST be handled gracefully (ranked on available signal or excluded), never causing the refresh to fail.
- **FR-009**: The refresh MUST be safe to run while the application is serving: a failure leaves the previous job set usable.
- **FR-010**: The refreshed job set MUST be shared across the maintenance job and the live application (a single source of truth), not recomputed inconsistently per process.

### Key Entities *(include if feature involves data)*

- **Job (catalog entry)**: a crawled job with title, description, required skills (each with an importance), seniority, salary range, and role category. The unit HR ultimately applies to and tracks.
- **Rankable Job Set**: the set of jobs the matcher can currently score a CV against, derived from the live catalog. Replaces the previously frozen, training-time set.
- **Job Set Snapshot**: the persisted, shareable representation of the rankable job set (the jobs plus their precomputed matching signals) that both the maintenance job and the live app read, enabling realtime reflection without retraining.
- **Employee Job Match**: the stored ranking result linking an employee to a catalog job, with score, matched/missing skills, and pipeline status (unchanged by this feature except that it now always references a real catalog job).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of jobs added to the catalog before a given daily refresh are eligible as candidate matches that same day (today: effectively 0% for jobs added after model training).
- **SC-002**: 0% of ranked results are dropped as unresolvable to a catalog job (today: roughly a quarter of results are skipped).
- **SC-003**: After a refresh, HR using the live app sees matches that include the latest catalog jobs without any server restart.
- **SC-004**: On a fixed sample of employees, the top-ranked jobs for the previously-covered catalog remain consistent with the current matcher (no quality regression beyond an agreed tolerance).
- **SC-005**: A full-catalog refresh (~6.5k jobs) completes within the daily maintenance window (target: a few minutes, well inside the overnight-to-morning gap).
- **SC-006**: Re-running the refresh with an unchanged catalog creates 0 new or duplicate matches and changes 0 HR-set pipeline statuses.

## Assumptions

- Live catalog jobs carry extracted skills with importance values; the overnight skill-extraction step runs before the refresh so new jobs are ready (verified: after cleanup, 100% of current jobs have skills).
- The trained matching model and its learned CV/skill knowledge remain fixed; only the job set is refreshed. No model retraining is in scope.
- The matcher's reranking stage generalises to the refreshed jobs without change (confirmed by source analysis); a ranking sanity-check guards against regression.
- The existing daily maintenance routine ("morning refresh") is the trigger point for rebuilding the rankable job set.
- Jobs identify uniquely by their catalog identifier, which becomes the single identifier used by ranking and match persistence.
- Single-tenant deployment; no per-customer isolation of the job set.

## Dependencies

- The overnight crawl and skill-extraction pipeline must complete before the daily refresh.
- The existing trained matching model (weights + CV/skill knowledge) is reused as-is.
- The existing daily schedule + digest pipeline are reused as the delivery surface.
