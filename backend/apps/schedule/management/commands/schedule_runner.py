"""In-process scheduler daemon.

Loops forever. Every ``--tick`` seconds it scans VerifierSchedule rows
for entries that should fire on the current UTC hour and haven't fired
in this calendar hour yet. Spawns the relevant management command via
the same code path as the manual "Run now" button.

Run forever in a dedicated process / tmux window:

    cd backend
    .venv/bin/python manage.py schedule_runner

The process holds no DB connection between ticks; sleeping is plain
``time.sleep``. Restart-safe — state lives entirely in
``VerifierSchedule.last_fired_at`` and the active-run trio.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from apps.schedule import services
from apps.schedule.models import VerifierSchedule

logger = logging.getLogger(__name__)

_DEFAULT_TICK_S = 60


class Command(BaseCommand):
    help = "Forever-loop scheduler that spawns verify_job_status / extract_job_dates by the hour."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tick", type=int, default=_DEFAULT_TICK_S,
            help=f"Seconds between scans (default {_DEFAULT_TICK_S}).",
        )
        parser.add_argument(
            "--once", action="store_true",
            help="Run a single scan and exit. For testing.",
        )

    def handle(self, *args, **opts):
        tick = max(5, int(opts["tick"]))
        once = bool(opts["once"])

        # Graceful Ctrl-C.
        self._stop = False
        def _sigterm(_signum, _frame):
            self._stop = True
            self.stderr.write(self.style.WARNING("schedule_runner: stopping after current tick"))
        signal.signal(signal.SIGINT, _sigterm)
        signal.signal(signal.SIGTERM, _sigterm)

        self.stdout.write(self.style.SUCCESS(
            f"schedule_runner started · tick={tick}s · once={once}"
        ))

        while not self._stop:
            now = datetime.now(timezone.utc)
            try:
                self._scan(now)
            except Exception:
                logger.exception("schedule_runner tick failed")
            if once:
                return
            # Sleep in small slices so SIGTERM is responsive.
            slept = 0
            while slept < tick and not self._stop:
                time.sleep(min(2, tick - slept))
                slept += 2

    def _scan(self, now: datetime) -> None:
        hour = now.hour
        for row in VerifierSchedule.objects.filter(enabled=True):
            services.refresh_active_run_state(row)
            if services.is_active_run(row):
                self.stdout.write(f"  [{row.command}] already running pid={row.current_run_pid}")
                continue
            if hour not in (row.hours_utc or []):
                continue
            if row.last_fired_at and (
                row.last_fired_at.date() == now.date()
                and row.last_fired_at.hour == hour
            ):
                continue
            ok, msg = services.start_run(row)
            row.last_fired_at = now
            row.save(update_fields=["last_fired_at"])
            if ok:
                self.stdout.write(self.style.SUCCESS(
                    f"  [{row.command}] fired @{hour:02d}:00 UTC → {msg}"
                ))
            else:
                self.stdout.write(self.style.ERROR(f"  [{row.command}] start failed: {msg}"))
