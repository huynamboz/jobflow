"""Deduplicate active catalog jobs by exact (title, company) (021/A9).

343 duplicate groups (731 redundant rows) pollute the ranking top-K ("JavaScript
Tutor" ×3). Per group keep ONE active row — preferring a row HR has engaged with
(pursuing/applied/won/in_progress/completed/lost), else the newest — and soft-
deactivate the rest (``is_active=False``, reversible). Groups with MULTIPLE
engaged rows are left untouched and reported for manual review (never orphan an
HR workflow).

    python manage.py dedup_jobs --dry-run   # print the full plan, no writes
    python manage.py dedup_jobs             # apply
"""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand

ENGAGED = ("pursuing", "applied", "won", "in_progress", "completed", "lost")


class Command(BaseCommand):
    help = "Deactivate duplicate active jobs (same title+company), keeping engaged/newest."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print plan only.")

    def handle(self, *args, **opts):
        from apps.employees.models import EmployeeJobMatch
        from apps.jobs.models import Job

        dry = opts["dry_run"]

        groups: dict[tuple[str, int | None], list[Job]] = defaultdict(list)
        for job in Job.objects.filter(is_active=True).only(
            "id", "title", "company_id", "created_at"
        ):
            groups[((job.title or "").strip().lower(), job.company_id)].append(job)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
        self.stdout.write(f"Active duplicate groups: {len(dup_groups)}")

        engaged_job_ids = set(
            EmployeeJobMatch.objects.filter(status__in=ENGAGED).values_list("job_id", flat=True)
        )

        to_deactivate: list[int] = []
        manual_review: list[tuple] = []
        kept_engaged = 0
        for (title, company_id), rows in dup_groups.items():
            engaged_rows = [r for r in rows if r.id in engaged_job_ids]
            if len(engaged_rows) > 1:
                # never orphan HR engagement — keep all engaged, drop only the rest
                manual_review.append((title, company_id, [r.id for r in engaged_rows]))
                losers = [r for r in rows if r.id not in engaged_job_ids]
            elif len(engaged_rows) == 1:
                kept_engaged += 1
                losers = [r for r in rows if r.id != engaged_rows[0].id]
            else:
                keeper = max(rows, key=lambda r: (r.created_at, r.id))
                losers = [r for r in rows if r.id != keeper.id]
            to_deactivate.extend(r.id for r in losers)

        self.stdout.write(
            f"Plan: deactivate {len(to_deactivate)} rows · keep-engaged {kept_engaged} "
            f"· manual-review groups {len(manual_review)}"
        )
        for title, company_id, ids in manual_review[:10]:
            self.stdout.write(f"  REVIEW: '{title[:50]}' company={company_id} engaged_rows={ids}")

        if dry:
            self.stdout.write(self.style.WARNING("--dry-run: no changes written."))
            return

        # Safety: re-assert nothing engaged is in the deactivation list.
        assert not (set(to_deactivate) & engaged_job_ids), "engaged job in deactivate list!"
        n = Job.objects.filter(id__in=to_deactivate).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(
            f"Deactivated {n} duplicate rows (reversible: is_active=True). "
            f"Run rebuild_job_pool to refresh the engine pool."
        ))