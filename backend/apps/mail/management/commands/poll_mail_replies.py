"""Poll all active mail credentials for recruiter replies (026 FR-006/011).

One-shot by default; pass --interval N to run forever, polling every N seconds
(used by runserver_all to poll every 5 minutes). The same code path backs the
"Sync now" button (apps.mail.views.sync_now) for manual triggering.
"""
from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.mail.models import EmployeeMailCredential


class Command(BaseCommand):
    help = "Poll active employee mailboxes for replies to system-sent applications."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval", type=int, default=0,
            help="If >0, loop forever polling every N seconds (e.g. 300 = 5 min).",
        )

    def handle(self, *args, **opts):
        interval = int(opts.get("interval") or 0)
        if interval > 0:
            self._loop(interval)
        else:
            self._poll_once()

    def _poll_once(self) -> int:
        from apps.mail.services.imap_poll import poll_credential

        total = 0
        creds = EmployeeMailCredential.objects.filter(status=EmployeeMailCredential.STATUS_ACTIVE)
        for cred in creds:
            try:
                n = poll_credential(cred)
                total += n
                if n:
                    self.stdout.write(f"  {cred.gmail_address}: {n} new")
            except Exception as e:  # noqa: BLE001 — one bad mailbox must not kill the run
                cred.status = EmployeeMailCredential.STATUS_ERROR
                cred.last_error = str(e)[:500]
                cred.save(update_fields=["status", "last_error"])
                self.stderr.write(self.style.WARNING(f"  {cred.gmail_address}: poll error → {e}"))
        self.stdout.write(self.style.SUCCESS(
            f"poll_mail_replies done — {total} new across {creds.count()} mailbox(es)."
        ))
        return total

    def _loop(self, interval: int) -> None:
        self._stop = False

        def _sig(_signum, _frame):
            self._stop = True
            self.stderr.write(self.style.WARNING("poll_mail_replies: stopping after current cycle"))

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
        self.stdout.write(self.style.SUCCESS(f"poll_mail_replies loop started · every {interval}s"))

        while not self._stop:
            close_old_connections()  # don't reuse stale DB conns across cycles
            try:
                self._poll_once()
            except Exception as e:  # noqa: BLE001 — keep looping despite transient errors
                self.stderr.write(self.style.ERROR(f"poll cycle failed: {e}"))
            # Sleep in small slices so SIGTERM stays responsive.
            slept = 0
            while slept < interval and not self._stop:
                time.sleep(min(2, interval - slept))
                slept += 2
