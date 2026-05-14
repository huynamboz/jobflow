# Implementation Plan: LinkedIn Job Lifecycle Verifier

**Branch**: `001-linkedin-job-verifier` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-linkedin-job-verifier/spec.md`

## Summary

Add lifecycle tracking (`active` / `stale` / `expired` / `unverified`) to the existing `Job` model and a pluggable verifier service that re-checks LinkedIn job pages via the existing Playwright Chromium auth and updates lifecycle accordingly. The matching API filters `expired` jobs out at request time. The verifier registry auto-discovers `JobStatusVerifier` subclasses so adding Indeed/RemoteOK in v2 needs only one new file.

Technical approach: extend `apps/jobs/models.py:Job` (5 new fields + migration). New package `ml_service/verifier/` with `base.py` (ABC + dataclasses), `factory.py` (auto-discovery clone of `ml_service/crawler/factory.py`), `browser_pool.py` (extracted from existing LinkedIn provider), `service.py` (orchestrator with constructor-injected verifier registry + repository + clock), `providers/linkedin_verifier.py`. Django management command `verify_job_status`. Matching service runtime filter. Tests via `pytest` with fake verifier + fake repository.

## Technical Context

**Language/Version**: Python 3.11 (matches existing `backend/.venv`)

**Primary Dependencies**: Django 5.x + DRF (existing), Playwright (existing — already used by `linkedin_provider.py`), `pytest`/`pytest-django` (existing)

**Storage**: PostgreSQL via Django ORM. Lifecycle fields added to `jobs` table.

**Testing**: `pytest backend/tests_ml/test_verifier.py` — unit tests with fakes + one integration smoke that uses the real factory dispatch but a fake verifier instance.

**Target Platform**: Linux/macOS workstation + cron, single-process Django manage.py. No worker queue in v1.

**Project Type**: Backend service inside the existing `backend/` Django project; no frontend changes beyond optional admin badge (deferred).

**Performance Goals**: Batch of 100 LinkedIn URLs in ≤15 minutes wall-clock (≤9s per URL average including 3-5s jitter sleep). Matching API filter adds ≤1 indexed SELECT per request, no measurable latency cost.

**Constraints**:
- No new infrastructure (no Celery, no Redis) in v1.
- Must not refactor existing crawler code beyond extracting Playwright init into the shared pool (additive change only).
- LinkedIn requests must look human-paced (per-URL delay 3s + jitter 0–1.5s).
- Backoff capped at 7 days; verifier never retries within its own backoff window.

**Scale/Scope**: Current DB ~6.2k jobs (Week 11 checkpoint). v1 target: verify ~500 stale LinkedIn jobs per day across two scheduled runs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project constitution file (`.specify/memory/constitution.md`) is a placeholder template at the time of writing — no principles have been ratified. Therefore no gates apply. If a constitution is added later, this plan should be re-checked against it before merge.

## Project Structure

### Documentation (this feature)

```text
specs/001-linkedin-job-verifier/
├── plan.md                  # This file
├── spec.md                  # Feature spec (already written)
├── research.md              # Phase 0 — design decisions and trade-offs
├── data-model.md            # Phase 1 — entities, state transitions, migration
├── quickstart.md            # Phase 1 — operator how-to for running the verifier
├── contracts/
│   ├── verifier_interface.md   # JobStatusVerifier ABC + VerifyResult
│   └── management_command.md   # `verify_job_status` CLI contract
├── checklists/
│   └── requirements.md      # Spec-quality checklist (already written)
└── tasks.md                 # Phase 2 — populated by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── apps/
│   ├── jobs/
│   │   ├── models.py                              # +5 lifecycle fields on Job (existing file, edit)
│   │   ├── migrations/
│   │   │   └── 00xx_job_lifecycle.py              # NEW — adds lifecycle columns + indexes
│   │   ├── services/
│   │   │   └── job_lifecycle_repository.py        # NEW — repository ABC + Django impl
│   │   └── management/commands/
│   │       └── verify_job_status.py               # NEW — operator entry point
│   └── matching/
│       └── services/
│           └── matching_service.py                # EDIT — runtime filter expired jobs
├── ml_service/
│   └── verifier/                                  # NEW package
│       ├── __init__.py
│       ├── base.py                                # NEW — JobStatusVerifier ABC, VerifyResult, JobStatus enum
│       ├── factory.py                             # NEW — auto-discover verifiers (mirrors crawler/factory.py)
│       ├── browser_pool.py                        # NEW — PlaywrightBrowserPool (Chromium context lifecycle)
│       ├── service.py                             # NEW — StatusCheckService orchestrator (DI)
│       ├── selectors/
│       │   └── linkedin.json                      # NEW — expired_markers, active_markers
│       └── providers/
│           ├── __init__.py
│           └── linkedin_verifier.py               # NEW — LinkedInVerifier
└── tests_ml/
    └── test_verifier.py                           # NEW — unit tests + smoke (~80% coverage target)

# Existing files referenced (no edit):
# backend/ml_service/crawler/providers/linkedin_auth.py — load_state_path()
# backend/ml_service/crawler/providers/linkedin_provider.py — pattern reference only
# backend/ml_service/crawler/factory.py              — pattern reference for verifier factory
```

**Structure Decision**: Add a new `ml_service/verifier/` package parallel to `ml_service/crawler/`. The verifier package depends on the crawler package only for `linkedin_auth.load_state_path()` (a stable function, not the LinkedIn provider class). Verifier service is invoked exclusively through `apps/jobs/management/commands/verify_job_status.py`. Matching engine integration is a single ORM filter call in `apps/matching/services/matching_service.py`; engine internals untouched.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New package `ml_service/verifier/` rather than putting verifier inside `ml_service/crawler/` | Crawler fetches data; verifier checks status. Different lifecycle (one runs per-discovery, the other recurring). Sharing the crawler module ties batch scheduling, retry semantics, and tests together unnecessarily. | Keeping verifier inside `crawler/` would force every crawler change to consider verifier impact, and would couple the auto-discovery registries. The marginal cost of a second package (one extra `__init__.py` and `factory.py` clone) is small. |
| Repository ABC (`JobLifecycleRepository`) over direct ORM calls in `StatusCheckService` | The spec requires the service be testable with fakes and no real DB writes. A repository interface is the only way to satisfy this without monkey-patching the ORM. | Calling `Job.objects.update(...)` directly inside the service would make unit tests require a real Django DB; spec acceptance test #4 (no real DB write in tests) would fail. |

(No other deviations from a typical Django-app structure.)
