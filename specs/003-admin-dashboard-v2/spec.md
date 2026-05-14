# Feature Specification: Admin Dashboard v2 — Cards + Charts

**Feature Branch**: `003-admin-dashboard-v2`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "Admin dashboard with summary cards and charts for system health"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator sees system health in one glance (Priority: P1)

An operator opening the admin app needs to know within a few seconds whether the matching pipeline is healthy: how many active jobs are in the catalog, how recently the verifier ran, whether the LinkedIn auth state is still valid, and whether the date-extraction backfill is making progress. Today the dashboard only shows labeling stats — the operator has to SSH and run scripts to learn anything about jobs or the verifier. The new dashboard surfaces those answers as KPI cards at the top of the page, with red/amber/green status indicators on items that need attention.

**Why this priority**: This is the page the operator opens daily; if it can't answer the daily-ops questions, they keep relying on ad-hoc terminal commands. Every other section serves stakeholders, not the operator.

**Independent Test**: With a clean DB, the dashboard loads and shows zero-state messaging for every health card. After inserting a few jobs and running the verifier once, the same cards now show non-zero counts and a "verifier ran X minutes ago" indicator. The page must render in under 2 seconds end-to-end.

**Acceptance Scenarios**:

1. **Given** the DB has 5,000 jobs of which 4,800 are `active`, 100 are `expired`, 100 are `unverified`, **When** the operator loads the dashboard, **Then** the "Catalog" card shows total 5,000, breakdown 4,800/100/100, color-coded.
2. **Given** the verifier last ran 18 hours ago, **When** the operator loads the dashboard, **Then** the "Last verifier run" card shows the relative time ("18h ago") and is green (within 24h SLA).
3. **Given** the verifier last ran 50 hours ago, **When** the operator loads the dashboard, **Then** the same card is amber and shows a "running stale" label.
4. **Given** the LinkedIn auth state file is missing or lacks `li_at`, **When** the operator loads the dashboard, **Then** a red banner at the top reads "Auth state invalid — run linkedin_auth.py" with a link to `roadmap/commands.md`.

---

### User Story 2 — Stakeholder sees catalog composition + freshness trends (Priority: P2)

A stakeholder (PM, advisor, hiring manager) browsing the admin app wants to understand the catalog at a glance: which platforms contribute most jobs, which role categories dominate, how fresh the data is (by `date_posted`), and how the inventory is changing week over week. They don't run scripts — they want visualizations. Today the only place to see this is the GNN training notebook outputs.

**Why this priority**: Lower priority than operator-health because most days nobody needs it, but on the days they do (planning, demo, retros), the alternative is a screenshot from a Jupyter notebook. The dashboard becomes the single source of truth.

**Independent Test**: With a non-trivial catalog (≥1,000 jobs across 2+ platforms), the dashboard renders four composition charts (platform, lifecycle, role, seniority) and one freshness time-series (jobs added per day, last 30 days). Tooltips show exact counts on hover. The charts must work without horizontal scrolling on a 1280×800 viewport.

**Acceptance Scenarios**:

1. **Given** jobs split LinkedIn 7,000 / Indeed 100 / RemoteOK 50, **When** the stakeholder loads the dashboard, **Then** the platform donut chart shows three slices proportional to those counts, with absolute counts visible on hover.
2. **Given** jobs span the last 90 days of `date_posted` values, **When** the stakeholder hovers over the freshness histogram, **Then** the tooltip shows "Week of YYYY-MM-DD — N jobs".
3. **Given** the role-category bar chart has 12 categories, **When** the chart is rendered on a 1280-pixel-wide screen, **Then** the labels are readable (no overlap, no truncation that hides the category name).

---

### User Story 3 — Operator monitors verifier and extractor runs (Priority: P1)

The operator needs to confirm the verifier and extractor are doing useful work, not silently failing. They want a section showing: the last N runs of each command, the outcome counts per run, the coverage percentages (% of LinkedIn jobs with `date_posted`, % verified in last 30 days), and a small chart of outcomes per day for the last two weeks. This complements the live per-URL logs the commands print — those are for watching a single run; this section is for trend awareness.

**Why this priority**: After User Story 1, this is the next thing an operator checks. Without it, drift goes unnoticed for weeks (the verifier "looks fine" but actually has produced 70% UNKNOWN for the last 3 days).

**Independent Test**: Run the verifier 5 times across 2 days with mixed outcomes. The "Recent verifier runs" table shows 5 rows with timestamp, batch size, and per-outcome counts. The "Verifier outcomes (last 14 days)" stacked bar chart aggregates those runs by date. Coverage card recomputes accurately after each run.

**Acceptance Scenarios**:

1. **Given** the verifier produced (active=10, expired=5, unknown=2) yesterday and (active=12, expired=3, unknown=1) today, **When** the operator loads the dashboard, **Then** the stacked-bar chart shows two day-columns with those stack heights.
2. **Given** 4,500 of 5,000 LinkedIn jobs have `date_posted`, **When** the operator loads the dashboard, **Then** the "Date coverage" card reads "90%" with a progress bar.
3. **Given** the verifier has not run in 72 hours, **When** the operator loads the dashboard, **Then** the freshness column for the verifier card turns red and shows the staleness explicitly.

---

### Edge Cases

