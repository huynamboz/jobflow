---
description: "Task list — LinkedIn date_posted extraction + auth-state fix + DB backfill"
---

# Tasks: LinkedIn date_posted extraction + auth-state fix + DB backfill

**Input**: Design documents from `/specs/002-job-date-posted-extraction/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: In scope (SC-006 ≥ 80% coverage). Tests are written first per task; the production code follows.

**Organization**: Tasks grouped by user story (US1 = date extraction; US2 = backfill; US3 = auth-state fix).
US3 ships in the same PR because the date extractor would inherit the same auth-state-rot bug otherwise.

## Format: `[ID] [P?] [Story] Description`

- **[P]** — parallelizable within phase (distinct files, no inter-dep).

## Path Conventions

`backend/` Django project. Paths match `plan.md` structure decision.

---

## Phase 1: Setup

- [ ] T001 [P] Create empty test file `backend/tests_ml/test_date_extractor.py` (docstring + pass assertion).
- [ ] T002 [P] Create empty test file `backend/tests_ml/test_auth_guard.py` (docstring + pass assertion).

---

## Phase 2: Foundational (US3 auth-state fix — blocks everything else because the page-opening code path it touches is shared)

**⚠️ CRITICAL**: This phase MUST complete before Phase 3 (US1) and Phase 4 (US2) because both rely on the hardened `open_browser_page` and the new `auth_guard` module.

### Tests for US3 (write first)

- [ ] T003 [P] [US3] In `test_auth_guard.py`, add `test_has_li_at_true_when_cookie_present` — feed a fake state dict with `cookies=[{name:"li_at", domain:".linkedin.com", ...}]`; assert `has_li_at(state)` returns True.
- [ ] T004 [P] [US3] Add `test_has_li_at_false_when_cookie_missing` — empty cookies → False; cookies with `li_at` but wrong domain → False; cookies without `li_at` → False.
- [ ] T005 [P] [US3] Add `test_load_state_path_returns_none_when_invariant_broken` — write a tempfile with no `li_at` cookie; call `load_state_path` (now invariant-aware); assert returns None.
- [ ] T006 [P] [US3] Add `test_persist_skipped_when_invariant_broken` — set up a tempfile with valid `li_at`. Simulate the persist flow with a fake "current state" missing `li_at`. Assert the file on disk is byte-identical after.
- [ ] T007 [P] [US3] Add `test_persist_writes_when_invariant_holds` — fake current state has `li_at`. Assert file is updated.

### Implementation for US3

- [ ] T008 [US3] Write `backend/ml_service/verifier/auth_guard.py` with:
  - `has_li_at(state: dict) -> bool` — pure function on Playwright storage-state dict.
  - `read_state(path: str) -> dict | None` — load + guard; returns None if invariant fails (logs WARNING with reason).
  - `persist_state(path: str, state: dict) -> bool` — write only if `has_li_at(state)`; returns True iff written.
- [ ] T009 [US3] Edit `backend/ml_service/crawler/providers/linkedin_auth.py:load_state_path` to delegate to `auth_guard.read_state` and return None when invariant fails. Update its docstring.
- [ ] T010 [US3] Edit `backend/ml_service/verifier/browser_pool.py` — replace the unconditional `ctx.storage_state(path=storage_state_path)` on exit with `auth_guard.persist_state(path, ctx.storage_state())`.
- [ ] T011 [US3] Edit `browser_pool.open_browser_page` — at function start, after loading storage_state, call `has_li_at` on the loaded dict; if False, raise a clear `RuntimeError("Auth state missing li_at — re-run linkedin_auth.py")` before launching Chromium. Callers (verifier service, future extract service) catch and report.
- [ ] T011b [US3] Edit `ml_service/verifier/service.py:StatusCheckService.check_batch` — after each `verify` call returns, if it returned `SESSION_EXPIRED`, immediately break the loop (do not continue draining remaining candidates). The current code already counts but does not stop. Also extend `LinkedInVerifier.verify_batch` (or its inner loop) to call `ctx.cookies()` after each `page.goto()` and short-circuit to `VerifyResult(SESSION_EXPIRED, reason='li_at lost mid-navigation')` if `li_at` is gone — implements FR-014 mid-batch detection. Add test `test_verifier_stops_on_first_session_expired` to `test_verifier.py`.
- [ ] T012 [US3] Update `apps/jobs/management/commands/verify_job_status.py` to catch the new `RuntimeError`, print the operator instruction, and exit code `2` (matches the contract).
- [ ] T013 [US3] Update existing test `tests_ml/test_verifier.py` smoke run instructions in the docstring to mention re-login if you see the new error. (No test code change needed.)

**Checkpoint**: `pytest tests_ml/test_auth_guard.py` passes. The 19 verifier tests still pass. `python manage.py verify_job_status --platform linkedin --batch 5` aborts cleanly with exit `2` if the state file lacks `li_at`.

---

## Phase 3: User Story 1 — Extractor produces real dates (Priority: P1)

**Goal**: A single pure function `extract_date_posted(page)` reliably returns an absolute date for LinkedIn job pages, or None.

**Independent Test**: Pass a `FakePage` to the extractor; verify each of the four source paths (datetime-attribute, json-ld, relative-text, expired-redirect) is selected in priority order.

### Tests for US1 (write first)

- [ ] T014 [P] [US1] In `test_date_extractor.py`, add `test_parse_relative_basic_units` — pass {"today", "yesterday", "1 hour ago", "3 days ago", "2 weeks ago", "5 months ago", "1 year ago"} with a fixed `now`; assert each yields the documented absolute date.
- [ ] T015 [P] [US1] Add `test_parse_relative_singular_plural` — "1 day ago" and "3 days ago" both parse; "1 minute ago" and "5 minutes ago" both → `now.date()` (sub-day collapses).
- [ ] T016 [P] [US1] Add `test_parse_relative_prefix_handling` — "Posted 2 weeks ago" and "Reposted 1 day ago" both parse correctly; case-insensitive.
- [ ] T017 [P] [US1] Add `test_parse_relative_unmatched_returns_none` — random garbage / empty string → None.
- [ ] T018 [P] [US1] Add `test_guardrail_rejects_future_date` — feed a date 5 days in the future; expect None.
- [ ] T019 [P] [US1] Add `test_guardrail_rejects_too_old_date` — feed a date 3 years ago; expect None.
- [ ] T020 [P] [US1] Add `test_extract_priority_expired_redirect` — `FakePage(url="https://linkedin.com/jobs/foo?trk=expired_jd_redirect")`; assert result `(None, "expired-redirect")` regardless of other content present.
- [ ] T021 [P] [US1] Add `test_extract_priority_json_ld_beats_relative` — FakePage exposes JSON-LD with `datePosted=2026-04-15` AND a `<time datetime>` AND relative text; result is `(2026-04-15, "json-ld")`.
- [ ] T022 [P] [US1] Add `test_extract_priority_datetime_beats_relative` — no JSON-LD, but a scoped `<time datetime="2026-05-01">` AND relative text "1 month ago"; result is `(2026-05-01, "datetime-attribute")`.
- [ ] T023 [P] [US1] Add `test_extract_falls_back_to_relative` — no JSON-LD, no `<time>`, but relative text "1 week ago"; result is `(today-7d, "relative-text")`.
- [ ] T024 [P] [US1] Add `test_extract_unscoped_time_in_more_jobs_panel_is_ignored` — `<time>` elements present only in selectors NOT in the scoped allow-list (e.g., `.people-also-viewed time`); extractor must NOT pick them. Result: `(None, "none")` if nothing else matches.
- [ ] T025 [P] [US1] Add `test_extract_json_ld_picks_jobposting_among_many` — page exposes 3 JSON-LD blocks with `@type` values `Organization`, `BreadcrumbList`, `JobPosting`; extractor selects the `JobPosting` block.
- [ ] T026 [P] [US1] Add `test_extract_returns_utc_midnight` — when result is non-None, assert `result.date.tzinfo` is `timezone.utc` and `result.date.hour == 0`.
- [ ] T027 [P] [US1] Add `test_extract_does_not_raise_on_broken_json_ld` — JSON-LD block contains malformed JSON; extractor swallows the error and continues to next source.

### Implementation for US1

- [ ] T028 [US1] Write `backend/ml_service/verifier/date_extractor.py`:
  - `DateExtractionResult` frozen dataclass (per contract).
  - `_GUARDRAIL_MAX_AGE_DAYS = 730`.
  - `parse_relative(text: str, now: datetime) -> datetime | None` — regex-based parser per research.md Decision 2.
  - `_apply_guardrails(date: datetime, now: datetime) -> datetime | None` — clamp logic.
  - `_extract_from_json_ld(page) -> datetime | None` — iterate `script[type=application/ld+json]`, pick `@type==JobPosting`.
  - `_extract_from_datetime_attribute(page) -> datetime | None` — scoped selectors only (top-card / tertiary-info / posted-time-ago).
  - `_extract_from_relative_text(page) -> datetime | None` — same scoped containers; pass text through `parse_relative`.
  - `extract_date_posted(page) -> DateExtractionResult` — orchestrator. Order: expired-redirect → json-ld → datetime-attribute → relative-text → none.
- [ ] T029 [US1] Add structured logger calls at INFO level for each successful extraction (source tag + date). Keep failure paths at DEBUG to avoid log noise.

**Checkpoint**: All `test_date_extractor.py` tests pass. The extractor module has no Django/Playwright runtime dependencies (tested with a `FakePage`).

---

## Phase 4: User Story 2 — Backfill command + crawler integration (Priority: P1)

**Goal**: Operator runs `extract_job_dates`; existing rows get `date_posted` populated. Future crawls also populate.

**Independent Test**: Pre-populate the FakeRepository with 5 rows (`date_posted=None`); run the orchestrator with a scripted FakeVerifier-style extractor; assert 5 rows updated, dry-run flag inverts to zero writes.

### Tests for US2 (write first)

- [ ] T030 [P] [US2] In `test_date_extractor.py` (or new `test_extract_command.py` — choose by file size), add `test_backfill_orchestrator_writes_date_when_populated` — fake repository, fake extractor returns `(date, "json-ld")`; assert `apply_date(job_id, date)` was called once.
- [ ] T031 [P] [US2] Add `test_backfill_orchestrator_marks_expired_on_redirect` — fake extractor returns `(None, "expired-redirect")`; assert lifecycle written to `expired` and `date_posted` left untouched.
- [ ] T032 [P] [US2] Add `test_backfill_orchestrator_increments_attempts_on_none` — fake extractor returns `(None, "none")`; assert `verification_attempts` +1 and backoff set; `date_posted` untouched.
- [ ] T033 [P] [US2] Add `test_backfill_dry_run_skips_writes` — same setup as T030, `dry_run=True`; assert no `apply_date`, no `apply_result` calls; report still has `populated_count=1`.
- [ ] T034 [P] [US2] Add `test_backfill_candidate_selection_skips_filled` — repository contains rows with both `date_posted=None` and `date_posted=<some date>`; only the NULL rows appear in the candidate set.
- [ ] T035 [P] [US2] Add `test_backfill_session_expired_stops_batch` — fake extractor returns `(None, "session_expired")` on the 3rd URL; assert URLs 4+ are NOT visited, report has `session_expired_count=1`.
- [ ] T035b [P] [US2] Add `test_backfill_service_isolates_per_url_exceptions` — fake extractor raises on URL #3 of 5; service continues to URLs 4, 5; report records `error_count=1, total_examined=5` (FR-015 service-level coverage).

### Implementation for US2

- [ ] T036 [US2] Extend `backend/apps/jobs/services/job_lifecycle_repository.py`:
  - Add `apply_date(job_id: int, date: datetime, *, now: datetime) -> None` to `JobLifecycleRepository` ABC and Django impl — writes only `date_posted` and `updated_at`.
  - Add `find_to_backfill_dates(*, platform: str, batch: int, now: datetime) -> list[dict]` — runs the candidate query from data-model.md.
- [ ] T037 [US2] Write `backend/ml_service/verifier/backfill_service.py` (NEW) — `DateBackfillService` mirror of `StatusCheckService`: constructor takes extractor function, repository, clock, browser_pool factory. `run(platform, batch, dry_run) -> BackfillReport`. The per-URL loop MUST:
  - Call `page.goto(url)` (wrapped in try/except — exceptions count as ERROR).
  - Call `ctx.cookies()` and check `auth_guard.has_li_at(...)`; if False, break the loop with `session_expired_count += remaining_urls` (per FR-014).
  - Call `extract_date_posted(page)`; dispatch result to the repository per data-model.md write semantics.
  - Wrap each iteration in try/except so one bad URL doesn't kill the batch (FR-015).
- [ ] T038 [US2] Write `backend/apps/jobs/management/commands/extract_job_dates.py` — argparse, wire factory → service → repo, print report. Mirror `verify_job_status.py` structure.
- [ ] T039 [US2] Edit `backend/ml_service/crawler/providers/linkedin_provider.py`:
  - Import `extract_date_posted` from `ml_service.verifier.date_extractor`.
  - Replace the lines 283-294 block (and `seniority_hint=date_posted_text` line) with `result = extract_date_posted(page)` and pass `date_posted=result.date` to the `RawJob(...)` constructor.
  - Remove the now-dead `seniority_hint=date_posted_text` argument (or set to `""`).
- [ ] T040 [US2] Verify `RawJob` dataclass has a `date_posted` field; if missing, add it as `datetime | None = None`. Verify the crawler → Job pipeline (`apps/jobs/services/job_service.py` or wherever RawJob → Job translation lives) reads `RawJob.date_posted` and writes `Job.date_posted` on insert.
- [ ] T041 [US2] Manual smoke per `quickstart.md` Step 0-2: re-login → dry-run batch 5 → real batch 50 → verify DB has populated rows.

**Checkpoint**: Real run on 50 LinkedIn URLs populates `date_posted` for ~70-80% of them. Repeated runs are no-ops on filled rows.

---

## Phase 5: Polish

- [ ] T042 Run full test suite: `pytest tests_ml/test_verifier.py tests_ml/test_date_extractor.py tests_ml/test_auth_guard.py --cov=ml_service.verifier --cov=apps.jobs --cov-report=term-missing`. Coverage ≥ 80% (SC-006). Add tests for any uncovered branch.
- [ ] T043 [P] Update `roadmap/architecture.md` "Crawl" section with a one-paragraph note: dates come from extractor, not from relative text storage. Link to specs/002 quickstart.
- [ ] T044 [P] Grep for stale references to `seniority_hint=date_posted_text` and similar in the codebase; remove or correct.
- [ ] T045 Manual end-to-end on at least 200 rows: confirm SC-001 (≥80% active rows get a date) and SC-002 (100% expired rows stay NULL).
- [ ] T046 Commit in 3 phased commits: (a) US3 auth-state fix, (b) US1 extractor module, (c) US2 backfill command + crawler integration. Each commit references the task IDs in its body.

---

## Dependency graph

```text
T001/T002 (setup)
        │
        ▼
