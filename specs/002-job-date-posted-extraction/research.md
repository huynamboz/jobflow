# Phase 0 — Research & Decisions: LinkedIn date_posted extraction

**Date**: 2026-05-13

Decisions made before writing data-model + contracts. Each entry resolves a question that would otherwise block implementation.

---

## Decision 1 — Extraction priority order

**Decision**: For each LinkedIn job page, try sources in this order; return at the first success:

1. **JSON-LD `JobPosting.datePosted`** (most authoritative — LinkedIn embeds this for SEO).
2. **`<time datetime="...">` inside the job-detail top-card or tertiary-info container** (authenticated layout; scoped selector avoids matching "more jobs from..." cards).
3. **Relative text** ("Posted X days/weeks/months ago", "today", "yesterday", "just now"), parsed against the run-time UTC clock.
4. None — leave `date_posted = NULL`.

**Rationale**:
- JSON-LD is *the* canonical structured-data signal. When present it's day-exact and free of ambiguity. It is generated server-side for SEO and is the same regardless of auth layout, so it works for both authenticated and guest renders.
- The `<time datetime>` attribute is also exact but only renders in the authenticated layout; checked second so the JSON-LD path takes precedence when both exist (defensive — they should agree, but if they don't, JSON-LD wins).
- Relative text is the only signal available on guest layout when JSON-LD is missing (varies by LinkedIn cache state). It's approximate but better than NULL.

**Alternatives considered**:
- *Guess "today" if nothing found*: poisons the data with fake recent dates. Rejected.
- *Use crawl `created_at` as fallback*: misleading — `created_at` says when we crawled, not when the job was posted. Rejected.
- *Try relative text first*: hurts precision when JSON-LD is present. Rejected.

---

## Decision 2 — Relative text parser scope

**Decision**: Parse English relative phrases only. Patterns supported:

```
"just now"                    → today
"today"                       → today
"yesterday"                   → today - 1 day
"N minute(s) ago"             → today
"N hour(s) ago"               → today
"N day(s) ago"                → today - N days
"N week(s) ago"               → today - N*7 days
"N month(s) ago"              → today - N*30 days
"N year(s) ago"               → today - N*365 days
"posted N <unit> ago"         → same as above (strip "posted " prefix)
"reposted N <unit> ago"       → same (relative is still relative)
```

**Rationale**:
- The English LinkedIn pages our crawler targets cover all data sources currently in use; we have no Vietnamese/French LinkedIn jobs in the catalog.
- "N hours ago" / "N minutes ago" all collapse to "today" — sub-day precision isn't useful for a `date_posted` field.
- "N month/year ago" uses a fixed 30/365 multiplier — known approximation. Documented in the source-tag metadata so callers know precision is week-level at best.

**Alternatives considered**:
- *Localized parsing via `babel.dates`*: heavy dependency for a feature where every existing data source is English-locale LinkedIn. Rejected for v1; revisit if a non-English source is added.
- *Calendar-aware month math*: marginal precision gain (30 → 28-31 days), zero practical benefit for week-level use. Rejected.

---

## Decision 3 — Date guardrails

**Decision**: A candidate date is accepted only if `(today_utc - 730 days) ≤ date ≤ today_utc`. Otherwise treat as no date found.

**Rationale**:
- LinkedIn job postings older than 2 years are extremely rare; any `<time datetime="2010-...">` is almost certainly a stray element (company founding date, "since 2010" badge, etc.) accidentally matched.
- A future-dated value is the result of clock skew, content-management bugs, or LinkedIn UX glitches — never a real job posting date.
- Discarding rather than clamping makes the failure mode loud (date stays NULL → operator can investigate) instead of silently corrupting the field.

**Alternatives considered**:
- *Clamp future to today, very-old to (today - 2y)*: hides the failure. Rejected.
- *Always accept whatever the page says*: pollutes data with garbage and breaks downstream aging logic. Rejected.

---

## Decision 4 — Auth-state guard module

**Decision**: A new module `ml_service/verifier/auth_guard.py` exposes two pure functions:

```python
def has_li_at(state: dict) -> bool: ...
def is_valid_state_path(path: str) -> bool: ...
```

The browser pool's persistence step is replaced with:

```python
new_state = ctx.storage_state()
if has_li_at(new_state):
    write_state_file(path, new_state)
# else: don't overwrite; the saved file (which we read at start) is preserved as-is
```

**Rationale**:
- The current bug is that `ctx.storage_state(path=...)` writes unconditionally. Pulling the state into Python first, then deciding whether to write, surfaces the invariant in code that's testable without Playwright.
- A single module owned by the verifier package avoids scattering the rule. The crawler will call it via the same pool.

**Alternatives considered**:
- *Move the invariant inside `linkedin_auth.load_state_path`*: works for reads but the write path also needs the guard. A separate module makes the symmetry explicit.
- *Throw an exception on missing `li_at` at write time*: surprises callers and forces try/except boilerplate. A boolean check is enough — the existing log line is the operator surface.

---

## Decision 5 — Mid-batch session-loss detection

**Decision**: After each `page.goto(url)` in the verifier/extractor, check whether the page's current cookies still contain `li_at` (`ctx.cookies(...)`). If not, return `SESSION_EXPIRED` for that URL and remaining URLs in the batch; do not overwrite the state file on exit.

**Rationale**:
- Today, LinkedIn can invalidate a session by issuing a `Set-Cookie: li_at=; Max-Age=0` while serving a job page that still looks like a guest layout (no redirect to `/login`). The current code (URL-pattern check) misses this.
- A cookie-level check is cheap (≤ 1ms per page) and catches the case before we silently process more URLs under guest auth.
- Aborting the batch cleanly (rather than continuing) lets the operator see one "Auth lost" alert instead of a flood of misclassified outcomes.

**Alternatives considered**:
- *Only do the URL-pattern check (status quo)*: misses the "guest layout without redirect" case which is exactly what we observed. Rejected.
- *Periodic re-check every N URLs*: cheaper but loses the first-failure boundary. The check is so cheap doing it every navigation is fine.

---

## Decision 6 — Backfill candidate selection

**Decision**:

```sql
SELECT id, source_url
FROM jobs
WHERE platform_id = :linkedin_id
  AND date_posted IS NULL
  AND lifecycle IN ('active', 'stale')
  AND (verification_backoff_until IS NULL OR verification_backoff_until <= now())
ORDER BY last_seen_at DESC
LIMIT :batch;
```

**Rationale**:
- `date_posted IS NULL` is the gap; this is the only filter that ensures idempotency / resumability.
- `lifecycle IN ('active', 'stale')` skips already-expired rows (no date is recoverable for them).
- Backoff respected so the extractor doesn't fight the verifier over the same rows.
- `ORDER BY last_seen_at DESC` picks the most-recently-crawled jobs first; their pages are most likely to still be alive.

**Alternatives considered**:
- *Skip the lifecycle filter*: would visit expired jobs and waste time; the page redirects mean we can't get a date anyway. Rejected.
- *Random ordering*: harder to reason about progress / resumption.

---

## Decision 7 — Crawler integration

**Decision**: `linkedin_provider.py` calls `extract_date_posted(page)` at the same point where it currently reads `date_posted_text`. The relative text is no longer stored in `RawJob.seniority_hint`. The returned date populates `RawJob.date_posted` (already a field). The legacy `seniority_hint` plumbing is left untouched for non-date callers.

**Rationale**:
- Single source of truth: the same extractor function the backfill uses.
- The crawler already opens the page; adding the extractor call is two lines plus the import.
- Storing relative text in `seniority_hint` was the original misuse; fixing it doesn't break anything because no consumer reads it.

**Alternatives considered**:
- *Add a separate cron just for date extraction at ingestion*: doubles page loads.
- *Keep the legacy relative-text storage and add the new date alongside*: confusing. Remove the dead code path during the fix.

---

## Decision 8 — Test strategy

**Decision**:

- **Pure parser tests** (`test_date_extractor.py`): cover the relative parser against ~20 inputs (singular/plural, "today/yesterday/just now", edge units, garbage input), JSON-LD selection across mixed `@type` arrays, guardrail clamping.
- **Auth-guard tests** (`test_auth_guard.py`): `has_li_at` on present / absent / empty cookie array, plus a tempfile-based test that proves the persist-no-op path leaves the original file byte-identical.
- **Extractor + Playwright stub** (`test_date_extractor.py`): use a `FakePage` exposing `query_selector_all`, `evaluate`, `locator` — no real browser.
- **Backfill orchestrator** (`test_extract_command.py` or extend `test_verifier.py`): fake verifier-style service, fake repository, assert candidate selection, write semantics, dry-run behaviour, `--platform` validation.

**Rationale**: same shape as the verifier's test layout (feature 001) — pure logic via fakes, no real browser in CI.

---

## Open items

None. Spec had zero NEEDS CLARIFICATION; no further blockers before Phase 1.
