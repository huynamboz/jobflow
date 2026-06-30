"""HTTP-presence verifier base — for job boards whose removed listings 404 (or
redirect away from the job URL). No browser, no auth: a plain GET tells us if the
posting is still live. Concrete providers (RemoteOK, Remotive) subclass this in
``providers/`` so the factory auto-discovers them.

Classification:
    HTTP 404 / 410                      → EXPIRED
    redirect off the job URL (id gone)  → EXPIRED
    page still on the job URL (200)     → ACTIVE  (unless an expired marker shows)
    network error / odd status          → ERROR / UNKNOWN  (no-op, never mislabels)
"""

from __future__ import annotations

import logging
import re
import time

import requests

from ml_service.verifier.base import JobStatus, JobStatusVerifier, VerifyResult

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (compatible; JobFlowVerifier/1.0)"}
_ID_RE = re.compile(r"-(\d+)/?$")


class HttpPresenceVerifier(JobStatusVerifier):
    # Subclasses set these:
    _NAME: str = ""
    _URL_PATTERNS: tuple[str, ...] = ()
    _EXPIRED_MARKERS: tuple[str, ...] = ()  # lowercased text substrings → EXPIRED
    # Optional company-logo backfill from the live page (e.g. RemoteOK lazy-loads
    # the real logo URL into a data-attr). Empty selector → no logo extraction.
    _LOGO_SELECTOR: str = ""
    _LOGO_ATTR: str = "data-src"

    def __init__(self, *, delay_s: float = 0.5, **_ignored) -> None:
        # **_ignored swallows browser-only kwargs (require_li_at/headless).
        self._delay_s = delay_s

    @property
    def name(self) -> str:
        return self._NAME

    def supports(self, url: str) -> bool:
        try:
            low = (url or "").lower()
            return any(p in low for p in self._URL_PATTERNS)
        except Exception:
            return False

    def verify(self, url: str) -> VerifyResult:
        return self.verify_batch([url])[0]

    def verify_batch(self, urls: list[str], *, progress_callback=None) -> list[VerifyResult]:
        results: list[VerifyResult] = []
        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(self._delay_s)
            result = self._check(url)
            results.append(result)
            if progress_callback is not None:
                progress_callback(i, len(urls), url, result)
        return results

    def _check(self, url: str) -> VerifyResult:
        try:
            resp = requests.get(url, headers=_UA, timeout=15, allow_redirects=True)
        except requests.RequestException as e:
            return VerifyResult(JobStatus.ERROR, reason=f"request failed: {e!r}", final_url=url)

        final_url = str(getattr(resp, "url", "") or url)
        if resp.status_code in (404, 410):
            return VerifyResult(JobStatus.EXPIRED, reason=f"HTTP {resp.status_code}", final_url=final_url)
        if resp.status_code != 200:
            return VerifyResult(JobStatus.UNKNOWN, reason=f"HTTP {resp.status_code}", final_url=final_url)

        # Redirected off the job page (the job id no longer in the final URL) →
        # the listing was pulled and the board bounced us to a search/home page.
        m = _ID_RE.search(url)
        job_id = m.group(1) if m else ""
        if job_id and job_id not in final_url:
            return VerifyResult(JobStatus.EXPIRED, reason="redirected off job URL", final_url=final_url)

        body = resp.text or ""
        text = body[:200_000].lower()
        for marker in self._EXPIRED_MARKERS:
            if marker in text:
                return VerifyResult(JobStatus.EXPIRED, reason=f"marker: {marker}", final_url=final_url)

        return VerifyResult(
            JobStatus.ACTIVE, reason="live (HTTP 200)", final_url=final_url,
            company_logo=self._extract_logo(body),
        )

    def _extract_logo(self, html: str) -> str:
        """Pull a company logo URL off the live page (subclass-configured
        selector + attr). Returns "" if not configured or not a real image URL."""
        if not self._LOGO_SELECTOR:
            return ""
        try:
            from bs4 import BeautifulSoup
            el = BeautifulSoup(html, "html.parser").select_one(self._LOGO_SELECTOR)
            if not el:
                return ""
            url = (el.get(self._LOGO_ATTR) or el.get("src") or "").strip()
            if url.startswith("http") and "pixel.gif" not in url:
                return url
        except Exception:
            pass
        return ""
