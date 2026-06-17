"""CrawlProvider backed by Adzuna REST API.

Free tier: rate-limited but no scraping needed. Structured data with salary.
Requires API key: https://developer.adzuna.com/

Env vars: ADZUNA_APP_ID, ADZUNA_APP_KEY
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import requests

from ml_service.crawler.base import CrawlProvider, RawJob

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaProvider(CrawlProvider):
    """Adzuna REST API provider.

    Usage:
        provider = AdzunaProvider(app_id="xxx", app_key="yyy")
        jobs = provider.fetch("python developer", location="us", results_wanted=50)
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_key: str | None = None,
        country: str = "us",
    ) -> None:
        self._app_id = app_id or os.environ.get("ADZUNA_APP_ID", "")
        self._app_key = app_key or os.environ.get("ADZUNA_APP_KEY", "")
        self._country = country

    @property
    def name(self) -> str:
        return "adzuna"

    def fetch(
        self,
        search_term: str,
        location: str = "",
        results_wanted: int = 100,
        **kwargs,
    ) -> list[RawJob]:
        if not self._app_id or not self._app_key:
            logger.error("Adzuna API credentials not set (ADZUNA_APP_ID, ADZUNA_APP_KEY)")
            return []

        country = kwargs.get("country", self._country)
        page_size = min(results_wanted, 50)  # Adzuna max 50 per page
        pages = (results_wanted + page_size - 1) // page_size

        all_jobs: list[RawJob] = []

        for page in range(1, pages + 1):
            try:
                params = {
                    "app_id": self._app_id,
                    "app_key": self._app_key,
                    "what": search_term,
                    "results_per_page": page_size,
                    "content-type": "application/json",
                }
                if location:
                    params["where"] = location

                url = f"{_BASE_URL}/{country}/search/{page}"
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    job = self._to_raw_job(item)
                    if job:
                        all_jobs.append(job)

                logger.info("Adzuna page %d: %d jobs", page, len(results))

                if len(all_jobs) >= results_wanted:
                    break

            except Exception as e:
                logger.error("Adzuna fetch error (page %d): %s", page, e)
                break

        logger.info("Adzuna total: %d jobs for '%s'", len(all_jobs), search_term)
        return all_jobs[:results_wanted]

    @staticmethod
    def _to_raw_job(item: dict) -> RawJob | None:
        title = item.get("title", "").strip()
        description = item.get("description", "").strip()
        if not title or not description:
            return None

        company = item.get("company", {}).get("display_name", "")
        location = item.get("location", {}).get("display_name", "")

        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")

        date_str = item.get("created")
        date_posted = None
        if date_str:
            try:
                date_posted = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return RawJob(
            source="adzuna",
            source_url=item.get("redirect_url", ""),
            title=title,
            company=company,
            location=location,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="USD",
            salary_interval="annual",  # Adzuna salaries are annualized
            date_posted=date_posted,
        )
