# Phase 1 — Data Model: date_posted extraction

**Date**: 2026-05-13

This feature does **not** introduce a schema change. It writes existing columns on `Job` and tightens a non-schema invariant on the saved auth file.

---

## Existing columns written by this feature

| Column | Type | When written | Write rule |
|--------|------|--------------|-----------|
| `Job.date_posted` | `DateTimeField(null=True)` | Crawler at ingestion + backfill | Set when extractor returns a date passing guardrails; otherwise unchanged. |
| `Job.lifecycle` | `CharField` | Backfill (only on `expired-redirect`) | Set to `'expired'` only when the extractor sees the redirect-to-search signal. Verifier write semantics unchanged. |
| `Job.verification_attempts` | `IntegerField` | Backfill (on `ERROR` only) | Incremented same as the verifier — share the repository's `apply_result` method. |
| `Job.verification_backoff_until` | `DateTimeField(null=True)` | Backfill (on `ERROR` only) | Set same as verifier. |

No new columns. No migration.

---

## In-memory entities

### `DateExtractionResult` (immutable)

```python
@dataclass(frozen=True)
class DateExtractionResult:
    date: datetime | None      # tz-aware UTC; midnight when source has day precision
    source: str                 # one of: datetime-attribute, json-ld, relative-text, expired-redirect, none
```

Produced by `extract_date_posted(page)`. Not persisted. The `source` tag is informational only and is logged in batch reports.

### `BackfillReport`

```python
@dataclass
class BackfillReport:
    platform: str
    batch_size_requested: int
    total_examined: int
    populated_count: int                       # date_posted written
    expired_marked_count: int                  # lifecycle promoted to expired
    none_count: int                            # processed but no date found, not expired
    error_count: int                           # exception during extraction
    session_expired_count: int                 # mid-batch auth loss
    started_at: datetime
    finished_at: datetime
    dry_run: bool
```

Mirrors the verifier's `StatusCheckReport` shape so operators reuse mental model.

---

## Auth-state invariant

The saved auth file at `backend/auth/linkedin_state.json` is a Playwright `storage_state` blob. The invariant added by this feature:

```
∃ c ∈ state.cookies . c.name == "li_at" ∧ c.domain endswith "linkedin.com"
```

Enforced at three points:

1. **Read** — `load_state_path()` returns the path only if the invariant holds; otherwise returns None (caller treats as "no state — abort or fail-fast").
2. **Pre-batch** — every batch (verifier or extractor) calls `has_li_at(load_state(...))` before opening a browser; if False, aborts with one clear log line.
3. **Pre-write** — every `storage_state(path=...)` is replaced by "fetch state into memory → check invariant → write only if invariant holds". If invariant fails, the in-memory state is discarded and the on-disk file is left untouched.

This makes "saved state is rotted" impossible to introduce silently.

---

## Backfill candidate query

```sql
SELECT id, source_url, lifecycle, last_seen_at
FROM jobs
WHERE platform_id = :platform_id
  AND date_posted IS NULL
  AND lifecycle IN ('active', 'stale')
  AND (verification_backoff_until IS NULL OR verification_backoff_until <= now())
ORDER BY last_seen_at DESC
LIMIT :batch;
```

Indexes used: existing FK index on `platform_id`, partial index on `(lifecycle)`, and `(verification_backoff_until)` — all added by feature 001's migration. No new indexes.

Idempotency is guaranteed by the `date_posted IS NULL` filter alone — running the command twice in a row picks disjoint candidate sets.

---

## Write semantics per `DateExtractionResult`

| Result source | `date_posted` | `lifecycle` | Other fields |
|---------------|----------------|-------------|---------------|
| `datetime-attribute` | = result.date | unchanged | unchanged |
| `json-ld` | = result.date | unchanged | unchanged |
| `relative-text` | = result.date | unchanged | unchanged |
| `expired-redirect` | unchanged (NULL stays NULL) | → `expired`, `last_verified_at = now`, `verification_attempts = 0`, `verification_backoff_until = NULL` | (same as verifier's EXPIRED outcome) |
| `none` | unchanged | unchanged | `verification_attempts += 1`, `verification_backoff_until = now + min(2^attempts × 1h, 7d)` |
| `ERROR` (exception) | unchanged | unchanged | same as `none` |
| `SESSION_EXPIRED` | unchanged | unchanged | unchanged (operator alert only) |

Backfill and verifier share the repository's `apply_result(job_id, verify_result, *, now)` method for `expired-redirect`, `none`, `ERROR`, and `SESSION_EXPIRED` paths. Only the `populated` write (setting `date_posted`) is unique to the backfill.

---

## Out of scope

- A `date_posted_source` column persisting which extractor branch produced the value. Decision 4 in research keeps this in-memory only.
- A `date_posted_precision` enum (day-exact vs week-approximate). Decided against in research Decision 2 — week-level precision is implied by the source tag for callers who care.
- A schema-level CHECK constraint on the 2-year guardrail. Application-level guardrail is sufficient and easier to evolve.