- **Empty DB (fresh install)**: every card shows a zero or "no data yet" state. Charts render an empty grid with a friendly placeholder, not blank space.
- **Backend endpoint failure**: a single section's fetch error must not crash the whole page; the failing card shows an inline error + retry button.
- **Very long category names** (e.g., `data engineering / mlops`): bar charts truncate with ellipsis + show full text on hover.
- **Auth state missing**: the red banner is dismissible per session but reappears on every page reload until fixed.
- **Concurrent operator runs**: dashboard is read-only; multiple operators can view simultaneously without lock contention.
- **Time-zone display**: all timestamps shown in the operator's local time (browser timezone), but the underlying values are UTC.
- **Mobile / narrow viewport**: cards stack to single column below 768px; charts switch to scrollable horizontal form factor.
- **Permission**: the dashboard requires an authenticated admin session; unauthenticated visits redirect to login (same as the rest of the admin app).

## Requirements *(mandatory)*

### Functional Requirements

#### Data — Catalog
- **FR-001**: The dashboard MUST show total job count broken down by `lifecycle` (active/stale/expired/unverified).
- **FR-002**: The dashboard MUST show total job count broken down by `platform.name` (LinkedIn / Indeed / RemoteOK / …).
- **FR-003**: The dashboard MUST show total job count broken down by `role_category` (backend / frontend / mobile / …).
- **FR-004**: The dashboard MUST show total job count broken down by `seniority` (intern / junior / mid / senior / lead / manager).
- **FR-005**: The dashboard MUST show the fraction of LinkedIn jobs with `date_posted IS NOT NULL` and the fraction with `last_verified_at` within the last 30 days.

#### Data — CVs and labeling
- **FR-006**: The dashboard MUST show total CV count and CV uploads in the last 7 days.
- **FR-007**: The dashboard MUST retain the labeling stats currently displayed (total / labeled / skipped / pending; by-reason; by-split) in a sub-section.

#### Data — Time series
- **FR-008**: The dashboard MUST show jobs added per day over the last 30 days.
- **FR-009**: The dashboard MUST show verifier outcomes per day (active / expired / unknown / error / session_expired) over the last 14 days.

#### Data — Ops health
- **FR-010**: The dashboard MUST show the wall-clock timestamp of the most recent verifier run, the most recent extractor run, and a coloured indicator (green ≤24h, amber 24-72h, red >72h or never).
- **FR-011**: The dashboard MUST show whether the LinkedIn auth state file exists AND contains `li_at`; if not, surface a dismissible banner with a remediation hint.
- **FR-012**: The dashboard MUST show the current GNN checkpoint name and its Test AUC-ROC / NDCG@5 metrics if available; if no checkpoint is loaded, the section reads "no model active".

#### Behaviour
- **FR-013**: Each section MUST be served by an independent backend endpoint so a failure in one does not block the rest of the page.
- **FR-014**: Each chart MUST show absolute counts on hover (tooltip) and MUST render a clearly-marked empty state when its underlying query returns zero rows.
- **FR-015**: The page MUST have a manual refresh button that re-fetches every section.
- **FR-016**: Every timestamp displayed in the UI MUST be in the operator's browser-local time zone, with the underlying ISO-8601 UTC value available on hover.

### Key Entities

- **DashboardSnapshot**: an in-memory aggregation built per request from queries over the existing `Job`, `CV`, `LabelingPair`, `Checkpoint`, and verifier run-log tables. Not persisted.
- **Verifier run log** (existing or to be added): a record of one batch run — timestamp, command (`verify_job_status` / `extract_job_dates`), platform, total_examined, outcomes by category. Powers the recent-runs table and the outcomes-per-day chart.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: First paint of the dashboard occurs in ≤2.0 seconds (95th percentile) on a workstation against a DB with ≤50,000 jobs.
- **SC-002**: Each backend endpoint serving the dashboard responds in ≤500 ms (95th percentile) on the same DB scale.
- **SC-003**: Total page load (all sections fetched + rendered) ≤4 seconds (95th percentile).
- **SC-004**: The dashboard reflects DB writes within at most one manual refresh round-trip (no stale cache layer).
- **SC-005**: All required interactive elements (buttons, chart tooltips, dismiss banner) are reachable via keyboard alone.
- **SC-006**: Frontend unit test coverage for the new dashboard components and the data hooks is ≥75%.

## Assumptions

- The admin app's authentication and routing are unchanged; the dashboard remains at the existing `/admin/dashboard` route.
- A verifier run log table either exists or is acceptable to add as part of this feature (one small Django model + migration). Operators have stated they want trend visibility; ad-hoc parsing of `tail` logs is not a substitute.
- Browser support: latest two stable versions of Chrome, Firefox, Safari, Edge. No IE.
- Charts rendered with Recharts (decided in spec-prep clarifications). No alternative library is in scope.
- Data is queried live from PostgreSQL on every request (decided in spec-prep clarifications). Caching is out of scope for v1.
- The admin app uses HeroUI for layout primitives; new cards continue using `Card` / `CardBody` from `@heroui/card` for visual consistency.
- Labeling metrics currently shown on the dashboard remain; they are moved into a sub-section but their data source (LabelingService.getStats) is unchanged.
- Internationalisation is out of scope. Strings are English; numbers are formatted using `Intl.NumberFormat` with the browser locale.
