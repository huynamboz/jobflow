"""CrawlProvider backed by Freelancer.com public Projects API.

Free, no auth for active projects. https://www.freelancer.com/api/
Returns freelance *projects* (fixed/hourly) — treated as remote jobs. There is
no "company" (projects are posted by individual clients, owner name not exposed
without auth), so ``company`` is set to a fixed "Freelancer client" label rather
than blank (which would normalize to the shared "Unknown" company).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone as _tz

import requests

from ml_service.crawler.base import CrawlProvider, RawJob

logger = logging.getLogger(__name__)

_API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
_HEADERS = {
    "User-Agent": "jobflow-gnn/0.1 (academic research)",
    "Accept": "application/json",
}
_PAGE = 50  # results per request


class FreelancerProvider(CrawlProvider):
    """Freelancer.com active-projects provider — free, no auth.

    Usage:
        provider = FreelancerProvider()
        jobs = provider.fetch("react developer", results_wanted=50)
    """

    def __init__(self, request_delay_s: float = 0.5) -> None:
        self._delay = request_delay_s

    @property
    def name(self) -> str:
        return "freelancer"

    def fetch(
        self,
        search_term: str,
        location: str = "",  # unused — projects are online/remote
        results_wanted: int = 100,
        **kwargs,
    ) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        offset = 0

        while len(jobs) < results_wanted:
            limit = min(_PAGE, results_wanted - len(jobs))
            params = {
                "query": search_term,
                "limit": limit,
                "offset": offset,
                "job_details": "true",
                "full_description": "true",
            }
            try:
                resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=30)
                resp.raise_for_status()
                projects = (resp.json().get("result") or {}).get("projects") or []
            except Exception as e:  # noqa: BLE001
                logger.error("Freelancer fetch failed: %s", e)
                break

            if not projects:
                break

            added = 0
            for item in projects:
                job = self._to_raw_job(item)
                if not job or (job.source_url and job.source_url in seen):
                    continue
                if job.source_url:
                    seen.add(job.source_url)
                jobs.append(job)
                added += 1

            offset += len(projects)
            # last page (short) or offset ignored (no new rows) → stop
            if len(projects) < limit or added == 0:
                break
            time.sleep(self._delay)  # be polite — public free API

        logger.info("Freelancer: %d projects for %r", len(jobs), search_term)
        return jobs[:results_wanted]

    @staticmethod
    def _to_raw_job(item: dict) -> RawJob | None:
        title = (item.get("title") or "").strip()
        description = (item.get("description") or item.get("preview_description") or "").strip()
        if not title or not description:
            return None

        seo = (item.get("seo_url") or "").strip()
        source_url = f"https://www.freelancer.com/projects/{seo}" if seo else ""

        budget = item.get("budget") or {}
        salary_min = _num(budget.get("minimum"))
        salary_max = _num(budget.get("maximum"))
        currency = ((item.get("currency") or {}).get("code") or "").strip() or "USD"

        date_posted = None
        epoch = item.get("time_submitted") or item.get("submitdate")
        if epoch:
            try:
                date_posted = datetime.fromtimestamp(int(epoch), tz=_tz.utc)
            except (ValueError, TypeError, OSError):
                pass

        skills = tuple(
            (j.get("name") or "").strip()
            for j in (item.get("jobs") or [])
            if (j.get("name") or "").strip()
        )

        bid_stats = item.get("bid_stats") or {}
        bid_count = bid_stats.get("bid_count")
        country = ((item.get("location") or {}).get("country") or {}).get("name") or ""

        extra: dict = {"budget_type": (item.get("type") or "").strip()}
        if bid_stats.get("bid_avg"):
            extra["bid_avg"] = bid_stats["bid_avg"]
        pid = item.get("id")
        if pid:
            extra["project_id"] = pid

        return RawJob(
            source="freelancer",
            source_url=source_url,
            title=title,
            company="Freelancer client",  # projects have an individual client, not a company (name not exposed by the public API)
            location=country.strip() or "Remote",
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            date_posted=date_posted,
            job_type=(item.get("type") or "").strip(),  # "fixed" | "hourly"
            raw_skills=skills,
            applicant_count=str(bid_count) if bid_count is not None else "",
            extra=extra,
        )


def _num(val) -> float | None:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None
