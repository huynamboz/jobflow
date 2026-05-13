# Contract: Dashboard REST API

**Base path**: `/api/admin-dashboard/`

**Auth**: Same as the rest of the admin API (DRF `IsAuthenticated`). 401 if unauthenticated.

**Response envelope**: `{"success": true, "data": <payload>}` on 2xx; `{"success": false, "error": {...}}` on 4xx/5xx. Mirrors the existing `/api/matching/*` convention.

**Content type**: `application/json`.

**Cache**: `Cache-Control: no-store`. Live data only.

---

## Endpoints

### `GET /api/admin-dashboard/kpi/`

Returns `KpiSnapshot` (see `data-model.md`). Always 200 even on partial-data DBs (zero-valued fields).

Failure modes:
- 503 if the DB connection is down (no fallback to disk).
- Never raises on missing files (auth_state probe gracefully returns `file_exists: false`).

### `GET /api/admin-dashboard/catalog/`

Returns `CatalogComposition`. Response time SLO ≤500 ms p95.

Pagination: not applicable — each `by_*` array is at most ~20 distinct categories. If a future role taxonomy explodes, this contract gets a `top_n` query param.

### `GET /api/admin-dashboard/freshness/`

Returns `FreshnessActivity`.

Query params (all optional):
- `days_added`: int, default 30, max 90. Window for `jobs_added_per_day`.
- `days_outcomes`: int, default 14, max 60. Window for `verifier_outcomes_per_day`.

### `GET /api/admin-dashboard/ops/`

Returns `OpsHealth`.

Query params:
- `recent_runs_limit`: int, default 20, max 100.

### `GET /api/admin-dashboard/labeling/`

Returns `LabelingSnapshot`. Mirrors the existing `/api/labeling/stats/` payload exactly; this endpoint is provided so the dashboard can call a single root path and so the future migration of labeling stats into the dashboard app is invisible to the frontend.

### `GET /api/admin-dashboard/model/`

Returns `ModelSnapshot`. Reads from the active checkpoint's metadata file (`checkpoints/<name>/meta.json` already produced at training time). If no checkpoint is loaded, returns all-null fields with `success: true` (zero state, not an error).

---

## Error response shape

```json
{
  "success": false,
  "error": {
    "code": "DB_UNAVAILABLE",
    "message": "Cannot reach Postgres",
    "status": 503
  }
}
```

Codes used: `DB_UNAVAILABLE` (503), `UNAUTHENTICATED` (401), `INTERNAL` (500). The 6 endpoints don't take request bodies, so `INVALID_INPUT` is not needed unless a query param is malformed (then 400 with `INVALID_QUERY_PARAM`).

---

## Idempotency, retries, ordering

All endpoints are pure reads. Idempotent by definition. Frontend may retry on 503/500 with backoff. No ordering between endpoints — frontend fetches them in parallel and renders each section when its data lands.

---

## Backwards compatibility

This is a new path. No existing client uses `/api/admin-dashboard/*`. The current `/api/labeling/stats/` endpoint remains and is unaffected; the new `/admin-dashboard/labeling/` proxies the same query so the dashboard can have one root.
