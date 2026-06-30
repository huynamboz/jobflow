"""CrawlProvider for LinkedIn.

Two crawl modes — guest (default, NO login) and authenticated (opt-in):

* GUEST (default): hits the public ``/jobs-guest`` HTTP endpoints with plain
  ``requests`` — no cookies, no browser, no login. List endpoint returns 10
  cards/page; a per-job detail request fills in the full description. Lighter
  and zero-setup, but more aggressively rate-limited (429) and missing salary /
  applicant-count for most postings.

* AUTHENTICATED (``auth=True``): the original Playwright flow using a saved
  login session. Richer fields (full description, salary, applicant count),
  fewer 429s. Prerequisites:
    1. Run: .venv/bin/python -m ml_service.crawler.providers.linkedin_auth
    2. Login manually in the browser → auth state saved → used automatically.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ml_service.crawler.base import CrawlProvider, RawJob
from ml_service.crawler.providers.linkedin_auth import load_state_path

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&start={offset}"
_SELECTORS_PATH = Path(__file__).parent / "linkedin_selectors.json"

# Guest (login-free) endpoints.
_GUEST_LIST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_GUEST_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_GUEST_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_GUEST_HEADERS = {"User-Agent": _GUEST_UA, "Accept-Language": "en-US,en;q=0.9"}
_GUEST_PAGE = 10  # cards per guest list page (fixed by LinkedIn)


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

    def __init__(
        self,
        headless: bool = True,
        save_path: str | None = None,
        auth: bool = False,
        request_delay: float = 1.5,
    ) -> None:
        self._headless = headless
        self._save_path = save_path
        self._auth = auth
        self._guest_delay = request_delay
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
        """Dispatch to guest (default, login-free) or authenticated mode."""
        if self._auth:
            return self._fetch_authenticated(search_term, location, results_wanted, **kwargs)
        return self._fetch_guest(search_term, location, results_wanted, **kwargs)

    # ── guest mode (login-free) ────────────────────────────────────────────────
    def _fetch_guest(
        self,
        search_term: str,
        location: str = "",
        results_wanted: int = 50,
        **kwargs,
    ) -> list[RawJob]:
        """Crawl via the public ``/jobs-guest`` endpoints — no login, no browser.

        Walks the paginated list endpoint (10 cards/page) then issues one detail
        request per job for the full description. Backs off on HTTP 429.
        """
        geo_id = str(kwargs.get("geo_id") or "")
        on_job = kwargs.get("on_job")  # optional per-job heartbeat for the live UI
        sess = requests.Session()
        sess.headers.update(_GUEST_HEADERS)

        jobs: list[RawJob] = []
        seen_ids: set[str] = set()
        start, empty_pages, max_start = 0, 0, max(results_wanted * 2, 100)

        while len(jobs) < results_wanted and start < max_start:
            cards, status = self._guest_list_page(sess, search_term, location, geo_id, start)
            if status == 429:
                logger.warning("LinkedIn guest 429 at start=%d — backing off", start)
                time.sleep(self._guest_delay * 4 + random.uniform(0, 2))
                continue
            if status != 200 or not cards:
                empty_pages += 1
                if empty_pages >= 2:
                    break
                start += _GUEST_PAGE
                continue
            empty_pages = 0
            for card in cards:
                jid = card.get("job_id")
                if not jid or jid in seen_ids:
                    continue
                seen_ids.add(jid)
                card.update(self._guest_detail(sess, jid))
                jobs.append(self._guest_card_to_rawjob(card))
                if self._save_path:
                    self._stream_save(jobs[-1])
                if on_job:
                    try:
                        on_job(len(jobs))
                    except Exception:
                        pass
                if len(jobs) >= results_wanted:
                    break
            start += _GUEST_PAGE
            time.sleep(self._guest_delay + random.uniform(0, 0.8))

        logger.info("LinkedIn guest: %d jobs for '%s'", len(jobs), search_term)
        return jobs

    def _guest_list_page(
        self, sess: requests.Session, query: str, location: str, geo_id: str, start: int
    ) -> tuple[list[dict], int]:
        params = {"keywords": query, "location": location, "start": start}
        if geo_id:
            params["geoId"] = geo_id
        try:
            r = sess.get(_GUEST_LIST_URL, params=params, timeout=20)
        except requests.RequestException as e:
            logger.warning("LinkedIn guest list request failed: %s", e)
            return [], 0
        if r.status_code != 200:
            return [], r.status_code
        return self._parse_guest_cards(r.text), 200

    @staticmethod
    def _parse_guest_cards(html_text: str) -> list[dict]:
        soup = BeautifulSoup(html_text, "html.parser")
        out: list[dict] = []
        for li in soup.select("li"):
            title = li.select_one("h3")
            company = li.select_one("h4")
            if not (title and company):
                continue
            loc = li.select_one(".job-search-card__location")
            link = li.select_one("a.base-card__full-link") or li.select_one("a[href*='/jobs/view/']")
            time_el = li.select_one("time")
            job_id = None
            urn = li.select_one("[data-entity-urn]")
            if urn and urn.get("data-entity-urn"):
                m = re.search(r"(\d+)$", urn["data-entity-urn"])
                job_id = m.group(1) if m else None
            if not job_id and link and link.get("href"):
                m = re.search(r"/jobs/view/.*?-(\d+)", link["href"])
                job_id = m.group(1) if m else None
            out.append({
                "job_id": job_id,
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True),
                "location": loc.get_text(strip=True) if loc else "",
                "url": (link["href"].split("?")[0] if link and link.get("href") else ""),
                "date_posted": (time_el.get("datetime") if time_el else None),
            })
        return out

    def _guest_detail(self, sess: requests.Session, job_id: str) -> dict:
        """Fetch the guest detail fragment for one job → description + the
        top-card extras (company logo/url, seniority, employment type,
        applicant count). Empty dict on failure/429."""
        out: dict = {}
        try:
            r = sess.get(_GUEST_DETAIL_URL.format(job_id=job_id), timeout=20)
        except requests.RequestException:
            return out
        if r.status_code == 429:
            time.sleep(self._guest_delay * 4 + random.uniform(0, 2))
            try:
                r = sess.get(_GUEST_DETAIL_URL.format(job_id=job_id), timeout=20)
            except requests.RequestException:
                return out
        if r.status_code != 200:
            return out

        soup = BeautifulSoup(r.text, "html.parser")
        box = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
        if box:
            out["description"] = box.get_text(" ", strip=True)

        # Company logo — real CDN images live on media.licdn.com (skip ghost
        # placeholders served from static.licdn.com).
        for img in soup.select(".top-card-layout__card img.artdeco-entity-image, img.artdeco-entity-image"):
            url = next((u for u in (img.get("src"), img.get("data-delayed-url"))
                        if u and "media.licdn.com" in u), "")
            if url:
                out["company_logo_url"] = url.strip()
                break

        org = soup.select_one("a.topcard__org-name-link")
        if org and org.get("href"):
            out["company_url"] = org["href"].split("?")[0]

        # Seniority level / Employment type from the job-criteria list.
        for item in soup.select(".description__job-criteria-item"):
            label = item.select_one(".description__job-criteria-subheader")
            value = item.select_one(".description__job-criteria-text")
            if not label or not value:
                continue
            lab, val = label.get_text(strip=True).lower(), value.get_text(strip=True)
            if "employment type" in lab:
                out["job_type"] = val
            elif "seniority level" in lab:
                out["seniority_hint"] = val

        appl = soup.select_one(".num-applicants__caption")
        if appl:
            out["applicant_count"] = appl.get_text(strip=True)
        return out

    @staticmethod
    def _guest_card_to_rawjob(card: dict) -> RawJob:
        date_posted = None
        if card.get("date_posted"):
            try:
                date_posted = datetime.strptime(card["date_posted"], "%Y-%m-%d")
            except ValueError:
                date_posted = None
        url = card.get("url") or (
            f"https://www.linkedin.com/jobs/view/{card['job_id']}" if card.get("job_id") else ""
        )
        return RawJob(
            source="linkedin",
            source_url=url,
            title=card.get("title", ""),
            company=card.get("company", ""),
            location=card.get("location", ""),
            description=card.get("description", ""),
            date_posted=date_posted,
            seniority_hint=card.get("seniority_hint", "") or None,
            company_logo_url=card.get("company_logo_url", ""),
            company_url=card.get("company_url", ""),
            job_type=card.get("job_type", ""),
            applicant_count=card.get("applicant_count", ""),
            extra={"guest": True},
        )

    # ── authenticated mode (Playwright, opt-in) ────────────────────────────────
    def _fetch_authenticated(
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
