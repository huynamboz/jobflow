"""CrawlProvider backed by python-jobspy (Indeed, Glassdoor, LinkedIn, etc.)."""

from __future__ import annotations

import logging

import pandas as pd

from ml_service.crawler.base import CrawlProvider, RawJob

logger = logging.getLogger(__name__)

# Columns we care about from the JobSpy DataFrame
_KEEP_COLS = [
    "site",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "description",
    "job_type",
    "is_remote",
    "min_amount",
    "max_amount",
    "currency",
    "date_posted",
    "company_url",
    "company_industry",
    "company_num_employees",
    "logo_photo_url",
]


class JobSpyProvider(CrawlProvider):
    """Wraps python-jobspy's scrape_jobs() into the CrawlProvider interface.

    Default sites: Indeed only (most reliable, no aggressive rate limiting).
    Pass ``sites=["indeed", "glassdoor"]`` to expand.
    """

    def __init__(self, sites: list[str] | None = None) -> None:
        self._sites = sites or ["indeed"]

    @property
    def name(self) -> str:
        return "jobspy"

    def fetch(
        self,
        search_term: str,
        location: str = "",
        results_wanted: int = 100,
        **kwargs,
    ) -> list[RawJob]:
        from jobspy import scrape_jobs

        hours_old = kwargs.get("hours_old", 168)  # default: last 7 days
        country = kwargs.get("country_indeed", "USA")

        logger.info(
            "JobSpy fetching: term=%r, location=%r, sites=%s, results=%d",
            search_term,
            location,
            self._sites,
            results_wanted,
        )

        df: pd.DataFrame = scrape_jobs(
            site_name=self._sites,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country,
        )

        if df.empty:
            logger.warning("JobSpy returned 0 results")
            return []

        logger.info("JobSpy returned %d raw rows", len(df))
        return self._to_raw_jobs(df)

    def _to_raw_jobs(self, df: pd.DataFrame) -> list[RawJob]:
        """Convert JobSpy DataFrame rows to RawJob instances."""
        jobs: list[RawJob] = []
        for _, row in df.iterrows():
            title = _safe_str(row.get("title"))
            description = _safe_str(row.get("description"))
            if not title or not description:
                continue

            salary_min = _safe_float(row.get("min_amount"))
            salary_max = _safe_float(row.get("max_amount"))
            currency = _safe_str(row.get("currency")) or "USD"
            salary_interval = _safe_str(row.get("interval")) or None  # yearly/monthly/weekly/daily/hourly

            date_posted = row.get("date_posted")
            if pd.isna(date_posted):
                date_posted = None

            # Extra metadata that RawJob has no first-class field for.
            extra: dict = {}
            industry = _safe_str(row.get("company_industry"))
            if industry:
                extra["company_industry"] = industry
            size = _safe_str(row.get("company_num_employees"))
            if size:
                extra["company_size"] = size
            remote = row.get("is_remote")
            if pd.notna(remote):
                extra["is_remote"] = bool(remote)
            apply_url = _safe_str(row.get("job_url_direct"))
            if apply_url:
                extra["apply_url"] = apply_url

            jobs.append(
                RawJob(
                    source=_safe_str(row.get("site")) or "indeed",
                    source_url=_safe_str(row.get("job_url")) or "",
                    title=title,
                    company=_safe_str(row.get("company")) or "Unknown",
                    location=_safe_str(row.get("location")) or "",
                    description=description,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=currency,
                    salary_interval=salary_interval,
                    date_posted=date_posted,
                    job_type=_safe_str(row.get("job_type")),
                    company_logo_url=_safe_str(row.get("logo_photo_url")),
                    company_url=_safe_str(row.get("company_url")),
                    extra=extra,
                )
            )
        return jobs


def _safe_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if pd.isna(f):
            return None
        return f
    except (ValueError, TypeError):
        return None
