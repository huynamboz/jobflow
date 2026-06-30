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


# verify status → (symbol, color, overview-counter key)
_VERIFY_SYM = {
    JobStatus.ACTIVE: ("✓", "green", "active"),
    JobStatus.EXPIRED: ("✗", "red", "expired"),
    JobStatus.UNKNOWN: ("?", "yellow", "unknown"),
    JobStatus.ERROR: ("!", "magenta", "error"),
    JobStatus.SESSION_EXPIRED: ("⌧", "red", "error"),
}


def _verify_progress_cb(dash):
    """Build a check_batch on_progress callback that feeds the full-terminal
    dashboard — one overview tally bump + one table row per verified job."""
    def cb(i: int, total: int, job_id: int, url: str, result) -> None:
        sym, color, key = _VERIFY_SYM.get(result.status, ("·", "white", "error"))
        has_logo = bool(getattr(result, "company_logo", ""))
        dash.set(done=i, total=total)
        dash.inc(key)
        if has_logo:
            dash.inc("logos")
        dash.row(
            i, job_id, f"[{color}]{sym} {result.status.value}[/]",
            (url or "")[:80], "🖼" if has_logo else "[dim]-[/]",
        )
    return cb


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
        parser.add_argument(
            "--no-auth-check",
            action="store_true",
            help="Deprecated / no-op — guest (anonymous) verification is now the default.",
        )
        parser.add_argument(
            "--use-auth",
            action="store_true",
            help=(
                "Opt into the authenticated li_at session. NOT recommended: "
                "high-volume status checks from a logged-in account get it "
                "flagged/locked. Default verifies anonymously (guest layout), "
                "which still detects expired jobs via the redirect signal."
            ),
        )
        parser.add_argument(
            "--headed",
            action="store_true",
            help="Launch Chromium with a visible window. Default is headless.",
        )
        parser.add_argument(
            "--min-age-hours",
            type=float,
            default=168.0,
            help=(
                "Skip jobs verified within the last N hours (never-verified jobs "
                "are always eligible). Avoids re-checking the same job multiple "
                "times a day. Default 12; pass 0 to disable."
            ),
        )

    def handle(self, *args, **opts):
        platform = opts["platform"]
        batch = int(opts["batch"])
        dry_run = bool(opts["dry_run"])
        json_report = bool(opts["json_report"])
        # Guest (anonymous) is the default; --use-auth opts into the risky li_at path.
        require_li_at = bool(opts["use_auth"])
        headed = bool(opts["headed"])

        if not (_MIN_BATCH <= batch <= _MAX_BATCH):
            raise CommandError(
                f"--batch out of range: {batch} (must be {_MIN_BATCH}..{_MAX_BATCH})"
            )

        try:
            verifier = verifier_factory.get_verifier(
                platform, require_li_at=require_li_at, headless=not headed,
            )
        except ValueError as e:
            raise CommandError(str(e)) from e

        service = StatusCheckService(
            verifier_registry={verifier.name: verifier},
            repository=DjangoJobLifecycleRepository(),
            clock=lambda: datetime.now(timezone.utc),
            min_verified_age_hours=float(opts["min_age_hours"]),
        )

        # Full-terminal live dashboard when on a terminal (skip for JSON output
        # / pipes / cron so logs stay plain).
        dash = None
        console = None
        if not json_report and sys.stdout.isatty():
            try:
                from rich.console import Console
                from apps.jobs.services.live_dashboard import make_verify_dashboard
                console = Console()
                if console.is_terminal:
                    dash = make_verify_dashboard(console, platform, batch)
            except ImportError:
                dash = None

        try:
            if dash:
                with dash:
                    report = service.check_batch(
                        platform=platform, batch=batch, dry_run=dry_run,
                        on_progress=_verify_progress_cb(dash),
                    )
            else:
                report = service.check_batch(
                    platform=platform, batch=batch, dry_run=dry_run,
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

        if dash:
            self._render_rich_summary(console, report, dash)
        else:
            self._print_report(report)
        if json_report:
            self._print_json_report(report)

        # Persist run log for the admin dashboard (spec 003). Never block exit
        # code on persistence failure — observability MUST NOT break ops.
        try:
            from apps.jobs.models import VerifierRunLog
            VerifierRunLog.objects.create(
                command=VerifierRunLog.COMMAND_VERIFY,
                platform=platform,
                started_at=report.started_at,
                finished_at=report.finished_at,
                batch_size_requested=report.batch_size_requested,
                total_examined=report.total_examined,
                skipped_unsupported_url=report.skipped_unsupported_url,
                counts_by_outcome={s.value: report.counts_by_outcome.get(s, 0) for s in JobStatus},
                session_expired_count=report.session_expired_count,
                error_count=report.counts_by_outcome.get(JobStatus.ERROR, 0),
                dry_run=report.dry_run,
            )
        except Exception:
            logger.exception("Failed to persist VerifierRunLog — continuing")

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

    def _render_rich_summary(self, console, report, dash) -> None:
        from rich.table import Table
        from rich import box

        table = Table(
            box=box.SIMPLE_HEAD, title_justify="left",
            title=(f"[bold]✓ verify {report.platform} — {report.total_examined} examined "
                   f"in {self._format_wall(report.wall_clock_seconds)}[/]"),
        )
        table.add_column("Outcome")
        table.add_column("Count", justify="right")
        rows = [
            ("[green]✓ active[/]", JobStatus.ACTIVE),
            ("[red]✗ expired[/]", JobStatus.EXPIRED),
            ("[yellow]? unknown[/]", JobStatus.UNKNOWN),
            ("[magenta]! error[/]", JobStatus.ERROR),
            ("[red]⌧ session_expired[/]", JobStatus.SESSION_EXPIRED),
        ]
        for label, status in rows:
            count = report.counts_by_outcome.get(status, 0)
            table.add_row(label, f"[bold]{count}[/]" if count else "[dim]0[/]")
        console.print(table)

        console.print(f"[blue]🖼 {dash.get('logos')}[/] company logo(s) scraped from pages"
                      + ("" if report.dry_run else " → backfilled where missing"))
        if report.skipped_unsupported_url:
            console.print(f"[dim]{report.skipped_unsupported_url} skipped (unsupported url)[/]")
        if report.dry_run:
            console.print("[yellow]dry-run — no DB writes[/]")
        if report.session_expired_count:
            console.print(
                f"[bold red]ALERT: {report.session_expired_count} session_expired — "
                f"re-run `python -m ml_service.crawler.providers.linkedin_auth`[/]"
            )

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
