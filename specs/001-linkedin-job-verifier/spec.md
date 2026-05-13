# Feature Specification: LinkedIn Job Lifecycle Verifier

**Feature Branch**: `001-linkedin-job-verifier`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "LinkedIn job lifecycle verifier with DI architecture"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Job seekers do not see expired listings (Priority: P1)

A job seeker uploads their CV and receives a ranked list of recommended jobs. Today, that list can contain jobs that have already been filled or closed on LinkedIn — clicking through to apply lands them on a "No longer accepting applications" page. The verifier marks those listings as expired in the database so the matching API filters them out before returning recommendations.

**Why this priority**: This is the user-visible problem the feature exists to solve. Without it, the recommendation surface is leaking dead links and eroding user trust on every session.

**Independent Test**: Pre-populate the database with two LinkedIn jobs known to be closed and three known to be active. Run the verifier once. Submit a CV that matches all five. Confirm only the three active jobs appear in the API response, in their original ranking order.

**Acceptance Scenarios**:

1. **Given** a job whose LinkedIn page still shows an active Apply button, **When** the verifier runs against it, **Then** the job's lifecycle is set to `active` and `last_verified_at` is updated.
2. **Given** a job whose LinkedIn page shows "No longer accepting applications", **When** the verifier runs against it, **Then** the job's lifecycle is set to `expired`.
3. **Given** a job whose lifecycle is `expired`, **When** a CV is submitted to the matching endpoint, **Then** that job does not appear in the returned ranked list, while the relative ordering of other recommendations is preserved.

---

### User Story 2 — Operators can verify the LinkedIn job catalog on a schedule (Priority: P1)

An operator running the platform needs a way to keep the database fresh without baby-sitting the verifier. They expect a one-line command that picks the most stale set of LinkedIn jobs, checks them against LinkedIn, and updates lifecycle/timestamps with a clear report at the end. That command must be safe to put on a cron so it runs unattended.

**Why this priority**: Without an operator entry point, the verifier provides no recurring value — it would degrade to a one-off check that drifts immediately. Scheduling is what turns a script into a service.

**Independent Test**: From a clean shell, run the management command with a small batch size against a known sample and confirm: (a) exit code reflects success, (b) a structured report is printed listing counts by outcome, (c) re-running immediately is a no-op for jobs that just succeeded (backoff respected).

**Acceptance Scenarios**:

1. **Given** the catalog has 100 LinkedIn jobs in `stale` state, **When** the operator runs the verify command with `--batch 50`, **Then** exactly 50 jobs are checked and the report shows the count per outcome (active, expired, error, session_expired).
2. **Given** the operator passes `--dry-run`, **When** the command completes, **Then** the report is produced but no lifecycle, attempt count, or backoff field is written to the database.
3. **Given** LinkedIn login cookies have expired and every check returns `session_expired`, **When** the command completes, **Then** the report flags the auth issue and the operator is told how to re-authenticate; no jobs are wrongly marked expired.

---

### User Story 3 — Engineering can add a second platform without touching the verifier service (Priority: P2)

The platform will need to verify jobs from sources other than LinkedIn (Indeed, RemoteOK, Wellfound). An engineer adding a new platform should only have to write one verifier file that conforms to a contract; the dispatch service, batch loop, scheduling, and database write paths must not change.

**Why this priority**: The first source motivates the architecture, but the architecture only pays off when the second source costs a fraction of the first. Without this, every new platform becomes a parallel codepath and the verifier service rots.

**Independent Test**: Drop a stub verifier file for a fake "indeed" platform into the providers directory; do not modify any service, command, or schema code. Insert a single job whose source URL matches the fake verifier's pattern. Run the management command targeting all platforms. Confirm the fake verifier was invoked and its result was written to the job row.

**Acceptance Scenarios**:

1. **Given** a new verifier file exists in the providers directory, **When** the service starts, **Then** the new verifier is discovered automatically without any registry edits.
2. **Given** a job's source URL matches the new verifier's URL pattern, **When** the dispatch service routes that URL, **Then** the new verifier handles it (not the LinkedIn one).
3. **Given** the test harness substitutes a fake verifier and fake database repository, **When** the verification service runs in tests, **Then** no real network calls or database writes occur.

---

### Edge Cases

