# Phase 1 — Data Model: LinkedIn Job Verifier

**Date**: 2026-05-13

This document specifies the data shape changes required by the feature: the new columns on `Job`, their semantics, indexes, and the state-transition rules.

---

## Entity: `Job` (existing — modified)

Existing fields touched/added below; all other fields untouched.

| Column | Type | Default | Index | Notes |
|--------|------|---------|-------|-------|
| `lifecycle` | `CharField(max_length=20)` | `"active"` | yes (b-tree) | One of `active`, `stale`, `expired`, `unverified`. |
| `last_seen_at` | `DateTimeField` | `auto_now_add` | yes | Updated by the crawler each time the job is re-encountered in a feed. |
| `last_verified_at` | `DateTimeField(null=True, blank=True)` | `null` | no | Set when a verifier returns `active`, `expired`, or `session_expired` (in the last case the timestamp records the attempt, lifecycle stays). |
| `verification_attempts` | `IntegerField` | `0` | no | Incremented on `error` or `unknown`; reset to 0 on `active`/`expired`. |
| `verification_backoff_until` | `DateTimeField(null=True, blank=True)` | `null` | yes | When set, the verifier skips this row until `now >= verification_backoff_until`. |
| `is_active` | `BooleanField` | (existing) | (existing) | **Kept** for transition window. Becomes a computed shim returning `lifecycle in {'active','stale','unverified'}`. Plan to remove in v2 once admin UI / consumers migrate. |

**Choices** for `lifecycle`:
- `active` — currently accepting applications (last verifier outcome was `active`, or freshly crawled job with `date_posted` set).
- `stale` — `date_posted` older than 14 days, eligible for re-verification but still matchable.
- `expired` — verifier confirmed closed/removed.
- `unverified` — created without a `date_posted` (or with one of unknown provenance); still matchable, lower confidence.

**Migration**: `00xx_job_lifecycle.py`. Backfill on apply:
- `lifecycle = 'active'` for all existing rows.
- `last_seen_at = created_at` (existing column) for all existing rows.
- `last_verified_at = NULL`, `verification_attempts = 0`, `verification_backoff_until = NULL`.

Migration is forward-safe: no data is destroyed, `is_active` remains.

---

## Entity: `VerifyResult` (new — in-memory, not persisted)

A frozen dataclass produced by every verifier per URL.

| Field | Type | Notes |
|-------|------|-------|
| `status` | `JobStatus` enum | One of `ACTIVE`, `EXPIRED`, `SESSION_EXPIRED`, `UNKNOWN`, `ERROR`. |
| `reason` | `str` | Free-text reason (selector matched, exception name, etc.). Defaults to `""`. |
| `final_url` | `str \| None` | The page's URL after redirects, if known. |
| `verified_at` | `datetime` | When the check completed (UTC). Default: `datetime.utcnow()`. |

`VerifyResult` is the only contract between verifier providers and `StatusCheckService`. It is not persisted; the service converts it to DB writes inside the repository.

---

## Entity: `StatusCheckReport` (new — in-memory, run output)

Returned by `StatusCheckService.check_batch()` and printed by the management command.

| Field | Type | Notes |
|-------|------|-------|
| `started_at` | `datetime` | Wall-clock start. |
| `finished_at` | `datetime` | Wall-clock end. |
| `platform` | `str` | Platform filter applied (`"linkedin"` in v1; `"all"` later). |
| `batch_size_requested` | `int` | The `--batch` argument. |
| `total_examined` | `int` | Jobs picked from the candidate query (≤ batch). |
| `counts_by_outcome` | `dict[JobStatus, int]` | Histogram across the batch. |
| `skipped_unsupported_url` | `int` | URLs no verifier supports. |
| `session_expired_count` | `int` | Subset of `counts_by_outcome[SESSION_EXPIRED]`; surfaces as ops alert. |
| `dry_run` | `bool` | True if no DB writes occurred. |

