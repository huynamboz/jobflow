# Implementation Plan: LinkedIn date_posted extraction + auth-state fix + DB backfill

**Branch**: `002-job-date-posted-extraction` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-job-date-posted-extraction/spec.md`

## Summary

Three threads in one feature, all coupled by the same Playwright-Chromium auth pipeline:

1. **Date extractor** — single function `extract_date_posted(page) -> (date | None, source_tag)` used by both the crawler at ingestion time and the backfill command after the fact. Priority order: `<time datetime>` in the top-card area → JSON-LD `JobPosting.datePosted` → relative-text parse → none.
2. **Auth-state guard** — `browser_pool.open_browser_page` and `linkedin_auth.load_state_path` learn the `li_at` invariant. Refusal to persist on `li_at`-missing exits stops the silent state-rot. A `SESSION_EXPIRED` detection check after every navigation surfaces mid-batch session loss as a clean alert.
3. **Backfill command** `extract_job_dates` — operator entry point that reuses the verifier's batching, browser-pool, and report patterns. Visits only rows with `date_posted IS NULL`, writes either a populated date or marks the row `lifecycle='expired'` (so the next run skips it).

Technical approach: add `ml_service/verifier/date_extractor.py` (pure logic), wire it into both the LinkedIn crawler (`crawler/providers/linkedin_provider.py`) and a new Django management command (`apps/jobs/management/commands/extract_job_dates.py`). Tighten `ml_service/verifier/browser_pool.py` with the auth invariant. No schema migration — `Job.date_posted` field already exists from migration `0007_job_lifecycle`.

## Technical Context

**Language/Version**: Python 3.11 (matches `backend/.venv`)

**Primary Dependencies**: Django 5.x + DRF (existing), Playwright (existing), pytest (existing).

**Storage**: PostgreSQL via Django ORM. Writes only to existing `Job.date_posted`, `Job.lifecycle`, and verification fields — no schema migration.

**Testing**: `pytest backend/tests_ml/test_date_extractor.py` for the pure extractor + relative parser; reuse `tests_ml/test_verifier.py` patterns for the backfill orchestration tests via fakes.

**Target Platform**: Linux/macOS workstation + cron (operator-initiated runs).

**Project Type**: Backend service inside the existing Django project; no frontend.

**Performance Goals**: Backfill 100 LinkedIn URLs in ≤ 15 minutes wall-clock (≤ 9s avg per URL). Pure relative-text parser ≤ 1ms per call. JSON-LD walk ≤ 50ms per page (small DOM).

**Constraints**:
- No new infrastructure (no Celery, no Redis, no async queue) — feature 001 set this precedent.
- Date extractor MUST be a pure function (no I/O beyond the `page` argument).
- Auth-state file MUST never be written without an `li_at` post-check.
- Extracted dates clamped to `[today-730d, today_utc]`; out-of-bound values treated as no date found.

**Scale/Scope**: ~7,134 LinkedIn jobs currently in DB; backfill is a one-shot multi-day operator run at 100/batch, two batches per day.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project constitution at `.specify/memory/constitution.md` remains a placeholder template. No principles ratified, no gates apply. Re-check is a no-op if the constitution is later filled in.

## Project Structure

### Documentation (this feature)

```text
specs/002-job-date-posted-extraction/
├── plan.md                  # This file
├── spec.md                  # Already written
├── research.md              # Phase 0 — design decisions
├── data-model.md            # Phase 1 — entities & state transitions
├── quickstart.md            # Phase 1 — operator runbook (re-login, backfill, monitoring)
├── contracts/
│   ├── date_extractor.md    # extract_date_posted(page) contract
│   └── extract_command.md   # extract_job_dates management command contract
├── checklists/
│   └── requirements.md      # Spec quality checklist (already written)
└── tasks.md                 # Phase 2 — populated by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── apps/
│   └── jobs/
│       └── management/commands/
│           └── extract_job_dates.py             # NEW — operator entry point
├── ml_service/
│   ├── crawler/providers/
│   │   ├── linkedin_provider.py                 # EDIT — call date_extractor, populate RawJob.date_posted
│   │   └── linkedin_auth.py                     # EDIT — load_state_path adds li_at-presence check
│   └── verifier/
│       ├── browser_pool.py                      # EDIT — refuse to persist if li_at missing on exit
│       ├── date_extractor.py                    # NEW — pure (page) -> (date|None, source_tag)
│       └── auth_guard.py                        # NEW — has_li_at(state_dict), guard_state_path(...)
└── tests_ml/
    ├── test_date_extractor.py                   # NEW — pure parser + page-shim tests
    └── test_auth_guard.py                       # NEW — invariant tests, FakeState fixtures
```

**Structure Decision**: All new files live under `ml_service/verifier/` because they share the verifier's Playwright pipeline (browser pool, auth state) and the verifier's domain (lifecycle decisions). The crawler reuses the same extractor by direct import, not by going through a service. This keeps the feature's extension surface obvious: a future Indeed extractor lives next to `date_extractor.py` and the orchestrator never grows.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New module `auth_guard.py` instead of inlining the `li_at` check in `linkedin_auth.py` | The invariant is used by two callers (the verifier's browser pool and the new backfill command) and tested independently of the Playwright loader. Putting it in `linkedin_auth.py` would force every test to import Playwright. | Inlining keeps the invariant scattered across the two call sites; if a future provider forgets to call it, the state-rot bug returns silently. A dedicated module is one extra file in exchange for guaranteeing the invariant is enforced exactly once at every persistence path. |
| Reusing the verifier's `browser_pool` rather than building a backfill-specific browser context manager | The backfill semantically does the same thing as the verifier (open one Chromium context for a batch of LinkedIn URLs, walk URLs, write results). Duplicating the pool would diverge on auth handling — exactly the bug we are fixing. | Building a parallel pool would let the bug we are fixing exist in two places. Reuse is cheaper and removes a duplication-drift surface. |

(No other deviations from the project's existing structure.)
