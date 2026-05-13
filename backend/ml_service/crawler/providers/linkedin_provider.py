"""CrawlProvider for LinkedIn using Playwright with saved auth state.

Prerequisites:
    1. Run: .venv/bin/python -m ml_service.crawler.providers.linkedin_auth
    2. Login manually in the browser
    3. Auth state saved → provider uses it automatically

Crawl strategy:
    - Load saved auth state (cookies)
    - Search LinkedIn Jobs with keyword
    - Scroll job list to load more results
    - Click each job to get full description
    - Extract structured fields
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ml_service.crawler.base import CrawlProvider, RawJob
from ml_service.crawler.providers.linkedin_auth import load_state_path

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&start={offset}"
_SELECTORS_PATH = Path(__file__).parent / "linkedin_selectors.json"


def _load_selectors() -> dict:
    """Load CSS selectors from JSON config."""
    with open(_SELECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _query_first(el, selectors: list[str]) -> object | None:
    """Try multiple CSS selectors, return first match."""
    for sel in selectors:
        result = el.query_selector(sel)
        if result:
            return result
    return None


class LinkedInProvider(CrawlProvider):
    """LinkedIn job crawler via Playwright with authenticated session.

    Usage:
        # First time: run linkedin_auth.py to save login state
        provider = LinkedInProvider()
        jobs = provider.fetch("python developer", location="United States", results_wanted=50)

        # With stream save (write each job immediately):
        provider = LinkedInProvider(save_path="data/raw_jobs.jsonl")
        jobs = provider.fetch("react developer", results_wanted=250)
    """

    def __init__(self, headless: bool = True, save_path: str | None = None) -> None:
        self._headless = headless
        self._save_path = save_path
        self._sel = _load_selectors()

    @property
    def name(self) -> str:
        return "linkedin"

    def fetch(
        self,
        search_term: str,
        location: str = "",
        results_wanted: int = 50,
        **kwargs,
    ) -> list[RawJob]:
        state_path = load_state_path()
        if not state_path:
            logger.error(
                "LinkedIn auth state not found. Run: "
                ".venv/bin/python -m ml_service.crawler.providers.linkedin_auth"
            )
            return []

        from patchright.sync_api import sync_playwright

        jobs: list[RawJob] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self._headless)
            context = browser.new_context(
                storage_state=state_path,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                jobs = self._crawl_jobs(page, search_term, location, results_wanted)
            except Exception as e:
                logger.error("LinkedIn crawl failed: %s", e)
            finally:
                # Update auth state (refresh cookies)
                context.storage_state(path=state_path)
                browser.close()

        logger.info("LinkedIn: %d jobs for '%s'", len(jobs), search_term)
        return jobs

    def _stream_save(self, job: RawJob) -> None:
        """Write a single job to file immediately."""
        if not self._save_path:
            return
        from ml_service.crawler.storage import save_raw_jobs
        save_raw_jobs([job], self._save_path)

    def _crawl_jobs(
        self, page, search_term: str, location: str, results_wanted: int,
    ) -> list[RawJob]:
        """Crawl LinkedIn job listings with stream save + cross-session dedup."""
        jobs: list[RawJob] = []
        seen_fps: set[str] = set()
        offset = 0
        page_num = 0

        # Load existing fingerprints from file to avoid cross-session duplicates
        if self._save_path:
            from ml_service.crawler.storage import compute_fingerprint, load_raw_jobs
            existing = load_raw_jobs(self._save_path)
            for j in existing:
                seen_fps.add(compute_fingerprint(j))
            if seen_fps:
                logger.info("Loaded %d existing fingerprints for dedup", len(seen_fps))

        while len(jobs) < results_wanted:
            page_num += 1
            url = _SEARCH_URL.format(
                query=search_term.replace(" ", "%20"),
                location=location.replace(" ", "%20"),
                offset=offset,
            )
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(3)

            # Check if logged in
            auth_patterns = self._sel["auth_check"]["expired_url_patterns"]
            if any(p in page.url.lower() for p in auth_patterns):
                logger.error("LinkedIn session expired. Re-run linkedin_auth.py")
                break

            # Scroll to load all cards
            for _ in range(5):
                page.mouse.wheel(0, 800)
                time.sleep(0.8)

            # Get job cards
            cards = page.query_selector_all(self._sel["job_cards"]["primary"])
            if not cards:
                for fallback in self._sel["job_cards"]["fallback"]:
                    cards = page.query_selector_all(fallback)
                    if cards:
                        break

            if not cards:
                logger.warning("Page %d: no job cards found", page_num)
                break

            page_jobs = 0
            for card in cards:
                if len(jobs) >= results_wanted:
                    break

                try:
                    job = self._extract_job_from_card(page, card)
                    if not job:
                        continue

                    # In-memory dedup by fingerprint
                    from ml_service.crawler.storage import compute_fingerprint
                    fp = compute_fingerprint(job)
                    if fp in seen_fps:
                        continue
                    seen_fps.add(fp)

                    jobs.append(job)
                    page_jobs += 1

                    # Stream save — write immediately
                    self._stream_save(job)

                except Exception as e:
                    logger.debug("Failed to extract job card: %s", e)
                    continue

            logger.info(
                "Page %d (offset %d): %d new jobs, %d total",
                page_num, offset, page_jobs, len(jobs),
            )

            if page_jobs == 0:
                logger.info("No new jobs on page %d, stopping", page_num)
                break

            offset += 25
            time.sleep(2)  # Rate limiting

        return jobs

    def _extract_job_from_card(self, page, card) -> RawJob | None:
        """Click a job card and extract full details from detail panel.

        All CSS selectors loaded from linkedin_selectors.json.
        """
        sel = self._sel

        # Get basic info from card
        title_el = _query_first(card, sel["card"]["title"])
        company_el = _query_first(card, sel["card"]["company"])
        location_el = _query_first(card, sel["card"]["location"])
        link_el = _query_first(card, sel["card"]["link"])

        # Get link before clicking
        source_url = link_el.get_attribute("href") if link_el else ""

        # Click card to load detail panel
        try:
            card.click()
            time.sleep(1.5)
        except Exception:
            pass

        # --- Title from detail panel (clean, not card which has noise) ---
        title = ""
        title_detail = _query_first(page, sel["detail_panel"]["title"])
        if title_detail:
            title = title_detail.inner_text().strip()
        if not title:
            # Fallback: card title, take first line only
            raw = title_el.inner_text().strip() if title_el else ""
            title = raw.split("\n")[0].strip()

        # --- Company from detail panel (clean) ---
        company = ""
        company_detail = _query_first(page, sel["detail_panel"]["company_url"])
        if company_detail:
            company = company_detail.inner_text().strip()
        if not company:
            company = company_el.inner_text().strip() if company_el else ""

        # --- Location from detail panel ---
        location = ""
        location_el_card = _query_first(card, sel["card"]["location"])
        if location_el_card:
            location = location_el_card.inner_text().strip()

        if not title:
            return None

        # --- Description ---
        description = ""
        desc_el = _query_first(page, sel["detail_panel"]["description"])
        if desc_el:
            description = desc_el.inner_text().strip()

        if not description or len(description) < 50:
            return None

        # --- Company logo ---
        company_logo_url = ""
        logo_el = _query_first(page, sel["detail_panel"]["company_logo"])
        if logo_el:
            company_logo_url = logo_el.get_attribute("src") or ""

        # --- Company URL ---
        company_url = ""
        company_link_el = _query_first(page, sel["detail_panel"]["company_url"])
        if company_link_el:
            href = company_link_el.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = f"https://www.linkedin.com{href}"
            company_url = href

        # --- Date posted + applicant count ---
        # Date is extracted by the shared extractor — same function the
        # backfill command uses. See spec 002-job-date-posted-extraction.
        from ml_service.verifier.date_extractor import extract_date_posted
        date_result = extract_date_posted(page)
        date_posted = date_result.date  # datetime | None

        applicant_count = ""
        tertiary_el = _query_first(page, sel["detail_panel"]["tertiary_info"])
        if tertiary_el:
            spans = tertiary_el.query_selector_all(sel["detail_panel"]["tertiary_spans"][0])
            for span in spans:
                text = span.inner_text().strip()
                if "applicant" in text.lower():
                    applicant_count = text

        # --- Salary ---
        salary_min, salary_max, salary_currency = self._extract_salary(page)

        # --- Job type (Remote, Contract, Full-time, etc.) ---
        job_type = ""
        fit_buttons = page.query_selector_all(sel["detail_panel"]["fit_preferences"][0])
        type_keywords = ["remote", "contract", "full-time", "part-time", "hybrid", "on-site"]
        for btn in fit_buttons:
            btn_text = btn.inner_text().strip().lower()
            for kw in type_keywords:
                if kw in btn_text:
                    job_type = (job_type + ", " + kw) if job_type else kw

        # --- Company industry + size (About the company section) ---
        company_industry = ""
        company_size = ""
        about_sel = sel.get("about_company", {})
        industry_el = _query_first(page, about_sel.get("industry", []))
        if industry_el:
            company_industry = industry_el.inner_text().strip().split("\n")[0].strip()

        size_els = page.query_selector_all(about_sel.get("size", [""])[0]) if about_sel.get("size") else []
        for size_el in size_els:
            text = size_el.inner_text().strip()
            if "employee" in text.lower():
                company_size = text
                break

        # --- Location from tertiary (APJ, Vietnam, etc.) ---
        if not location and tertiary_el:
            first_span = tertiary_el.query_selector(sel["detail_panel"]["tertiary_spans"][0])
            if first_span:
                loc_text = first_span.inner_text().strip()
                if loc_text and "ago" not in loc_text and "applicant" not in loc_text.lower():
                    location = loc_text

        # --- Clean URL ---
        if source_url and not source_url.startswith("http"):
            source_url = f"https://www.linkedin.com{source_url}"

        return RawJob(
            source="linkedin",
            source_url=source_url,
            title=title,
            company=company,
            location=location,
            description=description[:5000],
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            date_posted=date_posted,
            company_logo_url=company_logo_url,
            company_url=company_url,
            job_type=job_type,
            applicant_count=applicant_count,
            extra={
                "company_industry": company_industry,
                "company_size": company_size,
            },
        )

    def _extract_salary(self, page) -> tuple[float | None, float | None, str]:
        """Extract salary using selectors from JSON config."""
        for sel in self._sel["detail_panel"]["salary"]:
            elements = page.query_selector_all(sel)
            for el in elements:
                text = el.inner_text().strip()
                if "$" in text or "€" in text or "£" in text:
                    currency = "EUR" if "€" in text else ("GBP" if "£" in text else "USD")
                    numbers = re.findall(r"[\d,]+", text.replace(",", ""))
                    if len(numbers) >= 2:
                        return float(numbers[0]), float(numbers[1]), currency
                    elif len(numbers) == 1:
                        return float(numbers[0]), None, currency

        return None, None, "USD"
