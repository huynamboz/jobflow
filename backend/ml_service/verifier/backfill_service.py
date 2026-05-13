"""Date-backfill orchestrator.

Mirrors :class:`ml_service.verifier.service.StatusCheckService` but writes
``Job.date_posted`` (and `lifecycle='expired'` for redirected pages)
instead of running the lifecycle state machine.

Constructor injection — pass an extractor function, a repository, a clock,
and a browser-pool factory. Service is stateless and re-entrant.

Spec: 002-job-date-posted-extraction (US2).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Protocol

from ml_service.verifier.auth_guard import has_li_at
from ml_service.verifier.base import JobStatus, VerifyResult
from ml_service.verifier.date_extractor import (
    DateExtractionResult,
    extract_date_posted,
)

logger = logging.getLogger(__name__)


_MAX_BACKOFF_HOURS = 24 * 7
_DEFAULT_DELAY_S = 3.0
_DEFAULT_JITTER_S = 1.5


class BackfillRepository(Protocol):
    def find_to_backfill_dates(self, *, platform: str, batch: int, now: datetime) -> list[dict]: ...
    def apply_date(self, job_id: int, date: datetime, *, now: datetime) -> None: ...
    def apply_result(self, job_id: int, result: VerifyResult, *, now: datetime) -> None: ...


@dataclass
class BackfillReport:
    platform: str
    batch_size_requested: int
    total_examined: int = 0
    populated_count: int = 0
    expired_marked_count: int = 0
    none_count: int = 0
    error_count: int = 0
    session_expired_count: int = 0
    skipped_unsupported_url: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False

    @property
    def wall_clock_seconds(self) -> float:
        if not (self.started_at and self.finished_at):
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


class DateBackfillService:
    """Orchestrator for the `extract_job_dates` command."""

    def __init__(
        self,
        *,
        extractor: Callable[..., DateExtractionResult] = extract_date_posted,
        repository: BackfillRepository,
        browser_factory: Callable,                 # () -> contextmanager yielding (page, ctx)
        clock: Callable[[], datetime],
        url_supports: Callable[[str], bool] | None = None,
        per_url_delay_s: float = _DEFAULT_DELAY_S,
        per_url_jitter_s: float = _DEFAULT_JITTER_S,
    ) -> None:
        self._extractor = extractor
        self._repository = repository
        self._browser_factory = browser_factory
        self._clock = clock
        self._url_supports = url_supports or (lambda url: True)
        self._delay = per_url_delay_s
        self._jitter = per_url_jitter_s

    # ── Public ───────────────────────────────────────────────────────────

    def run(
        self,
        *,
        platform: str,
        batch: int,
        dry_run: bool = False,
    ) -> BackfillReport:
        if batch < 1:
            raise ValueError("batch must be >= 1")

        started = self._clock()
        report = BackfillReport(
            platform=platform,
            batch_size_requested=batch,
            started_at=started,
            dry_run=dry_run,
        )

        # Select candidates first — bail early if nothing to do.
        try:
            candidates = self._repository.find_to_backfill_dates(
                platform=platform, batch=batch, now=started
            )
        except Exception:
            logger.exception("find_to_backfill_dates failed; aborting batch")
            report.finished_at = self._clock()
            return report

        if not candidates:
            report.finished_at = self._clock()
            return report

        # Filter unsupported URLs.
        supported: list[tuple[int, str]] = []
        for row in candidates:
            url = (row.get("source_url") or "").strip()
            if not url or not self._url_supports(url):
                report.skipped_unsupported_url += 1
                continue
            supported.append((int(row["id"]), url))

        if not supported:
            report.finished_at = self._clock()
            return report

        # Open browser context and walk URLs. Collect outcomes in memory;
        # apply DB writes only AFTER the browser context exits — Playwright's
        # sync_playwright spins an event loop that makes Django ORM calls
        # raise SynchronousOnlyOperation if invoked while the context is
        # still open.
        outcomes: list[tuple[int, DateExtractionResult | None, bool]] = []
        # bool flag: True iff the URL raised an exception during extraction
        with self._browser_factory() as (page, ctx):
            for i, (job_id, url) in enumerate(supported):
                if i > 0:
                    time.sleep(self._delay + random.uniform(0.0, self._jitter))

                # Per-URL try/except — FR-015 isolation.
                try:
                    self._navigate(page, url)
                    # Note: do not bail on li_at loss — LinkedIn often
                    # downgrades to guest layout after the first request, but
                    # the page still loads with usable content. The
                    # extractor's expired-redirect URL check and guest-layout
                    # selectors handle both cases.
                    if not _ctx_has_li_at(ctx):
                        logger.debug(
                            "li_at not present after URL %d/%d — continuing in guest mode",
                            i + 1, len(supported),
                        )

                    result = self._extractor(page, now=self._clock())
                    outcomes.append((job_id, result, False))
                except Exception:  # noqa: BLE001
                    logger.exception("extract failed for job %s", job_id)
                    outcomes.append((job_id, None, True))

        # Browser context closed — safe to hit the ORM now.
        for job_id, result, errored in outcomes:
            report.total_examined += 1
            if errored:
                report.error_count += 1
                if not dry_run:
                    self._apply_error(job_id)
                continue
            self._apply_outcome(job_id, result, report=report, dry_run=dry_run)

        report.finished_at = self._clock()
        return report

    # ── Internals ────────────────────────────────────────────────────────

    def _navigate(self, page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)

    def _apply_outcome(
        self,
        job_id: int,
        result: DateExtractionResult,
        *,
        report: BackfillReport,
        dry_run: bool,
    ) -> None:
        if result.source == "expired-redirect":
            report.expired_marked_count += 1
            if not dry_run:
                self._repository.apply_result(
                    job_id,
                    VerifyResult(JobStatus.EXPIRED, reason="extractor saw expired_jd_redirect"),
                    now=self._clock(),
                )
        elif result.date is not None:
            report.populated_count += 1
            if not dry_run:
                self._repository.apply_date(job_id, result.date, now=self._clock())
        else:
            # source == "none"
            report.none_count += 1
            if not dry_run:
                self._repository.apply_result(
                    job_id,
                    VerifyResult(JobStatus.UNKNOWN, reason="no date source matched"),
                    now=self._clock(),
                )

    def _apply_error(self, job_id: int) -> None:
        self._repository.apply_result(
            job_id,
            VerifyResult(JobStatus.ERROR, reason="exception during date extraction"),
            now=self._clock(),
        )


def _ctx_has_li_at(ctx) -> bool:
    """Cheap mid-batch session check. ctx can be a Playwright BrowserContext
    or a stub exposing .cookies(). Returns False on any failure (safe).
    """
    if ctx is None:
        return True  # tests can omit ctx and accept that auth-check is no-op
    try:
        cookies = ctx.cookies()
    except Exception:
        return False
    return has_li_at({"cookies": cookies})
