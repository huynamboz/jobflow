"""Synchronously render + send the HR daily digest. Useful for dev/cron.

Examples::

    python manage.py send_hr_digest --user-id 1
    python manage.py send_hr_digest --all
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.tasks import _send_one

User = get_user_model()


class Command(BaseCommand):
    help = "Send HR daily digest email(s) synchronously."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, **options):
        if options["user_id"] is None and not options["all"]:
            raise CommandError("Provide --user-id or --all")

        if options["user_id"] is not None:
            users = User.objects.filter(pk=options["user_id"])
            if not users.exists():
                raise CommandError(f"User {options['user_id']} not found")
        else:
            users = User.objects.filter(
                role__in=["admin", "recruiter"], notify_daily_digest=True
            )

        sent = skipped = 0
        for user in users:
            result = _send_one(user)
            self.stdout.write(f"  user={user.pk} -> {result}")
            if "sent_to" in result:
                sent += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f"Done. sent={sent} skipped={skipped}"))
