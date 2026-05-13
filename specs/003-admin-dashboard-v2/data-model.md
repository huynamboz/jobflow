# Phase 1 — Data Model: Admin Dashboard v2

**Date**: 2026-05-13

The dashboard introduces **one** new persistent table; the rest is computed from existing models on every request.

---

## New entity: `VerifierRunLog`

Powers the "recent runs" table and the "outcomes per day" stacked-bar chart.

| Column | Type | Index | Notes |
|--------|------|-------|-------|
| `id` | `BigAutoField` | PK | Default Django. |
| `command` | `CharField(32)` | yes | `verify_job_status` or `extract_job_dates`. |
| `platform` | `CharField(32)` | yes | `linkedin` in v1; future-proofed. |
| `started_at` | `DateTimeField` | yes | Wall-clock start, UTC. |
| `finished_at` | `DateTimeField` | no | Wall-clock end, UTC. |
| `batch_size_requested` | `IntegerField` | no | The `--batch` arg the operator passed. |
| `total_examined` | `IntegerField` | no | URLs actually walked. |
| `skipped_unsupported_url` | `IntegerField` | no | URLs no verifier supported. Default 0. |
| `counts_by_outcome` | `JSONField` | no | For verifier: `{"active": N, "expired": N, "session_expired": N, "unknown": N, "error": N}`. For extractor: `{"populated": N, "expired_marked": N, "none": N, "error": N, "session_expired": N}`. |
| `session_expired_count` | `IntegerField` | no | Convenience for filter queries (avoids `counts_by_outcome->>'session_expired'` casts). |
| `error_count` | `IntegerField` | no | Same convenience as above. |
| `dry_run` | `BooleanField` | no | True iff `--dry-run` was set. Defaults False. |

**Composite index**: `(command, started_at DESC)` — supports the "recent runs of command X" query in one indexed scan.

**Migration**: forward-only, additive. No existing-row backfill needed (table starts empty).

**Write path**: At the end of `manage.py verify_job_status` and `manage.py extract_job_dates`, after the report is printed, the command inserts one `VerifierRunLog` row. If insertion fails, the failure is logged but does NOT change the command's exit code — observability MUST NOT break ops.

---

## Section payload shapes (in-memory only, not persisted)

All payloads are returned as JSON from the corresponding endpoint. Schemas below are the contract the frontend's `dashboard.types.ts` mirrors.

### `KpiSnapshot` — `/api/admin-dashboard/kpi/`

```json
{
  "jobs_total": 7134,
  "jobs_by_lifecycle": {
    "active": 7115,
    "stale": 0,
    "expired": 19,
    "unverified": 0
  },
  "cv_total": 1284,
  "cv_uploads_last_7d": 47,
  "verifier_last_run": {
    "started_at": "2026-05-13T08:52:05Z",
    "command": "verify_job_status",
    "freshness": "fresh"      // "fresh" | "stale" | "very_stale" | "never"
  },
  "extractor_last_run": {
    "started_at": "2026-05-13T09:09:29Z",
    "command": "extract_job_dates",
    "freshness": "fresh"
  },
  "auth_state": {
    "file_exists": true,
    "has_li_at": true
  },
  "model": {
    "checkpoint_name": "gnn_v2",
    "test_auc_roc": 0.876,
    "ndcg_at_5": 1.000,
    "trained_at": "2026-04-24T00:00:00Z"
  }
}
```

`freshness` thresholds: `fresh` ≤24 h, `stale` ≤72 h, `very_stale` >72 h, `never` for missing row.

### `CatalogComposition` — `/api/admin-dashboard/catalog/`

```json
{
  "by_platform": [
    {"key": "LinkedIn", "count": 7134},
    {"key": "Indeed", "count": 1}
  ],
  "by_lifecycle": [
    {"key": "active", "count": 7115},
    {"key": "expired", "count": 19}
  ],
  "by_role_category": [
    {"key": "backend", "count": 373},
    {"key": "frontend", "count": 746}
  ],
  "by_seniority": [
    {"key": 2, "label": "Mid", "count": 3200}
  ]
}
```

Each array is ordered `count DESC`. Empty arrays are valid (no jobs in catalog).

### `FreshnessActivity` — `/api/admin-dashboard/freshness/`

```json
{
  "jobs_added_per_day": [
    {"day": "2026-04-14", "count": 12},
    {"day": "2026-04-15", "count": 8}
  ],
  "verifier_outcomes_per_day": [
    {
      "day": "2026-05-12",
      "active": 4, "expired": 13, "unknown": 3, "error": 0, "session_expired": 0
    }
  ]
}
```

