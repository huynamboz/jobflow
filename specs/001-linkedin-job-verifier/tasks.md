---
description: "Task list — LinkedIn Job Lifecycle Verifier"
---

# Tasks: LinkedIn Job Lifecycle Verifier

**Input**: Design documents from `/specs/001-linkedin-job-verifier/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests ARE in scope (spec acceptance criterion SC-006: ≥80% line coverage). Test tasks are interleaved with implementation; the test FIRST, then the code it covers.

**Organization**: Tasks are grouped by user story (US1, US2, US3) from spec.md. US1 + US2 together are the MVP; US3 is the extensibility proof and may ship in the same release.

## Format: `[ID] [P?] [Story] Description`

- **[P]** — can run in parallel with other [P] tasks of the same phase (different files, no dependency between them).
- **[Story]** — which user story the task primarily serves; foundational tasks have no story tag.

## Path Conventions

Backend Django project under `backend/`. Reference paths follow `plan.md` structure decision exactly.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Lay down the empty package layout so subsequent tasks can land in the right files.

- [ ] T001 Create empty package directory `backend/ml_service/verifier/` with `__init__.py` (empty).
- [ ] T002 Create empty subpackage `backend/ml_service/verifier/providers/` with `__init__.py` (empty).
- [ ] T003 Create empty subdirectory `backend/ml_service/verifier/selectors/` (no `__init__.py` — JSON config dir).
- [ ] T004 [P] Create empty test file `backend/tests_ml/test_verifier.py` with a top-level docstring and one passing assertion to confirm pytest discovers it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migration + verifier ABC + factory. Until these exist, no user-story work can compile.

**⚠️ CRITICAL**: Phase 2 MUST complete before Phase 3/4/5 starts.

- [ ] T005 Edit `backend/apps/jobs/models.py:Job`: add the 5 lifecycle fields per `data-model.md` (`lifecycle`, `last_seen_at`, `last_verified_at`, `verification_attempts`, `verification_backoff_until`) with the documented defaults and indexes. **Leave the `is_active` column definition exactly as is** — do not delete it, do not change its default, do not turn it into a property. Any new code in this feature MUST read `lifecycle`; nothing in this feature MUST write to `is_active`.
- [ ] T006 Generate Django migration `backend/apps/jobs/migrations/00xx_job_lifecycle.py`: schema add + composite index `(platform_id, lifecycle)` + backfill `lifecycle='active'`, `last_seen_at=created_at`, `verification_attempts=0`, others NULL.
- [ ] T007 [P] Write `backend/ml_service/verifier/base.py`: `JobStatus` enum, `VerifyResult` frozen dataclass, `JobStatusVerifier` ABC — exact shapes from `contracts/verifier_interface.md`.
- [ ] T008 [P] Write `backend/ml_service/verifier/factory.py`: auto-discovery scanning `providers/`, registry dict, `get_verifier(name)`, `get_verifier_for_url(url)`, `list_verifiers()`. Mirror the structure of `backend/ml_service/crawler/factory.py`.
- [ ] T009 [P] [US1] Add unit test `test_factory_dispatch_by_name` and `test_factory_dispatch_by_url` in `tests_ml/test_verifier.py` using a `FakeVerifier` defined in-test. (Must fail until T008 is done, then pass.)
- [ ] T010 [P] [US1] Add unit test `test_factory_rejects_duplicate_name` in the same file. (Must fail until T008 enforces the rule, then pass.)
- [ ] T011 [P] [US1] Add unit test `test_factory_skips_broken_provider_module` (registers a fake broken module path, expects WARNING log, registry stays usable). Must fail until T008 implements the graceful skip.

**Checkpoint**: Migration applied, ABC + factory implemented and tested. Stories can now be built in parallel where the file boundaries allow.

---

## Phase 3: User Story 1 — Hide expired jobs from recommendations (Priority: P1) 🎯 MVP

**Goal**: A CV-to-jobs request never returns a job whose `lifecycle='expired'`.

**Independent Test**: Insert a fake "expired" job into the DB and confirm it is filtered from the matching API response while other rankings are preserved.

### Tests for US1 (write first)

- [ ] T012 [P] [US1] In `tests_ml/test_verifier.py`, add `test_matching_filter_drops_expired` — mocks the engine to return job_ids `[1,2,3,4,5]`; pre-populates `Job` rows where id=3 has `lifecycle='expired'`; calls the matching-service filter function; asserts result excludes 3 and preserves order `[1,2,4,5]`.
- [ ] T013 [P] [US1] Add `test_matching_filter_keeps_unverified_and_stale` — same setup with id=3 lifecycle='unverified', id=5 'stale'; asserts both stay.

### Implementation for US1

- [ ] T014 [US1] Edit `backend/apps/matching/services/matching_service.py`: after engine returns `top_k_job_ids`, apply the ORM filter from `data-model.md` (`lifecycle__in=['active','stale','unverified']`) and reorder by the engine's original order. Add a small helper function `_filter_active_jobs(ranked_ids: list[int]) -> list[int]` so the filter is unit-testable in isolation.
- [ ] T015 [P] [US1] Add `lifecycle` to the matching API response payload (`MatchResponse` / `JobMatchResult`) so admin UI can later show a badge. Field name: `lifecycle`. No UI work in this task.

**Checkpoint**: US1 done — expired jobs are filtered runtime. Tests pass. No verifier yet (lifecycle column populated via SQL by hand for the test).

---

## Phase 4: User Story 2 — Operator runs the verifier on a schedule (Priority: P1)

**Goal**: One command verifies a batch of LinkedIn jobs and updates lifecycle/timestamps.

**Independent Test**: Run `python manage.py verify_job_status --platform linkedin --batch 5 --dry-run` end-to-end with the real LinkedIn provider and inspect the report.

### Tests for US2 (write first)

- [ ] T016 [P] [US2] Add `test_repository_apply_result_active_resets_backoff` to `test_verifier.py` — exercises `DjangoJobLifecycleRepository.apply_result` with `JobStatus.ACTIVE` and asserts `last_verified_at` set, attempts=0, backoff=NULL.
- [ ] T017 [P] [US2] Add `test_repository_apply_result_error_increments_backoff` — calls `apply_result` with `ERROR`, attempts goes from N to N+1, `backoff_until = now + 2^(N+1)·1h`. Include a second sub-case with `attempts=20` asserting backoff is capped at exactly 7 days.
- [ ] T017b [P] [US2] Add `test_repository_apply_result_revives_expired_job` — fixture row with `lifecycle='expired'`, `last_verified_at=now-30d`; apply `VerifyResult(ACTIVE)`; assert lifecycle becomes `active`, `last_verified_at=now`, `verification_attempts=0`, `verification_backoff_until=None`. (Covers FR-013 — employer re-opens a closed job.)
- [ ] T018 [P] [US2] Add `test_repository_apply_result_session_expired_is_noop` — attempts/backoff/lifecycle/last_verified_at all unchanged.
- [ ] T019 [P] [US2] Add `test_service_check_batch_with_fake_verifier` — `StatusCheckService` with `FakeVerifier({url1: ACTIVE, url2: EXPIRED, url3: ERROR})` and `FakeRepository`; asserts report counts and that the repository was called once per URL with the matching `VerifyResult`.
- [ ] T020 [P] [US2] Add `test_service_skips_unsupported_url` — fake verifier whose `supports()` returns False for url2; service still calls it for url1/url3, url2 increments `skipped_unsupported_url`.
- [ ] T021 [P] [US2] Add `test_service_session_expired_alert_fires_once` — batch of 5 all return `SESSION_EXPIRED`; report carries `session_expired_count=5`; repository is called but lifecycle/attempts untouched (per Decision 5/data-model).
- [ ] T022 [P] [US2] Add `test_service_aging_promotes_stale` — fake clock + repository with `date_posted=now-15d` and `lifecycle='active'`; `check_batch` first applies aging then picks rows; the row appears in the candidate set as `stale`.
- [ ] T023 [P] [US2] Add `test_service_respects_backoff_window` — row with `verification_backoff_until=now+1h` is not picked; same row with `backoff_until=now-1m` is picked.
- [ ] T024 [P] [US2] Add `test_dry_run_skips_repository_writes` — `check_batch(..., dry_run=True)` returns the same report but `FakeRepository.apply_result` is never called.
- [ ] T024b [P] [US2] Add `test_service_batch_perf_budget` — fake verifier whose `verify_batch` returns `ACTIVE` for 100 URLs after sleeping a fixed `50ms` per URL (proxy for the 3–5s real LinkedIn pacing); assert total wall-clock <16 seconds. Documents the SC-002 budget (≤15 min wall-clock for 100 real URLs ≈ ≤9s per URL average). If this fails, the service is doing per-URL overhead that production cannot afford.

### Implementation for US2

- [ ] T025 [US2] Write `backend/ml_service/verifier/browser_pool.py`: `PlaywrightBrowserPool` context manager that loads storage state, yields a `Page`, refreshes storage state on exit. Extract pattern from `linkedin_provider.py`.
- [ ] T026 [P] [US2] Write `backend/ml_service/verifier/selectors/linkedin.json` with three top-level keys: `auth_check.expired_url_patterns` (copy from existing `linkedin_selectors.json`), `expired_markers` (3–5 selectors), `active_markers` (2–3 selectors). **JSON commenting convention (pinned)**: plain JSON (no JSON5, no `//`). For each top-level array, include a sibling string field `<key>_doc` (e.g., `expired_markers_doc`) summarizing the selectors' source and intent in one sentence. Selector list entries themselves are plain strings — no per-line annotation.
- [ ] T027 [US2] Write `backend/ml_service/verifier/providers/linkedin_verifier.py`: `LinkedInVerifier` implementing the contract. `supports()` matches `linkedin.com/jobs/`. `verify_batch()` opens one `PlaywrightBrowserPool` and inspects each URL in the documented detection order (session → expired → active → unknown). Per-URL sleep `3s + uniform(0,1.5)`. `verify(url)` delegates to `verify_batch([url])[0]`.
- [ ] T028 [US2] Add helper `linkedin_clean_url(url) -> str` inside the provider module (or `ml_service/verifier/url_utils.py`): regex `linkedin\.com/jobs/view/(\d+)` → canonical form. Used before passing the URL to Playwright.
- [ ] T029 [US2] Write `backend/apps/jobs/services/job_lifecycle_repository.py`: `JobLifecycleRepository` ABC + `DjangoJobLifecycleRepository` ORM impl with the exact write table from `data-model.md`. Include `apply_result(job_id, verify_result, clock_now)` and `find_to_verify(platform, batch, clock_now)`.
- [ ] T030 [US2] Write `backend/ml_service/verifier/service.py`: `StatusCheckService` with constructor-injected `verifier_registry`, `repository`, `clock`. Methods: `check_batch(platform, batch, dry_run)` → `StatusCheckReport`. Apply aging rule before candidate selection. Per-URL exception handling wraps into `VerifyResult(ERROR, ...)`. Build the report from accumulating counters.
- [ ] T031 [US2] Write `backend/apps/jobs/management/commands/verify_job_status.py`: argparse contract from `contracts/management_command.md`. Wire factory → service → repository. Print human report; optional JSON report. Exit codes per the contract.
- [ ] T032 [US2] Add to the management command: structured-logging line (single JSON dict) on completion when `--json-report` is set, going to stdout (not stderr).
- [ ] T033 [US2] Manual smoke per `quickstart.md`: insert 5 known LinkedIn jobs (3 active + 2 expired), run `verify_job_status --batch 5 --dry-run`, confirm `active:3, expired:2` in the report. Then run without `--dry-run` and confirm DB writes match the spec. Document the 5 URLs in a private note (not in the repo).

