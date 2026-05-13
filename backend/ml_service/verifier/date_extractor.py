"""Date extraction for LinkedIn job pages.

Single pure function ``extract_date_posted(page)`` consumed by both the
LinkedIn crawler (at ingestion) and the date-backfill command. Returns
an absolute UTC date or None — never relative text.

Spec: 002-job-date-posted-extraction (US1).
Contract: specs/002-job-date-posted-extraction/contracts/date_extractor.md
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


_GUARDRAIL_MAX_AGE_DAYS = 730

# Selectors scoped to the main job posting — NOT "more jobs from..." / "people
# also viewed" sections, where unrelated <time> elements live.
_SCOPED_DATETIME_SELECTORS = (
    # Authenticated layout
    "div.job-details-jobs-unified-top-card__tertiary-description-container time[datetime]",
    "div.jobs-unified-top-card time[datetime]",
    # Guest / public layout
    "div.top-card-layout time[datetime]",
    "span.posted-time-ago time[datetime]",
)

_SCOPED_TEXT_SELECTORS = (
    "div.job-details-jobs-unified-top-card__tertiary-description-container",
    "div.top-card-layout__second-subline",
    "div.posted-time-ago",
    "div.top-card-layout",
)

_EXPIRED_REDIRECT_MARKER = "trk=expired_jd_redirect"


# ─── Result type ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DateExtractionResult:
    date: datetime | None
    source: str  # one of: datetime-attribute | json-ld | relative-text | expired-redirect | none


# ─── Relative-text parser ─────────────────────────────────────────────────


_RELATIVE_NUMERIC_RE = re.compile(
    r"(?:posted|reposted)?\s*"
    r"(\d+)\s+"
    r"(minute|hour|day|week|month|year)s?"
    r"\s+ago",
    re.IGNORECASE,
)

_RELATIVE_TODAY_KEYWORDS = re.compile(r"\b(?:just\s+now|today)\b", re.IGNORECASE)
_RELATIVE_YESTERDAY_KEYWORDS = re.compile(r"\byesterday\b", re.IGNORECASE)

_UNIT_TO_DAYS = {
    "minute": 0,
    "hour": 0,
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}


def parse_relative(text: str, now: datetime) -> datetime | None:
    """Parse a LinkedIn-style relative time phrase to an absolute UTC date.

    Returns midnight-UTC on the resolved date. Returns None if no pattern
    matches OR the resolved date violates the guardrails.
    """
    if not text or not isinstance(text, str):
        return None

    today = _utc_midnight(now)

    # "just now" / "today"
    if _RELATIVE_TODAY_KEYWORDS.search(text):
        return _apply_guardrails(today, now)
    # "yesterday"
    if _RELATIVE_YESTERDAY_KEYWORDS.search(text):
        return _apply_guardrails(today - timedelta(days=1), now)
    # "N <unit> ago"
    m = _RELATIVE_NUMERIC_RE.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = _UNIT_TO_DAYS.get(unit, 0) * n
        candidate = today - timedelta(days=days)
        return _apply_guardrails(candidate, now)

    return None


# ─── Guardrails ───────────────────────────────────────────────────────────


def _utc_midnight(dt: datetime) -> datetime:
    """Return a tz-aware UTC datetime at midnight on dt's UTC date."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)


def _apply_guardrails(candidate: datetime, now: datetime) -> datetime | None:
    """Return the candidate iff it falls within (now - 730d, now]. Otherwise None."""
    if candidate is None:
        return None
    today = _utc_midnight(now)
    earliest = today - timedelta(days=_GUARDRAIL_MAX_AGE_DAYS)
    candidate = _utc_midnight(candidate)
    if candidate < earliest or candidate > today:
        return None
    return candidate


# ─── Per-source extractors ────────────────────────────────────────────────


def _extract_from_json_ld(page, now: datetime) -> datetime | None:
    """Look for a JSON-LD JobPosting block with datePosted."""
    try:
        scripts = page.locator('script[type="application/ld+json"]')
        n = scripts.count()
    except Exception:
        return None

    for i in range(n):
        try:
            raw = scripts.nth(i).inner_text()
            data = json.loads(raw)
        except Exception:
            continue
        # JSON-LD may be a single object or a list
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "JobPosting":
                continue
            dp = obj.get("datePosted")
            if not isinstance(dp, str):
                continue
            try:
                parsed = datetime.fromisoformat(dp.replace("Z", "+00:00"))
            except ValueError:
                # Try date-only form
                try:
                    parsed = datetime.fromisoformat(dp + "T00:00:00+00:00")
                except ValueError:
                    continue
            checked = _apply_guardrails(parsed, now)
            if checked:
                return checked
    return None


def _extract_from_datetime_attribute(page, now: datetime) -> datetime | None:
    """Scoped to top-card / tertiary-info containers only."""
    for selector in _SCOPED_DATETIME_SELECTORS:
        try:
            loc = page.locator(selector)
            n = loc.count()
        except Exception:
            continue
        for i in range(n):
            try:
                dt_attr = loc.nth(i).get_attribute("datetime")
            except Exception:
                continue
            if not dt_attr:
                continue
            try:
                parsed = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(dt_attr + "T00:00:00+00:00")
                except ValueError:
                    continue
            checked = _apply_guardrails(parsed, now)
            if checked:
                return checked
    return None


def _extract_from_relative_text(page, now: datetime) -> datetime | None:
    """Read text from the scoped containers; pass through parse_relative."""
    for selector in _SCOPED_TEXT_SELECTORS:
        try:
            loc = page.locator(selector)
            n = loc.count()
        except Exception:
            continue
        for i in range(n):
            try:
                text = loc.nth(i).text_content(timeout=500) or ""
            except Exception:
                continue
            parsed = parse_relative(text, now)
            if parsed:
                return parsed
    return None


# ─── Orchestrator ─────────────────────────────────────────────────────────


def extract_date_posted(
    page, *, now: datetime | None = None
) -> DateExtractionResult:
    """See contracts/date_extractor.md.

    Priority: expired-redirect → json-ld → datetime-attribute → relative-text → none.
    """
    now = now or datetime.now(timezone.utc)

    # 1. Short-circuit on the expired-redirect URL pattern.
    try:
        final_url = page.url
    except Exception:
        final_url = ""
    if final_url and _EXPIRED_REDIRECT_MARKER in final_url:
        return DateExtractionResult(date=None, source="expired-redirect")

    # 2. JSON-LD.
    d = _extract_from_json_ld(page, now)
    if d is not None:
        logger.info("extract_date_posted: source=json-ld date=%s", d.date())
        return DateExtractionResult(date=d, source="json-ld")

    # 3. <time datetime>.
    d = _extract_from_datetime_attribute(page, now)
    if d is not None:
        logger.info("extract_date_posted: source=datetime-attribute date=%s", d.date())
        return DateExtractionResult(date=d, source="datetime-attribute")

    # 4. Relative text.
    d = _extract_from_relative_text(page, now)
    if d is not None:
        logger.info("extract_date_posted: source=relative-text date=%s", d.date())
        return DateExtractionResult(date=d, source="relative-text")

    return DateExtractionResult(date=None, source="none")
