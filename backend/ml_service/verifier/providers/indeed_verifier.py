"""Indeed job-status verifier — Indeed mobile GraphQL API.

Indeed gates its public web pages behind Cloudflare: a plain HTTP GET to
``/viewjob`` returns a 403 "additional verification" challenge, and even a
stealth browser gets walled after the first request, so a browser verifier is
unreliable at volume.

But Indeed's mobile app talks to an UNPROTECTED GraphQL endpoint
(``apis.indeed.com/graphql``) authenticated with a public app API key — the
same one the JobSpy crawler uses to crawl Indeed. That API exposes a per-job
``expired`` boolean keyed by the job's ``jk`` (jobkey), so a whole batch can be
verified in one request: no browser, no Cloudflare, milliseconds per job. It
also returns ``employer.dossier.images.squareLogoUrl``, which we backfill into
the company logo for free.

Mapping (per jobkey):
    expired == False  → ACTIVE   (+ company logo backfilled from squareLogoUrl)
    expired == True   → EXPIRED
    jk absent from a SUCCESSFUL response → EXPIRED (Indeed no longer serves it)
    url has no jk                        → UNKNOWN
    API error / non-200 / bad JSON       → UNKNOWN for the whole chunk
                                           (lifecycle backs off and retries)
"""

from __future__ import annotations

import logging
import re

import requests

from ml_service.verifier.base import JobStatus, JobStatusVerifier, VerifyResult

logger = logging.getLogger(__name__)

_API_URL = "https://apis.indeed.com/graphql"
# Public Indeed iOS-app API key + headers (mirrors jobspy's IndeedScraper). If
# Indeed rotates the key the crawler breaks too; update both together.
_API_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
    "accept": "application/json",
    "indeed-locale": "en-US",
    "indeed-co": "US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

_QUERY_TMPL = (
    "query{ jobData(input:{jobKeys:[%s]}){ results{ job{ "
    "key expired employer{ dossier{ images{ squareLogoUrl } } } "
    "} } } }"
)

_JK_RE = re.compile(r"[?&]jk=([0-9a-fA-F]+)")
_DEFAULT_CHUNK = 25
_DEFAULT_TIMEOUT = 15.0


def _extract_jk(url: str) -> str:
    m = _JK_RE.search(url or "")
    return m.group(1).lower() if m else ""


class IndeedVerifier(JobStatusVerifier):
    _NAME = "indeed"

    def __init__(self, *, chunk_size: int = _DEFAULT_CHUNK,
                 timeout: float = _DEFAULT_TIMEOUT, **_ignored) -> None:
        # **_ignored swallows require_li_at / headless passed by the shared
        # command — the API path needs neither a login nor a browser.
        self._chunk = max(1, int(chunk_size))
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._NAME

    def supports(self, url: str) -> bool:
        try:
            return "indeed.com" in url
        except Exception:
            return False

    def verify(self, url: str) -> VerifyResult:
        return self.verify_batch([url])[0]

    def verify_batch(self, urls: list[str], *, progress_callback=None) -> list[VerifyResult]:
        if not urls:
            return []
        n = len(urls)
        results: list[VerifyResult | None] = [None] * n

        # Group input indices by jobkey; urls without a jk resolve immediately.
        idx_by_jk: dict[str, list[int]] = {}
        order: list[str] = []
        for i, url in enumerate(urls):
            jk = _extract_jk(url)
            if not jk:
                results[i] = VerifyResult(JobStatus.UNKNOWN, reason="no jk in url", final_url=url)
            else:
                if jk not in idx_by_jk:
                    order.append(jk)
                idx_by_jk.setdefault(jk, []).append(i)

        # Query the API in chunks; fill results by jobkey.
        for start in range(0, len(order), self._chunk):
            chunk = order[start:start + self._chunk]
            verdicts = self._query_chunk(chunk)
            for jk in chunk:
                status, reason, logo = verdicts[jk]
                for i in idx_by_jk[jk]:
                    results[i] = VerifyResult(
                        status, reason=reason, final_url=urls[i], company_logo=logo,
                    )

        # Emit progress in input order (the API is fast; ordered ticks keep the
        # service's job_id mapping and the dashboard's counter correct).
        if progress_callback is not None:
            for i in range(n):
                progress_callback(i, n, urls[i], results[i])

        return [r for r in results]  # type: ignore[return-value]

    # ── Internals ─────────────────────────────────────────────────────────
    def _query_chunk(self, jks: list[str]) -> dict:
        """Return ``{jk: (JobStatus, reason, logo)}`` for one chunk of jobkeys."""
        keys = '"' + '","'.join(jks) + '"'
        query = _QUERY_TMPL % keys
        try:
            resp = requests.post(
                _API_URL, headers=_API_HEADERS, json={"query": query}, timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.warning("Indeed API request failed: %r", exc)
            return {jk: (JobStatus.UNKNOWN, f"api request failed: {exc!r}", "") for jk in jks}
        if resp.status_code != 200:
            logger.warning("Indeed API non-200: %s", resp.status_code)
            return {jk: (JobStatus.UNKNOWN, f"api HTTP {resp.status_code}", "") for jk in jks}
        try:
            rows = resp.json()["data"]["jobData"]["results"]
        except Exception:
            return {jk: (JobStatus.UNKNOWN, "api bad JSON", "") for jk in jks}

        out: dict = {}
        for row in rows:
            job = row.get("job") or {}
            key = (job.get("key") or "").lower()
            if not key:
                continue
            expired = bool(job.get("expired"))
            if expired:
                out[key] = (JobStatus.EXPIRED, "api: expired=true", "")
            else:
                logo = (
                    ((job.get("employer") or {}).get("dossier") or {})
                    .get("images") or {}
                ).get("squareLogoUrl") or ""
                out[key] = (JobStatus.ACTIVE, "api: expired=false", logo)

        # A successful response that omits a jobkey means Indeed no longer
        # serves that listing → treat as removed/expired.
        for jk in jks:
            out.setdefault(jk, (JobStatus.EXPIRED, "api: not returned (removed)", ""))
        return out
