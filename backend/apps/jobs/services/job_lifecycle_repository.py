"""Repository for job lifecycle reads/writes used by the verifier service.

The service depends on the :class:`JobLifecycleRepository` ABC so tests can
substitute an in-memory fake. The Django implementation here is a thin
ORM adapter — no logic, all decisions live in
:class:`ml_service.verifier.service.StatusCheckService`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from ml_service.verifier.base import JobStatus, VerifyResult

logger = logging.getLogger(__name__)


_MAX_BACKOFF_HOURS = 24 * 7  # 7 days


def _compute_backoff_hours(attempts: int) -> int:
    """Exponential backoff in hours: ``min(2**attempts, 7d)``."""
    return min(2 ** max(1, attempts), _MAX_BACKOFF_HOURS)


class JobLifecycleRepository(ABC):
    @abstractmethod
    def find_to_verify(
        self, *, platform: str, batch: int, now: datetime
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def apply_result(
        self, job_id: int, result: VerifyResult, *, now: datetime
    ) -> None: ...

    @abstractmethod
    def apply_aging(self, *, now: datetime, threshold_days: int = 14) -> int: ...


class DjangoJobLifecycleRepository(JobLifecycleRepository):
    """ORM-backed implementation. Imports Django models lazily so the module
    can be imported without Django being initialised (matters for tests).
    """

    def find_to_verify(
        self, *, platform: str, batch: int, now: datetime
    ) -> list[dict[str, Any]]:
        from django.db.models import Q
        from apps.jobs.models import Job

        qs = (
            Job.objects
            .filter(platform__name=platform)
            .filter(lifecycle__in=[Job.LIFECYCLE_ACTIVE, Job.LIFECYCLE_STALE])
            .filter(Q(verification_backoff_until__isnull=True) | Q(verification_backoff_until__lte=now))
            .extra(select={"_lifecycle_order": "CASE WHEN lifecycle='stale' THEN 0 ELSE 1 END"})
            .extra(order_by=["_lifecycle_order", "last_verified_at"])
            .values("id", "source_url", "lifecycle", "date_posted")[:batch]
        )
        return list(qs)

    def apply_result(
        self, job_id: int, result: VerifyResult, *, now: datetime
    ) -> None:
        from apps.jobs.models import Job

        try:
            job = Job.objects.get(pk=job_id)
        except Job.DoesNotExist:
            logger.warning("apply_result: Job id=%s not found; skipping", job_id)
            return

        if result.status is JobStatus.ACTIVE:
            job.lifecycle = Job.LIFECYCLE_ACTIVE
            job.last_verified_at = now
            job.verification_attempts = 0
            job.verification_backoff_until = None
        elif result.status is JobStatus.EXPIRED:
            job.lifecycle = Job.LIFECYCLE_EXPIRED
            job.last_verified_at = now
            job.verification_attempts = 0
            job.verification_backoff_until = None
        elif result.status in (JobStatus.UNKNOWN, JobStatus.ERROR):
            job.verification_attempts = (job.verification_attempts or 0) + 1
            hours = _compute_backoff_hours(job.verification_attempts)
            job.verification_backoff_until = now + timedelta(hours=hours)
        elif result.status is JobStatus.SESSION_EXPIRED:
            # Intentional no-op — operator alert is surfaced by the service report.
            return
        else:
            logger.warning("apply_result: unknown JobStatus %r for job %s", result.status, job_id)
            return

        job.save(update_fields=[
            "lifecycle", "last_verified_at",
            "verification_attempts", "verification_backoff_until",
        ])

    def apply_aging(self, *, now: datetime, threshold_days: int = 14) -> int:
        """Promote `active` rows whose `date_posted` is older than the
        threshold to `stale`. Returns the number of rows updated.
        """
        from apps.jobs.models import Job

        cutoff = now - timedelta(days=threshold_days)
        promoted = (
            Job.objects
            .filter(
                lifecycle=Job.LIFECYCLE_ACTIVE,
                date_posted__isnull=False,
                date_posted__lt=cutoff,
            )
            .update(lifecycle=Job.LIFECYCLE_STALE)
        )
        if promoted:
            logger.info("apply_aging: promoted %d job(s) active → stale", promoted)
        return int(promoted or 0)
