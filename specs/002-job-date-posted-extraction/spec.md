# Feature Specification: LinkedIn date_posted extraction + auth-state fix + DB backfill

**Feature Branch**: `002-job-date-posted-extraction`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "LinkedIn date_posted extraction and DB backfill"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operators can rely on `Job.date_posted` to reason about freshness (Priority: P1)

Today, every LinkedIn job in the database has `date_posted = NULL` even though the crawler visits each job page and reads "Posted X weeks ago" text. As a result, the verifier's stale-promotion rule, the matching service's recency signal, and any operator question about "when was this job posted on LinkedIn" all silently break. The fix populates `date_posted` with the platform's posting date — extracted as an absolute YYYY-MM-DD value, never stored as relative text.

**Why this priority**: This is the gap the operator surfaced; everything else in this feature exists to make the field reliably populated.

**Independent Test**: Pick 3 LinkedIn job rows that have `date_posted IS NULL`. Run the backfill command for those rows. Confirm `date_posted` is now a real date (year-month-day) within plausible bounds (≥ 2024, ≤ today). The relative source text MUST NOT be stored anywhere — only the resolved absolute date.

**Acceptance Scenarios**:

1. **Given** a LinkedIn job page that exposes a `<time datetime="2026-04-29">` element, **When** the extractor runs against it, **Then** `Job.date_posted` is set to `2026-04-29 00:00 UTC` and the extractor records that the source was "datetime attribute".
2. **Given** a LinkedIn job page that exposes a JSON-LD `JobPosting` block with `"datePosted": "2026-04-15"`, **When** the extractor runs against it, **Then** `Job.date_posted` is set to that date and the source is recorded as "json-ld".
3. **Given** a LinkedIn job page that only exposes relative text such as "Posted 2 weeks ago", **When** the extractor runs against it, **Then** `Job.date_posted` is set to (run-time UTC date minus 14 days) and the source is recorded as "relative-text".
4. **Given** a LinkedIn job page that has been redirected to the `?trk=expired_jd_redirect` results page, **When** the extractor runs against it, **Then** `Job.date_posted` is left NULL and the job's `lifecycle` is set to `expired` (consistent with the verifier).

---

### User Story 2 — Operators can backfill the whole catalog without losing work mid-run (Priority: P1)

An operator wants to run `extract_job_dates --platform linkedin` once and have the catalog of ~7,000 LinkedIn jobs get their `date_posted` populated over the course of hours, with the option to stop and resume. The command must avoid re-processing jobs already filled in, must throttle politely, and must print a structured report at the end.

**Why this priority**: Without a one-shot backfill, the data fix never lands on existing rows. A non-resumable command means an interruption (cookies expire, machine sleeps) silently wastes the previous N URLs of work.

**Independent Test**: Start the backfill on a known sample of 20 jobs. Stop after the first 10 complete. Re-run with the same arguments. Confirm only the remaining 10 are visited; the first 10 are skipped because `date_posted` is already populated.

**Acceptance Scenarios**:

1. **Given** the operator runs `extract_job_dates --platform linkedin --batch 50`, **When** the command completes, **Then** at most 50 rows are visited, only rows with `date_posted IS NULL` are picked, and each row's source URL is opened exactly once.
2. **Given** the operator runs the command twice in succession with no other process in between, **When** the second run starts, **Then** the candidate set excludes rows the first run successfully filled.
3. **Given** the page extraction yields no date for a row (e.g., expired redirect), **When** the row is processed, **Then** `date_posted` stays NULL but the row's `lifecycle` is updated to `expired` so the next backfill run skips it.
4. **Given** `--dry-run` is passed, **When** the command completes, **Then** the report lists what *would* have been written but no DB row is mutated.

---

### User Story 3 — Auth-state file is not silently destroyed by background runs (Priority: P1)

Today, every `open_browser_page(...)` context exit calls `ctx.storage_state(path=...)` and overwrites the saved LinkedIn auth state with whatever cookies the current session has. When the active session has lost `li_at` (the LinkedIn login cookie) — which happens silently when LinkedIn ages the session out — the overwrite *removes* `li_at` from the saved state file. From that moment forward, every subsequent run authenticates as a guest, and the operator has no way to detect that the saved state has rotted until pages start rendering wrong layouts.

