"""Trimmed crawler package — sandbox only keeps RawJob and CrawlProvider ABC
because backend/ml_benchmark/data/skill_extractor.py imports RawJob.

Production providers (LinkedIn, Adzuna, RemoteOK, JobSpy, Remotive),
storage, scheduler, factory are all stripped — sandbox does not crawl.
"""

from ml_benchmark.crawler.base import CrawlProvider, RawJob

__all__ = ["CrawlProvider", "RawJob"]
