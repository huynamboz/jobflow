"""Freelancer.com job-status verifier — via the public Projects API.

No browser, no auth, no account risk: looks the project up by its seo-url and
reads the authoritative ``status`` field. Bidding-closed / awarded / frozen
projects = EXPIRED; ``active`` = ACTIVE. Ambiguous lookups stay UNKNOWN (a no-op
in the lifecycle repo) so an active job is never mislabeled.
"""

from __future__ import annotations

import logging
import re
import time

import requests

from ml_service.verifier.base import JobStatus, JobStatusVerifier, VerifyResult

logger = logging.getLogger(__name__)

_API = "https://www.freelancer.com/api/projects/0.1/projects/"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; JobFlowVerifier/1.0)"}
_SEO_RE = re.compile(r"/projects/(.+?)/?$", re.IGNORECASE)

# Freelancer project statuses → lifecycle. "active" is the only live one.
_EXPIRED_STATUSES = {"closed", "complete", "frozen", "rejected", "cancelled", "canceled"}
_ACTIVE_STATUSES = {"active"}


class FreelancerVerifier(JobStatusVerifier):
    _NAME = "freelancer"
    _URL_PATTERNS = ("freelancer.com/projects/",)

    def __init__(self, *, delay_s: float = 0.4, **_ignored) -> None:
        # **_ignored swallows browser-only kwargs (require_li_at/headless) the
        # generic command passes — this verifier is pure HTTP.
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
        m = _SEO_RE.search(url or "")
        seo = m.group(1) if m else ""
        if not seo:
            return VerifyResult(JobStatus.UNKNOWN, reason="no seo-url in URL", final_url=url)
        try:
            resp = requests.get(
                _API, params={"seo_urls[]": seo, "compact": "true"}, headers=_UA, timeout=15
            )
        except requests.RequestException as e:
            return VerifyResult(JobStatus.ERROR, reason=f"request failed: {e!r}", final_url=url)

        if resp.status_code != 200:
            return VerifyResult(JobStatus.UNKNOWN, reason=f"HTTP {resp.status_code}", final_url=url)
        try:
            projects = (resp.json().get("result") or {}).get("projects") or []
        except ValueError:
            return VerifyResult(JobStatus.UNKNOWN, reason="bad JSON", final_url=url)

        if not projects:
            # API doesn't index this seo-url anymore — treat as gone, but only
            # softly: UNKNOWN (no-op) avoids killing a still-active project that
            # the seo lookup simply failed to resolve.
            return VerifyResult(JobStatus.UNKNOWN, reason="not found via API", final_url=url)

        status = str(projects[0].get("status") or "").lower()
        if status in _EXPIRED_STATUSES:
            return VerifyResult(JobStatus.EXPIRED, reason=f"status={status}", final_url=url)
        if status in _ACTIVE_STATUSES:
            return VerifyResult(JobStatus.ACTIVE, reason=f"status={status}", final_url=url)
        return VerifyResult(JobStatus.UNKNOWN, reason=f"status={status!r}", final_url=url)
