"""Morning refresh — the daily HR pipeline tick.

1. Re-match every employee (with parsed skills) against the current job
   catalog (no CV re-parse, no LLM) so freshly-crawled jobs flow into each
   employee's suggested list. Upserts, so no duplicate jobs and the job
   pipeline status is preserved.
2. Send the HR daily digest so recipients get "CV X has Y new jobs".

Designed to be run once each morning (after the overnight crawl) by the
schedule daemon or OS cron::

    python manage.py morning_refresh                 # everyone with skills + digest
    python manage.py morning_refresh --no-digest      # re-match only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Daily morning refresh: re-match all employees, then send the HR digest."

    def add_arguments(self, parser):
        parser.add_argument("--no-digest", action="store_true", help="Skip the digest email step.")
        parser.add_argument("--no-rebuild", action="store_true", help="Skip rebuilding the job pool from the live catalog.")

    def handle(self, *args, **opts):
        from apps.employees.models import Employee
        from apps.employees.tasks import _do_rematch

        started = timezone.now()
        self.stdout.write(self.style.SUCCESS(f"== Morning refresh @ {started:%Y-%m-%d %H:%M:%S} UTC =="))

        # --- 0. Rebuild job pool from the live catalog (feature 018) ------
        if opts["no_rebuild"]:
            self.stdout.write("[1/3] Job-pool rebuild skipped (--no-rebuild).")
        else:
            # feature 027: use the rebuild_job_pool command — incremental upsert into
            # the pgvector store (encode only deltas), with a weekly --full on Monday
            # to refresh everything + the snapshot fallback (safety net vs hash drift).
            from django.core.management import call_command

            full = started.weekday() == 0  # Monday
            self.stdout.write(f"[1/3] Rebuilding job pool ({'FULL' if full else 'incremental'})…")
            call_command("rebuild_job_pool", full=full)

        # --- 1. Re-match -------------------------------------------------
        qs = Employee.objects.filter(is_parse_failed=False).exclude(skills=[])

        total = qs.count()
        self.stdout.write(f"[2/3] Re-matching {total} employee(s)…")
        created_total = 0
        for emp in qs.iterator():
            res = _do_rematch(emp.id)
            created = res.get("matches_created", 0)
            created_total += created
            self.stdout.write(
                f"  #{emp.id} {emp.full_name}: {res.get('matches_total', 0)} matched, "
                f"+{created} new, {res.get('matches_skipped', 0)} skipped"
            )
        self.stdout.write(self.style.SUCCESS(f"  → {created_total} new matches across {total} employee(s)."))

        # --- 2. Digest ---------------------------------------------------
        if opts["no_digest"]:
            self.stdout.write("[3/3] Digest skipped (--no-digest).")
        else:
            sent, skipped = self._send_digests()
            self.stdout.write(self.style.SUCCESS(f"[3/3] Digest sent={sent} skipped={skipped}."))
            # Push the same morning bulletin to every connected integration
            # channel (Slack/Telegram/…). Best-effort — never break the tick.
            self._push_integrations(created_total)

        elapsed = (timezone.now() - started).total_seconds()
        self.stdout.write(self.style.SUCCESS(
            f"== Done in {elapsed:.1f}s · {created_total} new matches =="
        ))

    def _push_integrations(self, new_matches: int) -> None:
        """Broadcast the morning bulletin to connected integration channels."""
        from apps.integrations.models import Integration
        from apps.integrations.services.digest import deliver_digest

        if not Integration.objects.exists():
            return
        results = deliver_digest(top_n=5, new_matches=new_matches)
        ok = sum(1 for v in results.values() if v == "sent")
        self.stdout.write(self.style.SUCCESS(
            f"[3/3] Integrations pushed: {ok}/{len(results)} channel(s)."
        ))
        for plat, outcome in results.items():
            if outcome != "sent":
                self.stdout.write(self.style.WARNING(f"  {plat}: {outcome}"))

    def _send_digests(self) -> tuple[int, int]:
        from django.contrib.auth import get_user_model

        from apps.notifications.tasks import _send_one

        User = get_user_model()
        recipients = User.objects.filter(role__in=["admin", "recruiter"], notify_daily_digest=True)
        sent = skipped = 0
        for user in recipients:
            result = _send_one(user)
            if "sent_to" in result:
                sent += 1
                self.stdout.write(f"  digest → {result['sent_to']}")
            else:
                skipped += 1
        return sent, skipped