The fix is to (a) only re-persist the auth state when it still contains `li_at`, and (b) detect auth loss mid-batch and surface it as a `SESSION_EXPIRED` outcome rather than continuing to walk pages as a guest.

**Why this priority**: This bug compounds: each broken run makes the next one worse. Without fixing it, the date-extractor and verifier will both eventually run unauthenticated and silently produce low-quality data.

**Independent Test**: Make a copy of the current state file. Run the verifier (or extractor) with the state file artificially broken (no `li_at`). Confirm: (a) the on-disk state file is unchanged after the run, (b) every URL outcome is `SESSION_EXPIRED`, (c) the run reports the auth-loss alert.

**Acceptance Scenarios**:

1. **Given** the saved state file contains a valid `li_at` cookie at the start of a batch, **When** the batch completes successfully, **Then** the file still contains a valid `li_at` cookie at the end (cookies rotated but the auth identity preserved).
2. **Given** the saved state file does *not* contain `li_at`, **When** any batch starts, **Then** the run aborts before any URL is fetched and prints "Auth state has no li_at cookie — run linkedin_auth.py".
3. **Given** the saved state was valid at start but LinkedIn invalidated the session mid-batch (page redirected to login), **When** the next URL is processed and yields `SESSION_EXPIRED`, **Then** the batch stops, the report flags the alert, and the state file is *not* overwritten with the now-anonymous cookies.

---

### Edge Cases

