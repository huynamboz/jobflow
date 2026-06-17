"""CrawlProvider backed by RemoteOK public JSON API.

Endpoint: https://remoteok.com/api?tags=<comma-separated-tags>
No auth required. Returns latest remote tech jobs.

Schema notes:
- ``tags`` filter is AND across comma-separated values.
- Salary currency is not exposed by the API; we default to USD with a heuristic
  flag for clearly non-USD amounts (e.g. < 1k → likely hourly; >300k → unusual).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterable

import requests

from ml_service.crawler.base import CrawlProvider, RawJob

logger = logging.getLogger(__name__)

_BASE_URL = "https://remoteok.com/api"
_DEFAULT_HEADERS = {
    "User-Agent": "jobflow-gnn/0.1 (academic research)",
    "Accept": "application/json",
}

# Map free-text search terms to RemoteOK tag(s). RemoteOK doesn't accept a full
# search query, only tag filters — so we translate to tags. Use AND filters
# (comma-separated) sparingly; they shrink yield fast.
_TAG_ALIASES: dict[str, list[str]] = {
    "backend engineer": ["backend"],
    "backend developer": ["backend"],
    "frontend engineer": ["frontend"],
    "frontend developer": ["frontend"],
    "fullstack engineer": ["full-stack"],
    "ios developer": ["ios"],
    "android developer": ["android"],
    "mobile engineer": ["mobile"],
    "mobile developer": ["mobile"],
    "data engineer": ["engineer"],  # RemoteOK has no "data" tag — falls back to general engineer
    "machine learning engineer": ["ai"],
    "ml engineer": ["ai"],
    "ai engineer": ["ai"],
    "devops engineer": ["devops"],
    "software engineer": ["engineer"],
    "python developer": ["python"],
    "javascript developer": ["javascript"],
    "java developer": ["java"],
    "golang developer": ["golang"],
}


class RemoteOKProvider(CrawlProvider):
    """RemoteOK public JSON provider.

    Usage:
        provider = RemoteOKProvider()
        jobs = provider.fetch("backend engineer", results_wanted=50)
        # or pass tags directly:
        jobs = provider.fetch("python,backend", results_wanted=50)
    """

    def __init__(self, request_delay_s: float = 1.0) -> None:
        self._delay = request_delay_s

    @property
    def name(self) -> str:
        return "remoteok"

    def fetch(
        self,
        search_term: str,
        location: str = "",  # unused — RemoteOK is remote-only
        results_wanted: int = 100,
        **kwargs,
    ) -> list[RawJob]:
        tags = self._term_to_tags(search_term)
        if not tags:
            logger.warning("RemoteOK: no tag mapping for %r — skipping", search_term)
            return []

        params = {"tags": ",".join(tags)}
        logger.info("RemoteOK fetching: term=%r → tags=%s", search_term, tags)

        try:
            resp = requests.get(_BASE_URL, params=params, headers=_DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("RemoteOK fetch failed: %s", e)
            return []

        # First element is meta {legal, last_updated}
        raw_items = [x for x in data if isinstance(x, dict) and "position" in x]
        logger.info("RemoteOK returned %d entries for tags=%s", len(raw_items), tags)

        jobs: list[RawJob] = []
        for item in raw_items[:results_wanted]:
            j = self._to_raw_job(item)
            if j:
                jobs.append(j)

        time.sleep(self._delay)  # be polite — public free API
        return jobs

    @staticmethod
    def _term_to_tags(term: str) -> list[str]:
        norm = (term or "").lower().strip()
        if not norm:
            return []
        # Direct tag pass-through (caller already gave tags)
        if "," in norm or norm in _TAG_ALIASES.values():
            return [t.strip() for t in norm.split(",") if t.strip()]
        if norm in _TAG_ALIASES:
            return _TAG_ALIASES[norm]
        # Fallback: try the term as a single tag
        return [norm.replace(" ", "-")]

    @staticmethod
    def _to_raw_job(item: dict) -> RawJob | None:
        title = (item.get("position") or "").strip()
        description = (item.get("description") or "").strip()
        if not title or not description:
            return None

        # RemoteOK descriptions are HTML — strip tags + collapse whitespace.
        import re
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

        company = (item.get("company") or "").strip() or "Unknown"
        location = (item.get("location") or "").strip() or "Remote"

        salary_min = _num(item.get("salary_min"))
        salary_max = _num(item.get("salary_max"))
        # RemoteOK doesn't expose currency. USD when in a plausible annual range;
        # otherwise blank to avoid a bad signal.
        currency = "USD" if (salary_max and 1000 < salary_max < 1_000_000) else ""

        date_posted = None
        date_str = item.get("date")
        if date_str:
            try:
                date_posted = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        source_url = (item.get("apply_url") or item.get("url") or "").strip()
        tags = item.get("tags") or []
        logo = (item.get("company_logo") or item.get("logo") or "").strip()

        return RawJob(
            source="remoteok",
            source_url=source_url,
            title=title,
            company=company,
            location=location,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_interval="annual",  # RemoteOK salaries are annual ranges
            date_posted=date_posted,
            raw_skills=tuple(t for t in tags if isinstance(t, str) and t.strip()),
            company_logo_url=logo,
        )


def _num(val) -> float | None:
    """RemoteOK salary → float; treat 0 / empty / invalid as None."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None