**Checkpoint**: US2 done — verifier runs end-to-end, DB updates correctly. Combined with US1, the system now filters expired jobs and refreshes lifecycle daily.

---

## Phase 5: User Story 3 — New platform integration costs only one file (Priority: P2)

**Goal**: Adding a new platform verifier requires no edits to service, command, or schema.

**Independent Test**: Drop a stub verifier file for a fake platform, confirm the management command routes a URL to it without code changes elsewhere.

### Tests for US3 (write first)

- [ ] T034 [P] [US3] Add `test_di_proof_new_provider_autodiscovered` to `test_verifier.py` — writes a temp module into the test's `monkeypatch`-managed copy of `providers/`, imports the factory, asserts the new verifier's `name` is in `list_verifiers()`.
- [ ] T035 [P] [US3] Add `test_di_proof_url_dispatch` — registers two fakes with different `supports()` patterns; asserts `get_verifier_for_url` returns the right one for each test URL.
- [ ] T036 [P] [US3] Add `test_di_proof_service_works_with_two_providers` — `StatusCheckService` configured with both fakes; batch with mixed URLs; each URL is verified by the correct fake; report aggregates correctly.

### Implementation for US3

No new production files are needed — US3 is satisfied iff Phase 2 (T008) implements the factory correctly. The tests in T034–T036 are the *verification* that the DI promise holds. If any test fails, the fix lands inside `factory.py` or `service.py`, not in a parallel codepath.