- **Multiple `<time>` elements on the page**: Active LinkedIn job pages expose `<time>` elements for both the main posting and the "People also viewed" / "More jobs from..." cards. The extractor MUST pick the element associated with the main posting (top-card / tertiary-info area), not a random card. If no scoped match is found, fall back to JSON-LD, then to relative text.
- **Multiple JSON-LD blocks**: A page may include several JSON-LD scripts; the extractor MUST select the one whose `@type` is `JobPosting`.
- **Relative text with unsupported units**: "Posted today", "Posted yesterday", "Just now" must all resolve to a date (today / today-1d / today). Singular and plural forms ("1 hour ago" vs "3 hours ago") must both parse.
- **Future dates from `<time datetime>`**: A datetime in the future (clock skew or unusual content) MUST be discarded (treated as "no date found" and the next source is tried). Do not silently clamp to today — discarding makes the failure loud so an operator can investigate.
- **Very old dates**: A `<time datetime="2010-01-01">` (e.g., a related "Company since 2010" element accidentally matched) MUST be rejected — guardrails on `(today - 2 years) ≤ date ≤ today`. Out-of-bounds dates are treated as "no date found".
- **Indeed and other platforms**: Indeed jobs already have `date_posted` populated (JobSpy returns absolute dates). This feature does not change Indeed behaviour. The extractor architecture is platform-pluggable so a future Indeed extractor can be added without touching the orchestrator.
- **Concurrent runs**: The backfill writes only `date_posted`. If the verifier writes `lifecycle` simultaneously to the same row, the writes are independent fields and no lock is needed.
- **Auth file rotation by linkedin_auth.py**: Re-running the login flow MUST result in a state file that includes `li_at`. Otherwise the next batch fails fast with a clear message (US3 acceptance #2).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a LinkedIn job page exposes an authoritative absolute posting date (via `<time datetime="...">` or JSON-LD `datePosted`), the system MUST store that date in `Job.date_posted`.
- **FR-002**: When only relative text ("Posted N day/week/month/year ago", "today", "yesterday") is available, the system MUST parse it to an absolute UTC date and store that absolute value. The relative text MUST NOT be stored.
- **FR-003**: When no date can be extracted (expired redirect, unsupported layout), `Job.date_posted` MUST remain NULL.
- **FR-004**: The extractor MUST record which source produced the final value (`datetime-attribute`, `json-ld`, `relative-text`, or `none`) for diagnostic logging; this MAY be in-memory only and is not required to persist.
- **FR-005**: An operator-invokable backfill MUST iterate jobs with `date_posted IS NULL`, batch them, and visit each source URL at most once per run.
- **FR-006**: The backfill MUST be safely re-runnable: rows already populated in a prior run MUST be excluded from the candidate set.
- **FR-007**: The backfill MUST accept `--platform`, `--batch`, `--dry-run`, and `--json-report` flags consistent with the existing verifier command.
- **FR-008**: When the backfill processes a job whose source page indicates the listing is expired (the same signal the verifier uses), the system MUST update that row's `lifecycle` to `expired` and leave `date_posted` NULL.
- **FR-009**: New LinkedIn jobs added to the catalog after this feature ships MUST have `date_posted` populated by the crawler at ingestion time, using the same extraction logic as the backfill.
- **FR-010**: Date extraction logic MUST live in a single function that takes a Playwright `page` and returns `(date | None, source_tag)`, so the crawler and the backfill share one implementation.
- **FR-011**: Extracted dates MUST satisfy `(today_utc - 730 days) ≤ date ≤ today_utc`. Dates outside this range MUST be discarded and treated as "no date found".
- **FR-012**: The auth-state file MUST NOT be overwritten by a batch run unless the current session still contains the `li_at` cookie at the moment of write.
- **FR-013**: If the auth-state file at start of a batch does not contain `li_at`, the batch MUST abort with a single clear instruction to re-run the login flow; no URLs are fetched.
- **FR-014**: If `li_at` is present at start of a batch but is no longer present after navigating to a URL, the batch MUST stop on that URL, mark it (and any remaining URL) as `SESSION_EXPIRED`, and not overwrite the state file.
- **FR-015**: Per-job extraction failures MUST be isolated: an exception while parsing one page's date MUST NOT abort the batch.

### Key Entities

- **Date extraction result**: A pair `(date | None, source)` produced by the extractor for one page. `source` is one of `datetime-attribute`, `json-ld`, `relative-text`, `expired-redirect`, or `none`.
- **Backfill batch report**: The structured run summary for the operator — total examined, counts by outcome (populated, expired, none, error), wall-clock, dry-run flag, alerts.
- **Auth state guard**: An invariant on the saved state file: must contain a `li_at` cookie. Enforced before any batch starts and before any state-file write.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Within 24 hours of shipping, ≥ 80% of `lifecycle='active'` LinkedIn jobs in the DB have a non-null `date_posted`.
- **SC-002**: 100% of `lifecycle='expired'` LinkedIn jobs have `date_posted IS NULL` (we deliberately do not invent dates for redirected pages).
- **SC-003**: The backfill processes 100 LinkedIn URLs in ≤ 15 minutes wall-clock on a single workstation (same budget as the verifier).
- **SC-004**: Zero auth-state files are silently rotated to a guest-only state during a normal run; an operator-initiated `linkedin_auth.py` is the only path that mutates the saved auth identity.
- **SC-005**: After the backfill completes on the catalog, the verifier's aging rule (active → stale after 14d) promotes at least one job per scheduled run, instead of always promoting zero (today's state).
- **SC-006**: Unit-test line coverage for the date-extraction helper, the relative-text parser, the auth-state guard, and the backfill command is ≥ 80%.

## Assumptions

- The existing `linkedin_auth` flow is the only operator path that captures `li_at`. This feature does not change how login is performed.
- The verifier's existing detection priority and lifecycle write semantics are unchanged. This feature only adds a new field write path (`date_posted`) and tightens auth-state handling.
- Other platforms (Indeed, RemoteOK) already populate `date_posted` at crawl time and do not need re-extraction. The architecture is extensible to add new-platform extractors later, but no new platform extractor ships in this feature.
- The relative-text parser need not handle every locale; English ("hour"/"day"/"week"/"month"/"year", "today", "yesterday", "just now") is sufficient for the data sources the crawler currently visits.
- The backfill is a one-shot batch operator action; it shares its rate-limit / politeness profile with the verifier (≥3s per URL, jitter 0–1.5s, single Chromium context per batch).
- Re-fetching an `lifecycle='active'` job that has since been closed on LinkedIn is allowed; in that case the backfill leaves `date_posted` NULL and updates `lifecycle='expired'` (same signal the verifier uses).
