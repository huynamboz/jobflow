---
description: "Task list — Admin Dashboard v2 (cards + charts)"
---

# Tasks: Admin Dashboard v2

**Input**: Design docs in `/specs/003-admin-dashboard-v2/`.

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md.

**Tests**: ≥75% coverage on new dashboard components + data hooks (SC-006). Backend service tests + frontend component tests.

**Organization**: Tasks grouped by user story.

## Format: `[ID] [P?] [Story] Description`

- **[P]** — parallelizable within phase
- **[Story]** — US1 (operator health) / US2 (catalog & freshness) / US3 (verifier-extractor ops)

## Path Conventions

`backend/` Django; `admin/src/` React.

---

## Phase 1: Setup

- [ ] T001 [P] Add `recharts` to `admin/package.json` dependencies. Run `npm install`.
- [ ] T002 [P] Create new Django app: `python manage.py startapp admin_dashboard apps/admin_dashboard`. Register in `config/settings.py:INSTALLED_APPS`.
- [ ] T003 [P] Create empty folders + index files: `admin/src/components/dashboard/`, `admin/src/components/dashboard/charts/`, `admin/src/components/__tests__/dashboard/`.
- [ ] T004 [P] Create empty type module `admin/src/types/dashboard.types.ts` with the 6 payload interfaces from data-model.md.

---

## Phase 2: Foundational — `VerifierRunLog` model + write-from-commands

**⚠️ Blocking**: every trend/recent-runs feature depends on this table existing and being populated. Do this BEFORE Phase 3-5.

- [ ] T005 Edit `apps/jobs/models.py`: add `VerifierRunLog` model per data-model.md (8 columns, composite index `(command, started_at)`).
- [ ] T006 `python manage.py makemigrations jobs --name verifier_run_log`. Inspect generated migration; ensure no other fields drift in.
- [ ] T007 Edit `apps/jobs/management/commands/verify_job_status.py`: after `_print_report`, insert a `VerifierRunLog` row with the run's data. Wrap insert in try/except + log warning on failure; never propagate to exit code.
- [ ] T008 Edit `apps/jobs/management/commands/extract_job_dates.py`: same — insert a `VerifierRunLog` row at run end.
- [ ] T009 [P] Add `test_verifier_run_log_written` in `tests_ml/test_verifier.py`: fake repo + service; run `check_batch`; assert one `VerifierRunLog` row exists with expected counts. *Skip if Django ORM is not available in unit tests; cover via integration smoke instead.*

**Checkpoint**: a real `verify_job_status` run creates a `verifier_run_logs` row visible in psql.

---

## Phase 3: Backend endpoints (parallel)

All 6 endpoints can be developed in parallel once Phase 2 is done.

### Shared scaffolding

- [ ] T010 Write `apps/admin_dashboard/urls.py` with all 6 paths.
- [ ] T011 Add `path("admin-dashboard/", include("apps.admin_dashboard.urls"))` to the root URLconf.
- [ ] T012 Write `apps/admin_dashboard/views.py` skeleton: 6 APIView classes, all initially returning `{"success": False, "error": {"code": "NOT_IMPLEMENTED"}}`. Confirms wiring before adding logic.
- [ ] T013 Write `apps/admin_dashboard/serializers.py` with the 6 response shapes (DRF Serializers OR plain dicts — author choice; consistency over the file).

### Per-section logic + tests

- [ ] T014 [P] [US1] `services.compute_kpi(now)` — query lifecycle counts, CV counts, latest VerifierRunLog rows per command, auth_guard.read_state probe, checkpoint metadata. Add `test_compute_kpi_*` tests (happy / empty DB / auth-state missing).
- [ ] T015 [P] [US2] `services.compute_catalog(now)` — 4 ORDER BY count DESC arrays. Tests: happy with mixed platforms, empty.
- [ ] T016 [P] [US2] `services.compute_freshness(*, days_added=30, days_outcomes=14)` — 2 time series with `date_trunc('day', ...)`. Tests: clamps to max windows, returns zero-rows-included.
- [ ] T017 [P] [US3] `services.compute_ops(*, recent_runs_limit=20)` — 2 coverage percentages + most-recent runs. Tests: coverage math correct on edge cases (0 jobs, 0 verified).
- [ ] T018 [P] `services.compute_labeling(now)` — wraps existing labeling stats service so the dashboard root has a parallel labeling endpoint. Test: mirrors `/api/labeling/stats/`.
- [ ] T019 [P] `services.compute_model(now)` — reads `<settings.ML_CHECKPOINT_DIR>/meta.json` (the active-checkpoint convention pinned in data-model.md). Returns all-null fields if the file is missing or unreadable. Test: no-file case, malformed-JSON case, complete-meta case.

### Wire endpoints to services

- [ ] T020 Replace each NOT_IMPLEMENTED view body with a call to the corresponding `services.compute_*` and wrap in the `{success, data}` envelope.
- [ ] T021 Add `permission_classes = [IsAuthenticated]` to all 6 views.
- [ ] T022 Run all backend tests; confirm 6 endpoints respond as documented in `contracts/dashboard_api.md`.
- [ ] T022b Add `test_endpoint_perf_smoke` in `tests_ml/test_dashboard_endpoints.py` (closes SC-002 gap): seed a fixture DB with 5,000 Job rows + 100 `VerifierRunLog` rows; call each `compute_*` service function; assert each returns in <500ms wall-clock. Pure pytest, no HTTP. Use `time.perf_counter()`.

