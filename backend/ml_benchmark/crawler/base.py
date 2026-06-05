"""Abstract base for crawl providers.

Every provider returns a list of RawJob — a flat, provider-agnostic
dataclass that downstream modules (skill extraction, graph builder)
consume. New providers only need to implement ``fetch()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RawJob:
    """Provider-agnostic job posting."""

    source: str  # e.g. "indeed", "adzuna", "topcv", "linkedin"
    source_url: str
    title: str
    company: str
    location: str
    description: str  # full text (for embedding + skill extraction)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    date_posted: datetime | None = None
    seniority_hint: str | None = None  # raw text like "senior", "entry level"
    raw_skills: tuple[str, ...] = ()  # skills extracted by the provider (if any)
    company_logo_url: str = ""  # company logo image URL
    company_url: str = ""  # company profile URL (e.g. LinkedIn company page)
    job_type: str = ""  # "full-time", "contract", "part-time", "remote"
    applicant_count: str = ""  # e.g. "Over 100 applicants"
    extra: dict = field(default_factory=dict)  # provider-specific metadata


class CrawlProvider(ABC):
    """Interface that all crawl providers implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider identifier (e.g. 'jobspy', 'adzuna')."""

    @abstractmethod
    def fetch(
        self,
        search_term: str,
        location: str = "",
        results_wanted: int = 100,
        **kwargs,
    ) -> list[RawJob]:
        """Fetch job postings matching the query.

        Implementations should handle retries and rate limiting internally.
        """