---

## State transitions (lifecycle)

```text
                   ┌──── age >= 14d ────────────────┐
                   ▼                                │
                 stale ───── verify → ACTIVE ──────┘
                   │                                ▲
                   │                                │
        verify → EXPIRED                 verify → ACTIVE
                   │                                │
                   ▼                                │
                expired ←──────────── (no return) ──┘
                   │
       (employer re-opens; verifier returns ACTIVE)
                   │
                   ▼
                 active

  active ───────── verify → ACTIVE ─────────► active (no transition)
  active ───────── verify → EXPIRED ────────► expired
  active ───────── verify → UNKNOWN ────────► active (attempts++, backoff)
  active ───────── verify → ERROR ──────────► active (attempts++, backoff)
  active ───────── verify → SESSION_EXPIRED ─► active (no field change, alert only)

  unverified (date_posted IS NULL)
      └─── treated as active for matching; first verify result follows the active rules above.
```

**Aging rule (Decision 9 in research.md)**: at the start of every batch run, the service applies:
```sql
UPDATE jobs
SET    lifecycle = 'stale'
WHERE  lifecycle = 'active'
  AND  date_posted IS NOT NULL
  AND  date_posted < (NOW() - INTERVAL '14 days');
```
This is the single source of `stale` transitions. No other code path writes `stale`.

---

## Repository write semantics (per `VerifyResult`)

| Outcome | Lifecycle write | `last_verified_at` | `verification_attempts` | `verification_backoff_until` |
|---------|----------------|--------------------|-------------------------|------------------------------|
| `ACTIVE` | → `active` | `= now()` | `= 0` | `= NULL` |
| `EXPIRED` | → `expired` | `= now()` | `= 0` | `= NULL` |
| `UNKNOWN` | unchanged | unchanged | `+= 1` | `= now + min(2^attempts × 1h, 7d)` |
| `ERROR` | unchanged | unchanged | `+= 1` | `= now + min(2^attempts × 1h, 7d)` |
| `SESSION_EXPIRED` | unchanged | unchanged | unchanged | unchanged (operator alert only) |

`now()` is read once at the start of `apply_result` to keep batch writes coherent.

`SESSION_EXPIRED` does not touch the row at all so a subsequent successful run treats the job exactly as it was before the session lapsed.

---

## Candidate selection query (executed by `StatusCheckService`)

```sql
SELECT id, source_url, platform_id
FROM   jobs
WHERE  platform_id = :platform_id   -- LinkedIn in v1
  AND  lifecycle IN ('stale', 'active')
  AND  (verification_backoff_until IS NULL OR verification_backoff_until <= NOW())
ORDER  BY
  CASE WHEN lifecycle = 'stale' THEN 0 ELSE 1 END,   -- stale first
  COALESCE(last_verified_at, '1970-01-01') ASC        -- oldest verified first
LIMIT  :batch;
```

Indexes used: `(platform_id)` (existing FK index), `(lifecycle)` (new), `(verification_backoff_until)` (new). Composite `(platform_id, lifecycle)` index added by migration for the hot path.

---

## Matching API filter (executed per CV-to-job request)

After the engine returns `top_k_job_ids: list[int]`, the matching service applies:

```python
allowed_ids = set(
    Job.objects
        .filter(id__in=top_k_job_ids, lifecycle__in=['active', 'stale', 'unverified'])
        .values_list('id', flat=True)
)
result = [j for j in engine_result if j.job_id in allowed_ids]
```

This preserves the engine's ranking order and drops `expired` (and any future tombstone state).

---

## Out of scope (this feature)

- A `JobLifecycleEvent` audit table (every transition logged) — useful for debugging but not required by acceptance criteria.
- Soft-delete of long-expired jobs (e.g., after 180 days) — separate concern, doesn't block v1.
- Bake lifecycle into the GNN checkpoint at build time — deferred to the next retrain.