Phase 2 [US3] — T003..T007 (tests) → T008 (auth_guard) → T009/T010/T011 (wire into existing pipeline) → T012 (command exit code) → T013 (doc)
        │
        ▼  [GATE: Phase 2 done — open_browser_page now refuses to silently degrade auth]
        │
Phase 3 [US1] — T014..T027 (tests, all [P]) → T028 (extractor impl) → T029 (logging)
        │
        ▼
Phase 4 [US2] — T030..T035 (tests, all [P]) → T036 (repository extension) → T037 (service) → T038 (command) → T039 (crawler integration) → T040 (RawJob plumbing audit) → T041 (manual smoke)
        │
        ▼
Phase 5 — T042 (coverage) → T043/T044 (docs) → T045 (e2e validation) → T046 (commits)
```

## Estimated effort

| Phase | Hours |
|-------|-------|
| 1 Setup | 0.25 |
| 2 Foundational (US3 auth-guard) | 1.5 |
| 3 US1 (extractor + tests) | 2.5 |
| 4 US2 (backfill + crawler integration) | 3.0 |
| 5 Polish | 1.5 |
| **Total** | **~8.75h** |

Phase 4 dominates because the backfill orchestrator + crawler integration + Django repo extension all live there. US3 is small but blocking; doing it first prevents the new code from inheriting the bug it exists to fix.

## Parallelism guidance

- Phase 2 tests T003–T007 in parallel; impl T008 standalone, then T009/T010/T011 parallel.
- Phase 3 tests T014–T027 all in parallel; impl T028 single big file; T029 trivial.
- Phase 4 tests T030–T035 parallel; impl T036 then T037 then T038 (sequential, each builds on previous); T039 + T040 parallel (different files).