- [ ] T037 [US3] If T034–T036 reveal an architectural leak (e.g., LinkedIn name hardcoded in service), refactor accordingly and update the relevant Phase 2/4 code. Do not paper over with conditionals.

**Checkpoint**: US3 done — DI promise is enforced by tests. The codebase is ready to receive a second platform (Indeed, RemoteOK) without churn.

---

## Phase 6: Polish & Cross-cutting

**Purpose**: Documentation, coverage, and any cleanup the user stories pulled into focus.

- [ ] T038 Run `pytest backend/tests_ml/test_verifier.py --cov=ml_service.verifier --cov=apps.jobs.services.job_lifecycle_repository --cov=apps.jobs.management.commands.verify_job_status --cov=apps.matching.services.matching_service --cov-report=term-missing`. Coverage MUST be ≥80% (SC-006). Add tests to close any uncovered branches.
- [ ] T039 [P] Add a `verify_job_status` row to the project's README crawler section listing the new command and a link to `specs/001-linkedin-job-verifier/quickstart.md`.
- [ ] T040 [P] Confirm **no code added by this feature** writes to `is_active`. Existing reads/writes outside this feature are left untouched — the v2 deprecation will handle them. Verify with `grep -rn 'is_active\s*=' backend/apps/jobs/ backend/apps/matching/ backend/ml_service/verifier/ backend/apps/jobs/management/`; only matches should be in code that pre-existed this branch.
- [ ] T041 Delete the placeholder `JD Extraction Record.lifecycle` accidentally added in a draft, if any. (Sanity check; should be a no-op if Phase 2 followed the plan.)
- [ ] T042 Commit message preview — separate commits per phase (Phase 1 setup, Phase 2 foundational, Phase 3 US1, Phase 4 US2, Phase 5 US3, Phase 6 polish). Reference task IDs in each commit body.