Time window: jobs_added = last 30 days from now (UTC midnight); verifier_outcomes = last 14 days. Days with zero values are included as zero rows (frontend doesn't need to fill gaps).

### `OpsHealth` — `/api/admin-dashboard/ops/`

```json
{
  "coverage": {
    "linkedin_with_date_posted_pct": 0.06,
    "linkedin_verified_last_30d_pct": 0.001
  },
  "recent_runs": [
    {
      "id": 41,
      "command": "verify_job_status",
      "started_at": "2026-05-13T08:52:05Z",
      "finished_at": "2026-05-13T08:52:31Z",
      "wall_clock_s": 25.9,
      "total_examined": 5,
      "counts_by_outcome": {"active": 1, "expired": 3, "session_expired": 0, "unknown": 0, "error": 1},
      "dry_run": false
    }
  ]
}
```

`recent_runs` is limited to the most recent 20 across both commands, newest first.

### `LabelingSnapshot` — `/api/admin-dashboard/labeling/`

Mirrors the existing `LabelingStats` shape from `apps/labeling/services` so the existing frontend type can be reused without changes:

```json
{
  "total_pairs": 11611,
  "labeled": 11500,
  "skipped": 50,
  "pending": 61,
  "by_reason": {"diverse_skills": {"labeled": 1234, "total": 1300}},
  "by_split": {"train": {"labeled": 9000, "total": 9000}}
}
```

### `ModelSnapshot` — `/api/admin-dashboard/model/`

**Source**: the *active* checkpoint is whichever one is referenced by
`settings.ML_CHECKPOINT_DIR`. The endpoint reads
`<ML_CHECKPOINT_DIR>/meta.json` (already produced at training time by
the GNN trainer). If the file is missing or unreadable, all fields are
null and the section renders "no model active".

```json
{
  "checkpoint_name": "gnn_v2",
  "trained_at": "2026-04-24T00:00:00Z",
  "metrics": {
    "test_auc_roc": 0.876,
    "ndcg_at_5": 1.000,
    "mrr": 1.000,
    "precision_at_5": 1.000
  },
  "calibration": {"a": 1.016, "b": -1.078}
}
```

If no checkpoint is currently loaded, all fields are null; the frontend renders "no model active".

---

## Query patterns

### Total + by_lifecycle (one query)

```sql
SELECT lifecycle, COUNT(*) AS n
FROM jobs
GROUP BY lifecycle;
```

Index used: `lifecycle` (added in feature 001).

### Jobs added per day, last 30 days

```sql
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS n
FROM jobs
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day;
```

Uses default `created_at` index implicitly via WHERE.

### Verifier outcomes per day, last 14 days

```sql
SELECT
  date_trunc('day', started_at) AS day,
  SUM((counts_by_outcome ->> 'active')::int)          AS active,
  SUM((counts_by_outcome ->> 'expired')::int)         AS expired,
  SUM((counts_by_outcome ->> 'unknown')::int)         AS unknown,
  SUM((counts_by_outcome ->> 'error')::int)           AS error,
  SUM((counts_by_outcome ->> 'session_expired')::int) AS session_expired
FROM verifier_run_logs
WHERE command = 'verify_job_status'
  AND started_at >= NOW() - INTERVAL '14 days'
  AND dry_run = false
GROUP BY day
ORDER BY day;
```

Uses composite index `(command, started_at)`.

### Coverage: % LinkedIn jobs with `date_posted`

```sql
SELECT
  COUNT(*)                                                    AS total,
  COUNT(*) FILTER (WHERE date_posted IS NOT NULL)             AS with_date,
  COUNT(*) FILTER (WHERE last_verified_at >= NOW() - INTERVAL '30 days') AS recent
FROM jobs
WHERE platform_id = :linkedin_platform_id;
```

Two FILTER aggregates in one scan — no separate roundtrips.

---

## Out of scope

- Per-user dashboard preferences (saved layouts, hidden cards). v1 has one layout for everyone.
- Drilldowns from chart → list view. v1 chart click does nothing; clicks are deferred.
- Real-time push (WebSocket / SSE). Manual refresh button only.
- Cost / LLM-usage charts. Already covered by the LLM Logs page; not duplicated here.
- A "verifier health" alerting hook (e.g., POST to Slack on stale). Could be added later; v1 surfaces info, doesn't alert.
