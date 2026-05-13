"""Management command — backfill Job.date_posted by re-fetching source pages.

Per specs/002-job-date-posted-extraction/contracts/extract_command.md.

Usage:
    python manage.py extract_job_dates --platform linkedin --batch 100 [--dry-run] [--json-report]
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.jobs.services.job_lifecycle_repository import DjangoJobLifecycleRepository
from ml_service.crawler.providers.linkedin_auth import load_state_path
from ml_service.verifier.backfill_service import BackfillReport, DateBackfillService
from ml_service.verifier.browser_pool import AuthStateMissingError, open_browser_page

logger = logging.getLogger(__name__)

_MIN_BATCH = 1
_MAX_BATCH = 1000

_LINKEDIN_URL_PATTERNS = ("linkedin.com/jobs/",)


def _linkedin_supports(url: str) -> bool:
    return any(p in url for p in _LINKEDIN_URL_PATTERNS)


class Command(BaseCommand):
    help = "Backfill Job.date_posted for rows that are currently NULL."

    def add_arguments(self, parser):
        parser.add_argument("--platform", default="linkedin")
        parser.add_argument("--batch", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--json-report", action="store_true")

    def handle(self, *args, **opts):
        platform = opts["platform"]
        batch = int(opts["batch"])
        dry_run = bool(opts["dry_run"])
        json_report = bool(opts["json_report"])

        if platform != "linkedin":
            raise CommandError(f"v1 supports only --platform linkedin (got {platform!r}).")
        if not (_MIN_BATCH <= batch <= _MAX_BATCH):
            raise CommandError(
                f"--batch out of range: {batch} (must be {_MIN_BATCH}..{_MAX_BATCH})"
            )

        state_path = load_state_path()
        if not state_path:
            self.stderr.write(self.style.ERROR(
                "Auth state missing or invalid — run "
                "`python -m ml_service.crawler.providers.linkedin_auth`"
            ))
            sys.exit(2)

        @contextmanager
        def browser_factory():
            with open_browser_page(state_path, headless=True) as (page, ctx):
                yield page, ctx

        service = DateBackfillService(
            repository=DjangoJobLifecycleRepository(),
            browser_factory=browser_factory,
            clock=lambda: datetime.now(timezone.utc),
            url_supports=_linkedin_supports,
        )

        try:
            report = service.run(platform=platform, batch=batch, dry_run=dry_run)
        except AuthStateMissingError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            sys.exit(2)
        except Exception as exc:
            logger.exception("DateBackfillService failed")
            self.stderr.write(self.style.ERROR(f"Run aborted: {exc!r}"))
            sys.exit(3)

        self._print_report(report)
        if json_report:
            self._print_json_report(report)

        if (
            report.total_examined > 0
            and report.session_expired_count >= report.total_examined
        ):
            sys.exit(2)
        sys.exit(0)

    # ── Output ──────────────────────────────────────────────────────────

    def _print_report(self, report: BackfillReport) -> None:
        out = self.stdout.write
        out(f"extract_job_dates — {report.platform} — {report.started_at:%Y-%m-%d %H:%M:%S} UTC")
        out(f"  platform              : {report.platform}")
        out(f"  batch requested       : {report.batch_size_requested}")
        out(f"  batch examined        : {report.total_examined}"
            f"          ({report.skipped_unsupported_url} skipped: unsupported url)")
        out("  outcomes              :")
        out(f"                          populated       : {report.populated_count}")
        out(f"                          expired_marked  : {report.expired_marked_count}")
        out(f"                          none            : {report.none_count}")
        out(f"                          error           : {report.error_count}")
        out(f"                          session_expired : {report.session_expired_count}")
        out(f"  wall-clock            : {self._format_wall(report.wall_clock_seconds)}")
        out(f"  dry-run               : {'yes' if report.dry_run else 'no'}")

        if report.session_expired_count > 0:
            self.stderr.write(self.style.WARNING(
                f"ALERT: {report.session_expired_count} job(s) marked session_expired. "
                "Auth-state file was preserved."
            ))
            self.stderr.write(self.style.WARNING(
                "  → Re-run `python -m ml_service.crawler.providers.linkedin_auth` and retry."
            ))

    def _print_json_report(self, report: BackfillReport) -> None:
        payload = {
            "version": "1",
            "command": "extract_job_dates",
            "platform": report.platform,
            "started_at": report.started_at.isoformat() if report.started_at else None,
            "finished_at": report.finished_at.isoformat() if report.finished_at else None,
            "wall_clock_s": round(report.wall_clock_seconds, 3),
            "batch_size_requested": report.batch_size_requested,
            "total_examined": report.total_examined,
            "skipped_unsupported_url": report.skipped_unsupported_url,
            "populated_count": report.populated_count,
            "expired_marked_count": report.expired_marked_count,
            "none_count": report.none_count,
            "error_count": report.error_count,
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
