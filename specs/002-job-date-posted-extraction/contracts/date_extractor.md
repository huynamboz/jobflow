# Contract: `extract_date_posted(page)`

**Scope**: The single pure function called by both the LinkedIn crawler and the backfill command to produce a date from a Playwright page.

**Location**: `backend/ml_service/verifier/date_extractor.py`

---

## Signature

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class DateExtractionResult:
    date: datetime | None
    source: str   # datetime-attribute | json-ld | relative-text | expired-redirect | none

def extract_date_posted(page) -> DateExtractionResult: ...
```

`page` is anything that quacks like a Playwright `Page` — supports `page.url`, `page.locator(...)`, `page.evaluate(js)`, `page.query_selector_all(...)`. Tests pass a `FakePage` shim.

---

## Behaviour

The function MUST evaluate the four sources below in this exact order and return at the first success:

1. **expired-redirect** — if `page.url` contains `trk=expired_jd_redirect`, return `DateExtractionResult(None, "expired-redirect")`. (Short-circuit: we can't get a date and the verifier's lifecycle write applies.)

2. **json-ld** — iterate `<script type="application/ld+json">` blocks. For each block, JSON-parse the content. If the parsed object has `@type == "JobPosting"` and a `datePosted` field, parse the date as ISO-8601 (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`). Apply guardrails. Return with `source="json-ld"`.

3. **datetime-attribute** — find `<time datetime="...">` elements **scoped** to the job-detail top-card / tertiary-info container:
   - Authenticated layout selector: `div.job-details-jobs-unified-top-card__tertiary-description-container time[datetime]`
   - Guest layout selector: `div.top-card-layout__second-subline time[datetime]`, `span.posted-time-ago time[datetime]`
   
   Parse the `datetime` attribute as ISO date. Apply guardrails. Return with `source="datetime-attribute"`.

4. **relative-text** — collect text from the same scoped selectors above; if no scoped match, fall back to scanning `tertiary_info` spans for substrings matching the patterns. Pass each candidate to `parse_relative(text, now=utcnow())`. Apply guardrails. Return with `source="relative-text"`.

5. **none** — none of the above succeeded. Return `DateExtractionResult(None, "none")`.

---

## Relative-text parser (`parse_relative`)

```python
def parse_relative(text: str, now: datetime) -> datetime | None: ...
```

Accepts (case-insensitive, optional "Posted " or "Reposted " prefix stripped before matching):

| Pattern | Result |
|---------|--------|
| `just now`, `today` | `now.date()` |
| `yesterday` | `now.date() - 1 day` |
| `\d+ minute(s)? ago` | `now.date()` (sub-day) |
| `\d+ hour(s)? ago` | `now.date()` |
| `\d+ day(s)? ago` | `now.date() - N days` |
| `\d+ week(s)? ago` | `now.date() - N * 7 days` |
| `\d+ month(s)? ago` | `now.date() - N * 30 days` |
| `\d+ year(s)? ago` | `now.date() - N * 365 days` |

Returns `None` if no pattern matches or if the resulting date violates the guardrails.

---

## Guardrails

A candidate date is accepted iff:

```
(now - 730 days) ≤ date.date() ≤ now.date()
```

Where `now` is the current UTC datetime. Both endpoints inclusive. Out-of-range candidates are discarded (treated as "no match" — the next source in priority order is tried).

---

## Return-value invariants

- `date` is either `None` or a tz-aware UTC datetime with `hour=minute=second=0` (midnight).
- `source` is always one of the five string values; never empty.
- The function MUST be side-effect-free: no DB writes, no logging at WARNING+, no global mutation. Side effects are the orchestrator's job.

---

## Exception policy

The function MUST NOT raise. Internal failures (broken JSON-LD, locator timeouts, etc.) are swallowed and treated as "this source didn't match — try the next". An orchestrator wraps the call in its own try/except as a defensive layer (FR-015), but a well-behaved extractor never relies on that wrapper.
