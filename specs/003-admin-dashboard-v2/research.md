# Phase 0 — Research & Decisions: Admin Dashboard v2

**Date**: 2026-05-13

---

## Decision 1 — Six independent endpoints, not one aggregator

**Decision**: `/api/admin-dashboard/<section>/` for each of six sections (`kpi`, `catalog`, `freshness`, `ops`, `labeling`, `model`).

**Rationale**:
- FR-013 demands independent failure isolation; an aggregator breaks this.
- Progressive rendering is better UX: KPI strip can land in 80 ms while the (slower) time-series section is still computing.
- Cache-busting is trivial: refresh hits all six in parallel; the slow ones don't block the fast ones.

**Alternatives**:
- *One `/dashboard/all/` endpoint*: single round-trip, simpler frontend wiring. Rejected per FR-013.
- *GraphQL*: power tool overkill for a hand-rolled admin page.

---

## Decision 2 — Live DB queries, no cache layer

**Decision**: Every request runs the query directly against PostgreSQL. No Redis, no materialized views, no in-process cache.

**Rationale**:
- DB scale (≤50k jobs) makes well-indexed GROUP BY queries trivially fast.
- Cache invalidation is its own complexity tax; we'd need to wire it through verifier/extractor/crawl pipelines.
- Operators want trust: "the page shows what's in the DB right now."

**Alternatives**:
- *5-min Redis cache*: would cut DB load if the dashboard becomes hot, but premature for current traffic.
- *Materialized views refreshed nightly*: introduces refresh scheduling and adds staleness — defeats SC-004.

---

## Decision 3 — Charts via Recharts

**Decision**: Use Recharts for all visualisations. Wrap each chart type (donut, horizontal bar, area, stacked bar) in a small adapter component so we can swap libraries later without touching section components.

**Rationale**:
- React-first declarative API, fits the rest of the codebase.
- ~50 kB gzipped — within the +100 kB bundle budget.
- Built-in accessibility for tooltips and legends.

**Alternatives**:
- *Tremor*: ships KPI cards too, but those overlap with HeroUI; mixing both would be visually inconsistent.
- *Chart.js + react-chartjs-2*: canvas, fast on huge datasets, but imperative API breaks our React idiom.
- *visx*: more flexible but requires more wiring; overkill for our chart set.

---

## Decision 4 — Add `VerifierRunLog` Django model

**Decision**: One new table:

```python
class VerifierRunLog(models.Model):
    COMMAND_VERIFY = "verify_job_status"
    COMMAND_EXTRACT = "extract_job_dates"
    command = CharField(max_length=32, db_index=True, choices=...)
    platform = CharField(max_length=32, db_index=True)
    started_at = DateTimeField(db_index=True)
    finished_at = DateTimeField()
    batch_size_requested = IntegerField()
    total_examined = IntegerField()
    counts_by_outcome = JSONField()   # {"active": 1, "expired": 3, ...} OR {"populated": 4, "none": 1, ...}
    session_expired_count = IntegerField(default=0)
    error_count = IntegerField(default=0)
    dry_run = BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]
        indexes = [Index(fields=["command", "started_at"])]
```

Both management commands write one row at end-of-run.

**Rationale**:
- Trend charts (US3) need structured data that survives log rotation.
- Recent-runs table needs a fast indexed query, not a tail-and-parse.
- One small migration, one INSERT per run — negligible cost.

**Alternatives**:
- *Parse JSON-report logs from disk*: brittle, slow, breaks SC-002. Rejected.
- *Re-derive from `Job.verification_attempts` aggregates*: lossy (no per-run granularity, no extractor's "populated" outcome). Rejected.

---

## Decision 5 — Section component shell

**Decision**: A shared `<SectionCard>` component wraps each dashboard section and handles three states: `loading`, `error` (with retry), `empty`. Section-specific components inherit this shell and only render the chart/content branch.

**Rationale**:
- Avoids 6× of identical loading/error boilerplate.
- Centralises empty-state messaging (FR-014).
- Makes accessibility (ARIA live regions for status changes) consistent.

---

## Decision 6 — Time-series bucketing

**Decision**: Backend buckets time-series data into day-level buckets aligned to UTC midnight. Frontend reformats the day strings to local-timezone labels.

**Rationale**:
- DB query `date_trunc('day', column AT TIME ZONE 'UTC')` is index-friendly and deterministic.
- Hour-level granularity is wasteful for the 14- and 30-day windows the dashboard uses.
- Operator's local-time presentation is a frontend concern; backend stays UTC.

**Alternatives**:
- *Bucket on the frontend*: forces fetching every row; SC-002 violation at 50k jobs.
- *Hour-level*: visual noise on 30-day charts; serves no decision.

---

## Decision 7 — Auth state introspection

**Decision**: The KPI endpoint reads `backend/auth/linkedin_state.json` via the existing `ml_service.verifier.auth_guard.read_state` and reports `{has_li_at: bool, file_exists: bool}`. No cookie values cross the API boundary.

**Rationale**:
- Reuses the invariant module added in feature 002 — single source of truth for "what does a valid state look like".
- Reading a small JSON once per request is cheap (≤5 ms).

**Alternatives**:
- *Check disk only*: misses the `li_at`-missing case the feature 002 bug exposed.
- *Expose cookie expires-at*: PII leak risk for no operational gain.

---

## Decision 8 — Test seam

**Decision**: All backend section logic lives in `apps/admin_dashboard/services.py` as plain functions taking optional `now: datetime` and returning DTOs. Views are thin shells. Tests call services directly, not HTTP.

**Rationale**:
- Same DI pattern as the verifier feature — service is a pure function, views just JSON-encode.
- Avoids spinning up DRF test client for every assertion.
- Frontend tests can rely on the contracts in `contracts/dashboard_api.md`, not on real backend.

---

## Open items

None. All clarifications were resolved at the spec-prep step. No NEEDS CLARIFICATION markers remain in the spec.
