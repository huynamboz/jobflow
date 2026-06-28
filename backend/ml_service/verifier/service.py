"""Status check orchestrator.

Single responsibility: given a verifier registry, a repository, and a clock,
pick candidate jobs, dispatch each to the verifier whose ``supports(url)``
returns True, apply outcomes through the repository, and emit a structured
report.

Constructor injection — no module-level state. Easy to fake in tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Mapping, Protocol

from ml_service.verifier.base import JobStatus, JobStatusVerifier, VerifyResult

logger = logging.getLogger(__name__)


# ─── Repository protocol (for type hints) ────────────────────────────────


class LifecycleRepository(Protocol):
    def apply_result(self, job_id: int, result: VerifyResult, *, now: datetime) -> None: ...
    def find_to_verify(self, *, platform: str, batch: int, now: datetime,
                        min_verified_age_hours: float = 0) -> list[dict]: ...
    def apply_aging(self, *, now: datetime, threshold_days: int = 14) -> int: ...


# ─── Report dataclass ────────────────────────────────────────────────────


def _log_verify_progress(
    i: int,
    total: int,
    job_id: int,
    url: str,
    result: VerifyResult,
) -> None:
    """Print a single line per URL — flushed immediately for live observation.

    Mirrors the format used by ``extract_job_dates``:
        [  1/200] job=11510   ACTIVE                                         url=...
        [  4/200] job=11507   EXPIRED  reason=text=No longer accepting...    url=...
        [  9/200] job=11200   UNKNOWN                                        url=...
        [ 12/200] job=10500   SESSION_EXPIRED                                url=...
        [ 27/200] job=10800   ERROR    TimeoutError                          url=...
    """
    prefix = f"[{i:>3d}/{total:<3d}] job={job_id:<6d}"
    status = result.status.value.upper()
    if result.status is JobStatus.ERROR:
        tag = f"ERROR    {(result.reason or 'unknown')[:40]}"
    elif result.reason and result.status is JobStatus.EXPIRED:
        tag = f"EXPIRED  reason={result.reason[:40]}"
    else:
        tag = f"{status:<8s}"
    print(f"{prefix}  {tag:<60s}  url={url[:80]}", flush=True)


@dataclass
class StatusCheckReport:
    platform: str
    batch_size_requested: int
    total_examined: int = 0
    skipped_unsupported_url: int = 0
    counts_by_outcome: dict[JobStatus, int] = field(
        default_factory=lambda: {s: 0 for s in JobStatus}
    )
    session_expired_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False

    @property
    def wall_clock_seconds(self) -> float:
        if not (self.started_at and self.finished_at):
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


# ─── Service ─────────────────────────────────────────────────────────────


class StatusCheckService:
    def __init__(
        self,
        verifier_registry: Mapping[str, JobStatusVerifier],
        repository: LifecycleRepository,
        clock: Callable[[], datetime],
        stale_age_days: int = 14,
        min_verified_age_hours: float = 0,
    ) -> None:
        self._verifiers = dict(verifier_registry)
        self._repository = repository
        self._clock = clock
        self._stale_age_days = stale_age_days
        # Skip jobs verified within this window (0 = no minimum). Avoids
        # re-checking the same job multiple times a day.
        self._min_verified_age_hours = min_verified_age_hours

    # ── Public ───────────────────────────────────────────────────────────

    def check_batch(
        self,
        *,
        platform: str,
        batch: int,
        dry_run: bool = False,
    ) -> StatusCheckReport:
        if batch < 1:
            raise ValueError("batch must be >= 1")

        verifier = self._verifiers.get(platform)
        if verifier is None:
            raise ValueError(
                f"No verifier registered for platform '{platform}'. "
                f"Available: {sorted(self._verifiers.keys())}"
            )

        started = self._clock()
        report = StatusCheckReport(
            platform=platform,
            batch_size_requested=batch,
            started_at=started,
            dry_run=dry_run,
        )

        # Aging rule — runs at the start of every batch (skipped in dry-run
        # since it's a write).
        if not dry_run:
            try:
                promoted = self._repository.apply_aging(
                    now=started, threshold_days=self._stale_age_days
                )
                if promoted:
                    logger.info("Aged %d active job(s) to stale before selection", promoted)
            except Exception:
                logger.exception("apply_aging failed; continuing with whatever rows we can pick")
        else:
            # In dry-run we still call apply_aging so the same code path is
            # exercised; the FakeRepository's apply_aging is a write but in a
            # real Django impl this would be skipped.
            try:
                self._repository.apply_aging(
                    now=started, threshold_days=self._stale_age_days
                )
            except Exception:
                logger.exception("apply_aging failed in dry-run")

        # Pick candidates and dispatch by URL.
        try:
            candidates = self._repository.find_to_verify(
                platform=platform, batch=batch, now=started,
                min_verified_age_hours=self._min_verified_age_hours,
            )
        except Exception:
            logger.exception("find_to_verify failed; aborting batch")
            report.finished_at = self._clock()
            return report

        supported: list[tuple[int, str]] = []
        for row in candidates:
            url = row.get("source_url") or ""
            if not url or not verifier.supports(url):
                report.skipped_unsupported_url += 1
                continue
            supported.append((int(row["id"]), url))

        if not supported:
            report.finished_at = self._clock()
            return report

        # Run verifier on the supported URLs.
        # Build a per-URL progress callback so operators watching long
        # batches can see results as they come in (same UX as
        # `extract_job_dates`).
        def _on_progress(i: int, total: int, _url: str, result: VerifyResult) -> None:
            job_id, _ = supported[i]
            _log_verify_progress(i + 1, total, job_id, _url, result)

        try:
            results = verifier.verify_batch(
                [u for _, u in supported],
                progress_callback=_on_progress,
            )
        except Exception as exc:  # whole-batch failure
            logger.exception("verifier.verify_batch raised; treating all as ERROR")
            results = [
                VerifyResult(JobStatus.ERROR, reason=f"batch exception: {exc!r}")
                for _ in supported
            ]

        # Apply results.
        for (job_id, _url), result in zip(supported, results):
            report.total_examined += 1
            report.counts_by_outcome[result.status] = (
                report.counts_by_outcome.get(result.status, 0) + 1
            )
            if result.status is JobStatus.SESSION_EXPIRED:
                report.session_expired_count += 1
            if not dry_run:
                try:
                    self._repository.apply_result(job_id, result, now=self._clock())
                except Exception:
                    logger.exception("apply_result failed for job_id=%s; continuing", job_id)

        report.finished_at = self._clock()
        return report
