"""Push the morning staffing digest to every connected integration channel.

Run standalone (cron/schedule_runner) or as a step in morning_refresh:
    python manage.py send_integration_digest
    python manage.py send_integration_digest --top 8
    python manage.py send_integration_digest --message "Custom text"
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integrations.services.digest import deliver_digest, deliver_to_all


class Command(BaseCommand):
    help = "Send the morning digest to all connected integration channels."

    def add_arguments(self, parser):
        parser.add_argument("--message", help="Override the digest with custom plain text.")
        parser.add_argument("--top", type=int, default=5, help="How many top suggestions to include (default 5).")

    def handle(self, *args, **options):
        if options.get("message"):
            results = deliver_to_all(options["message"], subject="JobFlow")
        else:
            results = deliver_digest(top_n=options["top"])
        if not results:
            self.stdout.write(self.style.WARNING("No connected integrations."))
            return
        for platform, outcome in results.items():
            style = self.style.SUCCESS if outcome == "sent" else self.style.ERROR
            self.stdout.write(style(f"{platform}: {outcome}"))