- **Transient network failure**: a verifier returns an error outcome. The job's `verification_attempts` is incremented and a backoff is set; the job is not re-checked until the backoff window passes.
- **Session expired**: the LinkedIn cookies stored on disk are no longer valid. The verifier reports `session_expired` for every job in the batch; no job is wrongly marked expired, and a single alert is surfaced to the operator instead of one per job.
- **Job page is ambiguous**: the page renders but neither expired nor active markers match. The verifier returns `unknown`. Lifecycle is not changed; a short backoff is applied so the job is re-checked later.
- **Job has no `date_posted`**: the job's lifecycle starts as `unverified` rather than `active`. It is still eligible to be returned by the matching API but is sorted lower in confidence.
- **Job URL points to a redirect**: the verifier follows the redirect and inspects the final URL. If the final URL matches LinkedIn's auth-redirect pattern, the outcome is `session_expired`; otherwise the markers are evaluated on the final page.
- **Same job verified by two concurrent batches**: the database write is keyed by job ID and overwrites the lifecycle deterministically; backoff and attempts are reset on a successful outcome regardless of which batch wrote last.
- **A previously expired job becomes active again** (re-opened by the employer): the verifier reports `active`; the job is moved from `expired` back to `active` and is eligible for matching once more.
- **Catalog contains a non-LinkedIn URL but the operator selected `--platform linkedin`**: the LinkedIn verifier reports it does not support the URL; the job is skipped and counted under a "skipped: unsupported" line in the report.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST track lifecycle state for every job, with at minimum the states `active`, `stale`, `expired`, and `unverified`.
- **FR-002**: The system MUST timestamp when a job was last seen in a crawl (`last_seen_at`) and when it was last verified by the verifier (`last_verified_at`).
- **FR-003**: The system MUST track verification retry state (number of attempts, next eligible time) on a per-job basis so transient failures back off exponentially without hammering the source.
- **FR-004**: The system MUST expose an operator-invokable batch verifier with options to select platform, cap the batch size, and run without writing to the database.
- **FR-005**: The verifier MUST detect three outcomes from a LinkedIn job page: that the job is still accepting applications (`active`), that the job has been closed or removed (`expired`), and that the platform's authenticated session has been invalidated (`session_expired`).
- **FR-006**: When the LinkedIn session is invalidated, the system MUST surface a single actionable alert to the operator and MUST NOT mark jobs as expired solely because the session lapsed.
- **FR-007**: When a job's page is ambiguous (neither expired nor active markers match), the system MUST report `unknown` and MUST NOT alter the job's lifecycle, only its retry state.
- **FR-008**: The matching API MUST exclude jobs whose lifecycle is `expired` from any ranked recommendation returned to a CV submission, while preserving the relative ranking of the remaining jobs.
- **FR-009**: The verifier service MUST dispatch each job to the verifier whose URL pattern matches the job's source URL; an unsupported URL MUST be reported as skipped, not retried.
- **FR-010**: Adding a new platform's verifier MUST be possible by adding a single file that conforms to the verifier contract, without modifying the dispatch service, the batch entry point, the schema, or the matching filter.
- **FR-011**: The verification service MUST be testable with a fake verifier and a fake repository, without any real network call or database write.
- **FR-012**: The batch verifier MUST emit a structured run report containing total verified, counts per outcome, wall-clock duration, and any session alerts.
- **FR-013**: A job whose lifecycle transitions back from `expired` to `active` (re-opened by the source) MUST become eligible for matching again on the next request.
- **FR-014**: The verifier MUST throttle requests to a single source by introducing a per-request delay with jitter so that batch behaviour does not resemble automated scraping bursts.
- **FR-015**: Failure to verify any single job MUST NOT abort the batch; subsequent jobs MUST still be attempted and their outcomes recorded.

### Key Entities

- **Job**: an open-position record sourced from a platform. Carries lifecycle state, the platform URL by which it can be re-verified, and timestamps for "last seen" and "last verified".
- **VerifyResult**: the outcome of a single check — one of `active`, `expired`, `session_expired`, `unknown`, or `error` — together with a human-readable reason and the final URL the verifier inspected.
- **Verifier (per-platform)**: a checker bound to a URL pattern that knows how to determine a VerifyResult for jobs from one platform.
- **Verifier registry**: the lookup that picks the right verifier for a given URL or platform name.
- **Verification batch report**: the structured record produced when the operator runs the batch verifier — counts per outcome, duration, alerts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of jobs returned in production CV-to-job recommendations link to a page that is still accepting applications (manually sampled weekly).
- **SC-002**: The operator can verify a batch of 100 LinkedIn jobs in under 15 minutes of wall-clock time on a single workstation.
- **SC-003**: A new platform verifier can be added by an engineer in under 4 hours, including writing tests, with no changes to the dispatch service, batch command, or database schema.
- **SC-004**: When LinkedIn cookies expire, the operator is alerted on the next scheduled run and the verifier raises zero false-expired updates during that run.
- **SC-005**: Transient verification failures retry on exponential backoff and never exceed an average of 1 verification attempt per job per day during a 7-day soak test.
- **SC-006**: Test coverage for the verifier service, registry dispatch, backoff math, and matching-filter integration is at least 80% of lines.

## Assumptions

- LinkedIn authentication cookies have already been captured to disk by the existing `linkedin_auth` flow; re-authentication is an operator action, not part of this feature.
- The matching engine continues to read its initial candidate set from the existing checkpoint; the lifecycle filter is applied at runtime to the engine's output rather than baked into the checkpoint. Re-baking the checkpoint at the next retrain remains a separate concern.
- Job identity for re-verification is the existing `(platform, fingerprint)` pair already enforced as unique in the database; no new identifier field is introduced.
- The platform does not yet operate any async task runner (Celery/RQ); the operator entry point is a synchronous command suitable for cron. Adopting a task runner is out of scope and may be added later without changing the verifier service.
- The existing `is_active` boolean on the job model is superseded by the new lifecycle field. **Decision (pinned)**: `is_active` remains a stored column for v1 backward compatibility; no new code in this feature writes to it, and consumers added in this feature read `lifecycle` exclusively. Dropping the column is a v2 task once all existing readers migrate.
- LinkedIn-only is the v1 scope. The architecture must support additional platforms but no other platform verifier ships in this feature.
