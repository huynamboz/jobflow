# Implementation Plan: Admin Dashboard v2

**Branch**: `003-admin-dashboard-v2` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-admin-dashboard-v2/spec.md`

## Summary

Replace the current labeling-only dashboard with a 6-section operator-and-stakeholder home page:

1. **Top banner / KPI strip** — total jobs, last verifier run, last extractor run, auth state, model status.
2. **Catalog composition** — donuts for platform + lifecycle; bars for role_category + seniority.
3. **Freshness & activity** — area chart of jobs added per day (30d); stacked bars of verifier outcomes per day (14d).
4. **Verifier / Extractor ops** — coverage cards (% with date_posted, % verified ≤30d) + recent runs table.
5. **Labeling** — keep current labeling-stats UI as a sub-section, less prominent.
6. **Model** — checkpoint name + AUC-ROC / NDCG@5 / training timestamp.

Each section is independently fetched from its own Django endpoint under a new `apps/admin_dashboard/` app so a single section's failure doesn't break the page. The frontend uses Recharts for visualisation and keeps HeroUI `Card` for layout.

Add a small `VerifierRunLog` model + migration so trend charts have a stable data source instead of parsing stdout.

## Technical Context

**Language/Version**: Python 3.11 (backend); TypeScript 5.x + React 18 (frontend).

**Primary Dependencies**:
- Backend: Django 5.x + DRF (existing); no new Python deps.
- Frontend: existing — `@heroui/*`, axios, react-router; new — `recharts` (~50 kB gzipped).

**Storage**: PostgreSQL via Django ORM. One new table (`verifier_run_logs`). No changes to existing tables.

**Testing**: `pytest backend/tests_ml/test_dashboard_endpoints.py` for the API; Vitest for the React components (project already has Vitest config — confirm during implementation).

**Target Platform**: Modern browsers (Chrome / Firefox / Safari / Edge — latest two versions). 1280×800 minimum viewport for charts; cards collapse to single column below 768 px.

**Project Type**: Full-stack — backend API endpoints + frontend admin page.

**Performance Goals**:
- Each backend endpoint: ≤500 ms p95 on ≤50k jobs (SC-002).
- First paint: ≤2.0 s p95 (SC-001).
- Total page load: ≤4 s p95 (SC-003).
- Chart re-render on tab focus: ≤200 ms (Recharts native).

**Constraints**:
- No caching layer (live DB query) — every endpoint must therefore use indexed GROUP BY queries, not Python aggregation.
- No new infrastructure (no Celery, no Redis).
- Bundle size budget: dashboard route ≤+100 kB gzipped over baseline.
- All timestamps shown in browser-local time; values transit as ISO-8601 UTC.

**Scale/Scope**: ~7,134 LinkedIn jobs today, expected ≤50k within 6 months. ~tens of labeling pairs per day. Single-digit concurrent admin users.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project constitution remains a placeholder. No gates apply. Re-check is a no-op if a constitution is later filled in.

## Project Structure

### Documentation (this feature)

```text
specs/003-admin-dashboard-v2/
├── plan.md                       # This file
├── spec.md                       # Already written
├── research.md                   # Phase 0 — design decisions
├── data-model.md                 # Phase 1 — VerifierRunLog model + section payload shapes
├── quickstart.md                 # Phase 1 — how to add a new dashboard section
├── contracts/
│   ├── dashboard_api.md          # REST endpoint contracts
│   └── dashboard_ui.md           # Component contract (props, states, accessibility)
├── checklists/
│   └── requirements.md           # Already written
└── tasks.md                      # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── apps/
│   ├── admin_dashboard/                                NEW Django app
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── urls.py                                     # 6 endpoint paths
│   │   ├── views.py                                    # 6 APIView classes
│   │   ├── services.py                                 # query helpers (testable without HTTP)
│   │   └── serializers.py                              # response shapes (DRF Serializers)
│   ├── jobs/
│   │   ├── models.py                                   # +VerifierRunLog (existing file, edit)
│   │   └── migrations/00xx_verifier_run_log.py         # NEW migration
│   └── jobs/management/commands/
│       ├── verify_job_status.py                        # EDIT — write a VerifierRunLog row at end
│       └── extract_job_dates.py                        # EDIT — same
├── config/settings.py                                  # EDIT — register apps.admin_dashboard
└── tests_ml/
    └── test_dashboard_endpoints.py                     # NEW — happy/empty/edge cases per endpoint

admin/
├── src/
│   ├── pages/admin/
│   │   └── dashboard.tsx                               # REPLACE with v2 composition
│   ├── components/dashboard/                           # NEW — reusable section components
│   │   ├── KpiStrip.tsx
│   │   ├── CatalogComposition.tsx
│   │   ├── FreshnessActivity.tsx
│   │   ├── VerifierExtractorOps.tsx
│   │   ├── LabelingProgress.tsx
│   │   ├── ModelStatus.tsx
│   │   ├── SectionCard.tsx                             # shared shell w/ loading + error states
│   │   └── charts/                                     # tiny wrappers over Recharts
│   │       ├── Donut.tsx
│   │       ├── BarH.tsx
│   │       ├── AreaSeries.tsx
│   │       └── StackedBar.tsx
│   ├── services/
│   │   └── dashboard.service.ts                        # NEW — 6 fetchers
│   ├── types/
│   │   └── dashboard.types.ts                          # NEW — payload TS types
│   └── components/__tests__/dashboard/*.test.tsx       # NEW — Vitest unit tests
└── package.json                                        # EDIT — add `recharts`
```

**Structure Decision**: A new Django app `apps/admin_dashboard/` owns the dashboard endpoints. This keeps the dashboard query logic out of the matching/jobs apps (which serve user-facing CV-to-job matching) and makes it obvious where to add new sections later. On the frontend, each dashboard section is its own component that fetches its own data — composition over inheritance, simple to add/remove sections.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New `VerifierRunLog` model + migration instead of parsing JSON-report logs | The trend charts (verifier outcomes per day, recent runs table) need stable structured data. Parsing rotating log files in a Django view is brittle and slow, and breaks the SC-002 500ms budget. | A logs-on-disk approach would couple the dashboard to filesystem layout, log rotation policy, and parsing edge cases for every new section. A single small DB table is one migration, one INSERT per run, indexed by date. |
| 6 separate endpoints rather than one aggregated `/dashboard/all/` | Spec FR-013 explicitly requires section-independent failure isolation. With one endpoint, one slow query (e.g., a missing index on `Job.date_posted`) tanks the whole page. With six, only that section spins. | An aggregated endpoint is simpler to call once from the frontend but causes a thundering-herd problem in failure modes and prevents progressive rendering. Six small endpoints render the first ones quickly while the slow one is still loading. |

(No other deviations.)
