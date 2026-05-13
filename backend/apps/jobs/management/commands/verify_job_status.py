"""Management command — run the job-status verifier.

Wires up factory → service → repository per
``specs/001-linkedin-job-verifier/contracts/management_command.md``.

Usage:
    python manage.py verify_job_status --platform linkedin --batch 100 [--dry-run] [--json-report]
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.jobs.services.job_lifecycle_repository import DjangoJobLifecycleRepository
from ml_service.verifier import factory as verifier_factory
from ml_service.verifier.base import JobStatus
from ml_service.verifier.service import StatusCheckService

logger = logging.getLogger(__name__)


_MIN_BATCH = 1
_MAX_BATCH = 1000


class Command(BaseCommand):
    help = "Verify job listings against their source platforms and update lifecycle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--platform",
            default="linkedin",
            help="Verifier platform name (default: linkedin)",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=100,
            help=f"Max jobs to verify per run (default: 100, range {_MIN_BATCH}..{_MAX_BATCH})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run verifier but skip all DB writes",
        )
        parser.add_argument(
            "--json-report",
            action="store_true",
            help="Emit the run report as a single-line JSON object on stdout",
        )

    def handle(self, *args, **opts):
        platform = opts["platform"]
        batch = int(opts["batch"])
        dry_run = bool(opts["dry_run"])
        json_report = bool(opts["json_report"])

        if not (_MIN_BATCH <= batch <= _MAX_BATCH):
            raise CommandError(
                f"--batch out of range: {batch} (must be {_MIN_BATCH}..{_MAX_BATCH})"
            )

        try:
            verifier = verifier_factory.get_verifier(platform)
        except ValueError as e:
            raise CommandError(str(e)) from e

        service = StatusCheckService(
            verifier_registry={verifier.name: verifier},
            repository=DjangoJobLifecycleRepository(),
            clock=lambda: datetime.now(timezone.utc),
        )

        try:
            report = service.check_batch(
                platform=platform, batch=batch, dry_run=dry_run
            )
        except Exception as exc:
            # Auth-state missing: special exit code so cron can alert.
            from ml_service.verifier.browser_pool import AuthStateMissingError
            if isinstance(exc, AuthStateMissingError):
                self.stderr.write(self.style.ERROR(str(exc)))
                sys.exit(2)
            logger.exception("StatusCheckService failed")
            self.stderr.write(self.style.ERROR(f"Run aborted: {exc!r}"))
            sys.exit(3)

        self._print_report(report)
        if json_report:
            self._print_json_report(report)

        # Exit code policy (contracts/management_command.md)
        if (
            report.total_examined > 0
            and report.session_expired_count == report.total_examined
        ):
            sys.exit(2)
        sys.exit(0)

    # ── Output ──────────────────────────────────────────────────────────

    def _print_report(self, report) -> None:
        out = self.stdout.write

        out(f"verify_job_status — {report.platform} — {report.started_at:%Y-%m-%d %H:%M:%S} UTC")
        out(f"  platform              : {report.platform}")
        out(f"  batch requested       : {report.batch_size_requested}")
        out(f"  batch examined        : {report.total_examined}"
            f"          ({report.skipped_unsupported_url} skipped: unsupported url)")
        out("  outcomes              :")
        for status in JobStatus:
            count = report.counts_by_outcome.get(status, 0)
            out(f"                          {status.value:16s} : {count}")
        out(f"  wall-clock            : {self._format_wall(report.wall_clock_seconds)}")
        out(f"  dry-run               : {'yes' if report.dry_run else 'no'}")

        if report.session_expired_count > 0:
            out("")
            self.stderr.write(self.style.WARNING(
                f"ALERT: {report.session_expired_count} job(s) returned session_expired."
            ))
            self.stderr.write(self.style.WARNING(
                "  → Re-run `python -m ml_service.crawler.providers.linkedin_auth` and retry."
            ))

    def _print_json_report(self, report) -> None:
        payload = {
            "version": "1",
            "command": "verify_job_status",
            "platform": report.platform,
            "started_at": report.started_at.isoformat() if report.started_at else None,
            "finished_at": report.finished_at.isoformat() if report.finished_at else None,
            "wall_clock_s": round(report.wall_clock_seconds, 3),
            "batch_size_requested": report.batch_size_requested,
            "total_examined": report.total_examined,
            "skipped_unsupported_url": report.skipped_unsupported_url,
            "counts_by_outcome": {
                s.value: report.counts_by_outcome.get(s, 0) for s in JobStatus
            },
            "session_expired_count": report.session_expired_count,
            "dry_run": report.dry_run,
        }
        self.stdout.write(json.dumps(payload))

    @staticmethod
    def _format_wall(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}s"
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
