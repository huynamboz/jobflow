"""Poll all active mail credentials for recruiter replies (026 FR-006/011)."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.mail.models import EmployeeMailCredential


class Command(BaseCommand):
    help = "Poll active employee mailboxes for replies to system-sent applications."

    def handle(self, *args, **opts):
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
        self.stdout.write(self.style.SUCCESS(f"poll_mail_replies done — {total} new across {creds.count()} mailbox(es)."))