**Checkpoint**: `curl http://localhost:8000/api/admin-dashboard/kpi/` returns valid JSON with the documented shape.

---

## Phase 4: Frontend — shared scaffolding + chart wrappers

- [ ] T023 [P] Write `admin/src/services/dashboard.service.ts` per `contracts/dashboard_ui.md`. Six fetch methods, unwrap `data` from envelope.
- [ ] T024 [P] Write `admin/src/components/dashboard/SectionCard.tsx` per UI contract (loading/error/empty/success branches).
- [ ] T025 [P] Write `admin/src/components/dashboard/charts/Donut.tsx`.
- [ ] T026 [P] Write `admin/src/components/dashboard/charts/BarH.tsx`.
- [ ] T027 [P] Write `admin/src/components/dashboard/charts/AreaSeries.tsx`.
- [ ] T028 [P] Write `admin/src/components/dashboard/charts/StackedBar.tsx`.
- [ ] T029 [P] Vitest unit tests for SectionCard (4 state branches) and each chart wrapper (empty + non-empty render, ariaLabel set).

---

## Phase 5: Frontend — section components (parallel)

- [ ] T030 [P] [US1] `KpiStrip.tsx`: fetches `kpi/`, renders 5 cards (catalog, CVs, verifier, extractor, auth state + model). Color-codes freshness via `KpiSnapshot.*_last_run.freshness`. Test: snapshot tests covering each color state.
- [ ] T031 [P] [US1] `AuthStateBanner.tsx`: read auth_state from `KpiSnapshot` via shared context OR re-fetch. Banner is dismissible per session. Test: shows when `has_li_at=false`, hides when true, hides after dismiss.
- [ ] T032 [P] [US2] `CatalogComposition.tsx`: 4 sub-cards (platform donut, lifecycle donut, role bar, seniority bar). Test: renders all 4 with non-empty data; empty payload renders 4 empty placeholders.
- [ ] T033 [P] [US2] `FreshnessActivity.tsx`: AreaSeries (jobs added 30d) + StackedBar (verifier outcomes 14d). Test: tooltip shows exact counts.
- [ ] T034 [P] [US3] `VerifierExtractorOps.tsx`: 2 coverage cards + recent-runs table. Test: relative-time formatting; table sorts newest-first.
- [ ] T035 [P] `LabelingProgress.tsx`: thin wrapper of the existing labeling stats UI; reuses `LabelingStats` type. Test: matches existing dashboard's visual output.
- [ ] T036 [P] `ModelStatus.tsx`: checkpoint name + 3 metric cards (AUC-ROC, NDCG@5, trained_at). Test: "no model" empty state when payload is all-null.

---

## Phase 6: Page composition + refresh

- [ ] T037 Replace `admin/src/pages/admin/dashboard.tsx` content with the composition from `contracts/dashboard_ui.md`. Header has title + refresh button.
- [ ] T038 Implement the global refresh button: page exposes `useState<number>` increment that's passed as a prop dependency to every section so they re-fetch.
- [ ] T039 Verify mobile responsive layout: 768px viewport stacks all cards to single column; 1280px shows the two-column grid as designed.
- [ ] T040 Keyboard a11y pass: tab order matches visual order; section retry buttons reachable; chart tooltips reachable via Recharts' built-in keyboard layer (`accessibilityLayer={true}`).

---

## Phase 7: Polish

- [ ] T041 Run frontend coverage: `npm run test -- --coverage`. Must reach ≥75% on the new files. Add tests to close uncovered branches.
- [ ] T042 [P] Update `roadmap/commands.md` with the new dashboard endpoints and how to seed data for local testing.
- [ ] T043 [P] Visual smoke against a non-empty DB (after a real verifier run): all 6 sections populated, refresh button updates them, no console errors.
- [ ] T044 Bundle size check: `npm run build` and confirm the dashboard chunk delta is within +100 kB gzipped over the baseline.
- [ ] T045 Document the new endpoints in CLAUDE.md SPECKIT block reference.
- [ ] T046 Phased commits (1 per phase + 1 final docs commit). Each commit body references the task IDs covered.

---

## Dependency graph

```text
Phase 1 (setup)          T001..T004
        │
        ▼
Phase 2 (VerifierRunLog) T005 → T006 → T007/T008 [parallel] → T009
        │
        ▼  (DB schema + write path ready)
        │
Phase 3 (backend)        T010..T013 (scaffold)
                                │
                                ▼
                         T014..T019 (services + tests, parallel)
                                │
                                ▼
                         T020 → T021 → T022
        │
        ▼
Phase 4 (FE scaffolding) T023..T029 (parallel)
        │
        ▼
Phase 5 (FE sections)    T030..T036 (parallel)
        │
        ▼
Phase 6 (page)           T037 → T038 → T039 → T040
        │
        ▼
Phase 7 (polish)         T041 → T042/T043 → T044 → T045 → T046
```

## Effort estimate

| Phase | Hours |
|-------|-------|
| 1 Setup | 0.5 |
| 2 VerifierRunLog | 1.5 |
| 3 Backend (6 services + tests) | 4.0 |
| 4 FE scaffold + charts | 2.5 |
| 5 FE sections (6 components) | 4.0 |
| 6 Page composition + a11y | 1.5 |
| 7 Polish | 1.5 |
| **Total** | **~15.5h** |

Two days of focused work. Bigger than feature 002 because of the frontend surface (6 components × 4 states each).