---

## Dependency graph (tasks)

```text
T001/T002/T003 (setup) ──► T005 (Job migration prep)
                          │
                          ▼
                       T006 (migration apply) ──► [DB ready]
                                                  │
T007 (base.py)  ──┐                               │
T008 (factory)  ──┴── T009/T010/T011 (factory tests)
                                                  │
[after Phase 2]                                   │
                                                  │
US1: T012/T013 (tests)  ──► T014 (filter)  ──► T015 (response field)
                                                  │
US2: T016..T024 (tests, parallel)  ──► T025 (browser pool) ──► T027 (verifier)
                                       T026 (selectors)    ──┘
                                       T028 (clean_url)
                                       T029 (repository) ──┐
                                       T030 (service)     ─┴──► T031 (command) ──► T032 (json log) ──► T033 (smoke)
                                                  │
US3: T034..T036 (tests, use factory + service)
                                                  │
Phase 6: T038 (coverage)  ──► T039/T040/T041 (cleanup, parallel)  ──► T042 (commit hygiene)
```

## Estimated effort

| Phase | Hours |
|-------|-------|
| 1 Setup | 0.5 |
| 2 Foundational (migration + ABC + factory + tests) | 1.5 |
| 3 US1 (filter + tests) | 0.75 |
| 4 US2 (verifier + service + command + tests + smoke) | 4.5 |
| 5 US3 (DI proof tests) | 0.5 |
| 6 Polish (coverage + docs) | 1.0 |
| **Total** | **~8.75h** |

Three-quarters of the work is in Phase 4 (US2). Phases 1, 2, 3, 5 can be done in a single morning sitting.

## Parallelism guidance

Within a phase, [P] tasks can be worked on by separate agents/threads safely.

- Phase 2: T007 + T008 in parallel (one file each), then T009–T011 in parallel.
- Phase 3: T012 + T013 in parallel, then T014 sequentially, then T015 in parallel with the start of Phase 4.
- Phase 4: T016–T024 all in parallel (one test each, same file but distinct test functions — split by author if multiple hands). Then T025/T026/T028 in parallel, then T027, then T029, then T030, then T031.
- Phase 5: T034–T036 in parallel.
