"""LinkedIn job-status verifier.

Reuses the saved auth state from ``ml_service.crawler.providers.linkedin_auth``.
One browser context per batch — see ``browser_pool.open_browser_page``.

Detection priority (research.md decision 5, extended after live debugging):
    1. Final URL matches ``auth_check.expired_url_patterns`` → SESSION_EXPIRED
    2. Final URL matches ``expired_url_patterns`` (e.g., LinkedIn's
       ``trk=expired_jd_redirect``) → EXPIRED
    3. Any ``expired_markers`` selector matches → EXPIRED
    4. Any ``active_markers`` selector matches → ACTIVE
    5. Otherwise → UNKNOWN
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

from ml_service.crawler.providers.linkedin_auth import load_state_path
from ml_service.verifier.base import JobStatus, JobStatusVerifier, VerifyResult
from ml_service.verifier.browser_pool import (
    AuthStateMissingError,
    cookies_have_li_at,
    open_browser_page,
)

logger = logging.getLogger(__name__)

_SELECTORS_PATH = Path(__file__).parent.parent / "selectors" / "linkedin.json"
_LINKEDIN_JOB_ID_RE = re.compile(r"linkedin\.com/jobs/view/(\d+)")
_DEFAULT_DELAY_S = 3.0
_DEFAULT_JITTER_S = 1.5


def linkedin_clean_url(url: str) -> str:
    """Canonicalize a LinkedIn job URL to ``https://www.linkedin.com/jobs/view/<id>/``.

    Returns the original URL if the LinkedIn job-id pattern is not present.
    """
    if not url:
        return url
    m = _LINKEDIN_JOB_ID_RE.search(url)
    if not m:
        return url
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"


def _load_selectors() -> dict:
    with _SELECTORS_PATH.open() as f:
        return json.load(f)


class LinkedInVerifier(JobStatusVerifier):
    _NAME = "linkedin"
    _URL_PATTERNS = ("linkedin.com/jobs/",)

    def __init__(
        self,
        *,
        delay_s: float = _DEFAULT_DELAY_S,
        jitter_s: float = _DEFAULT_JITTER_S,
        headless: bool = True,
        storage_state_path: str | None = None,
        selectors: dict | None = None,
    ) -> None:
        self._delay_s = delay_s
        self._jitter_s = jitter_s
        self._headless = headless
        self._storage_state_path = storage_state_path
        self._selectors = selectors  # lazy-loaded on first use

    @property
    def name(self) -> str:
        return self._NAME

    def supports(self, url: str) -> bool:
        try:
            return any(p in url for p in self._URL_PATTERNS)
        except Exception:
            return False

    def verify(self, url: str) -> VerifyResult:
        return self.verify_batch([url])[0]

    def verify_batch(self, urls: list[str]) -> list[VerifyResult]:
        if not urls:
            return []

        state_path = self._storage_state_path or load_state_path()
        if not state_path:
            msg = (
                "LinkedIn auth state not found. Run: "
                "python -m ml_service.crawler.providers.linkedin_auth"
            )
            return [VerifyResult(JobStatus.SESSION_EXPIRED, reason=msg) for _ in urls]

        selectors = self._selectors or _load_selectors()
        results: list[VerifyResult] = []

        try:
            with open_browser_page(state_path, headless=self._headless) as (page, ctx):
                for i, url in enumerate(urls):
                    if i > 0:
                        time.sleep(self._delay_s + random.uniform(0.0, self._jitter_s))
                    result = self._check_one(page, linkedin_clean_url(url), selectors)
                    results.append(result)
                    # Note: LinkedIn often invalidates li_at after the first
                    # request from a re-opened browser instance, but continues
                    # to serve the guest layout. We do NOT bail on li_at loss
                    # — the per-URL detection priority (login URL pattern →
                    # expired URL pattern → expired markers → active markers)
                    # handles both authenticated and guest layouts. Only a
                    # final_url matching ``auth_check.expired_url_patterns``
                    # is treated as a true SESSION_EXPIRED outcome.
                    if not cookies_have_li_at(ctx):
                        logger.debug(
                            "li_at not present after URL %d/%d — continuing in guest mode",
                            i + 1, len(urls),
                        )
        except AuthStateMissingError as exc:
            # Auth state file invalid at start — every URL is session_expired.
            return [
                VerifyResult(JobStatus.SESSION_EXPIRED, reason=str(exc))
                for _ in urls
            ]
        except Exception as exc:
            logger.exception("LinkedIn browser session failed mid-batch")
            while len(results) < len(urls):
                results.append(
                    VerifyResult(JobStatus.ERROR, reason=f"browser failure: {exc!r}")
                )

        return results

    # ── Internals ────────────────────────────────────────────────────────

    def _check_one(self, page, url: str, selectors: dict) -> VerifyResult:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:  # network, timeout, etc.
            return VerifyResult(
                JobStatus.ERROR, reason=f"goto failed: {exc!r}", final_url=url
            )

        final_url = page.url or url

        # 1. Session-expired check (highest priority — bad sessions corrupt the rest).
        session_patterns: list[str] = selectors.get("auth_check", {}).get(
            "expired_url_patterns", []
        )
        if any(p in final_url for p in session_patterns):
            return VerifyResult(
                JobStatus.SESSION_EXPIRED,
                reason=f"final_url matched session pattern: {final_url}",
                final_url=final_url,
            )

        # 2. Expired-by-URL check — LinkedIn redirects deleted job IDs to a
        #    search results page with trk=expired_jd_redirect. The page would
        #    otherwise pass active-marker checks because it shows similar jobs.
        expired_url_patterns: list[str] = selectors.get("expired_url_patterns", [])
        if any(p in final_url for p in expired_url_patterns):
            return VerifyResult(
                JobStatus.EXPIRED,
                reason=f"final_url matched expired pattern: {final_url}",
                final_url=final_url,
            )

        # 3. Expired markers.
        for sel in selectors.get("expired_markers", []):
            try:
                if page.locator(sel).first.is_visible(timeout=500):
                    return VerifyResult(
                        JobStatus.EXPIRED,
                        reason=f"matched expired marker: {sel}",
                        final_url=final_url,
                    )
            except Exception:
                continue

        # 4. Active markers.
        for sel in selectors.get("active_markers", []):
            try:
                if page.locator(sel).first.is_visible(timeout=500):
                    return VerifyResult(
                        JobStatus.ACTIVE,
                        reason=f"matched active marker: {sel}",
                        final_url=final_url,
                    )
            except Exception:
                continue

        # 5. Ambiguous.
        return VerifyResult(
            JobStatus.UNKNOWN,
            reason="no markers matched",
            final_url=final_url,
        )
