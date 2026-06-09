"""Re-match employees against the current job catalog — no CV re-parse, no LLM.

Run after a crawl or on a schedule so new jobs flow into each employee's
suggested list without resetting HR's pipeline progress.

    python manage.py rematch_employees                # everyone with skills
    python manage.py rematch_employees --employee 12  # a single employee
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.employees.models import Employee
from apps.employees.tasks import _do_rematch


class Command(BaseCommand):
    help = "Re-match employees against the current job catalog (no LLM)."

    def add_arguments(self, parser):
        parser.add_argument("--employee", type=int, default=None, help="Re-match a single employee id.")

    def handle(self, *args, **opts):
        qs = Employee.objects.filter(is_parse_failed=False).exclude(skills=[])
        if opts["employee"]:
            qs = qs.filter(pk=opts["employee"])

        total = qs.count()
        self.stdout.write(f"Re-matching {total} employee(s)…")
        created_total = 0
        for emp in qs.iterator():
            res = _do_rematch(emp.id)
            created_total += res.get("matches_created", 0)
            self.stdout.write(
                f"  #{emp.id} {emp.full_name}: "
                f"{res.get('matches_total', 0)} matched, "
                f"+{res.get('matches_created', 0)} new, "
                f"{res.get('matches_skipped', 0)} skipped"
            )
        self.stdout.write(self.style.SUCCESS(f"Done — {created_total} new matches across {total} employee(s)."))
