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
    # Lifecycle outcomes from the bundled verify pass (when enabled).
    verify_active: int = 0
    verify_expired: int = 0
    verify_unknown: int = 0
    verify_session_expired: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False

    @property
    def wall_clock_seconds(self) -> float:
        if not (self.started_at and self.finished_at):
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


class DateBackfillService:
    """Orchestrator for the `extract_job_dates` command.

    When ``verifier`` is provided, each page visit ALSO runs a lifecycle
    check (verify + extract date in one navigation). The same Playwright
    page is inspected twice (cheap DOM scans), and both outcomes are
    written: date_posted via apply_date, lifecycle via apply_result.
    """

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
        verifier: Callable[..., VerifyResult] | None = None,
    ) -> None:
        self._extractor = extractor
        self._repository = repository
        self._browser_factory = browser_factory
        self._clock = clock
        self._url_supports = url_supports or (lambda url: True)
        self._delay = per_url_delay_s
        self._jitter = per_url_jitter_s
        self._verifier = verifier   # fn(page) -> VerifyResult, or None

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
        outcomes: list[tuple[int, DateExtractionResult | None, VerifyResult | None, bool]] = []
        # tuple: (job_id, date_result_or_None, verify_result_or_None, errored)
        total = len(supported)
        with self._browser_factory() as (page, ctx):
            for i, (job_id, url) in enumerate(supported):
                if i > 0:
                    time.sleep(self._delay + random.uniform(0.0, self._jitter))

                # If the page/browser is gone (operator hit Stop, OOM,
                # crash) bail the whole batch instead of producing N copies
                # of TargetClosedError.
                if page.is_closed():
                    logger.warning("page closed mid-batch at %d/%d — aborting", i + 1, total)
                    break

                # Per-URL try/except — FR-015 isolation.
                try:
                    self._navigate(page, url)
                    if not _ctx_has_li_at(ctx):
                        logger.debug(
                            "li_at not present after URL %d/%d — continuing in guest mode",
                            i + 1, total,
                        )

                    date_result = self._extractor(page, now=self._clock())
                    verify_result = self._verifier(page) if self._verifier else None
                    outcomes.append((job_id, date_result, verify_result, False))
                    self._log_progress(i + 1, total, job_id, url, date_result, verify_result, errored=False)
                except Exception as exc:  # noqa: BLE001
                    if page.is_closed():
                        logger.warning("page closed during URL %d/%d — aborting", i + 1, total)
                        break
                    logger.exception("extract failed for job %s", job_id)
                    outcomes.append((job_id, None, None, True))
                    self._log_progress(i + 1, total, job_id, url, None, None, errored=True, exc=exc)

        # Browser context closed — safe to hit the ORM now.
        for job_id, date_result, verify_result, errored in outcomes:
            report.total_examined += 1
            if errored:
                report.error_count += 1
                if not dry_run:
                    self._apply_error(job_id)
                continue
            self._apply_outcome(job_id, date_result, report=report, dry_run=dry_run)
            if verify_result is not None:
                self._apply_verify(job_id, verify_result, report=report, dry_run=dry_run)

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

    def _apply_verify(
        self,
        job_id: int,
        result: VerifyResult,
        *,
        report: BackfillReport,
        dry_run: bool,
    ) -> None:
        """Apply a lifecycle verify outcome alongside the date result.

        Skips writing for EXPIRED if _apply_outcome already wrote that
        (expired-redirect path) — avoids double increment + redundant
        apply_result call.
        """
        if result.status is JobStatus.ACTIVE:
            report.verify_active += 1
        elif result.status is JobStatus.EXPIRED:
            report.verify_expired += 1
        elif result.status is JobStatus.UNKNOWN:
            report.verify_unknown += 1
        elif result.status is JobStatus.SESSION_EXPIRED:
            report.verify_session_expired += 1
        else:
            # ERROR from verifier; subsumed by date error path; skip apply.
            return

        if dry_run:
            return
        # SESSION_EXPIRED is a no-op write per spec 001 — operator alert only.
        if result.status is JobStatus.SESSION_EXPIRED:
            return
        self._repository.apply_result(job_id, result, now=self._clock())

    @staticmethod
    def _log_progress(
        i: int,
        total: int,
        job_id: int,
        url: str,
        date_result: DateExtractionResult | None,
        verify_result: VerifyResult | None = None,
        *,
        errored: bool,
        exc: Exception | None = None,
    ) -> None:
        """Print a single line per URL — flushed immediately for live observation.

        Format:
            [3/200] job=11514 OK date=2026-05-08 src=relative-text status=ACTIVE
            [4/200] job=11520 EXPIRED                              status=EXPIRED
            [5/200] job=11519 NONE                                 status=UNKNOWN
            [6/200] job=11517 ERR TimeoutError
        """
        prefix = f"[{i:>3d}/{total:<3d}] job={job_id:<6d}"
        if errored:
            tag = f"ERR    {type(exc).__name__ if exc else 'Exception'}"
        elif date_result is None:
            tag = "NONE"
        elif date_result.source == "expired-redirect":
            tag = "EXPIRED"
        elif date_result.date is not None:
            tag = f"OK     date={date_result.date.date().isoformat()} src={date_result.source}"
        else:
            tag = f"NONE   src={date_result.source}"

        if verify_result is not None and not errored:
            tag = f"{tag:<50s} status={verify_result.status.value.upper()}"

        print(f"{prefix}  {tag:<70s}  url={url[:80]}", flush=True)


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
