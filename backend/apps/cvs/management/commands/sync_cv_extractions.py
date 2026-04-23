"""Sync CVExtractionRecord results back to CV table.

Applies the latest done extraction result for each CV — updates seniority,
experience_years, education, role_category, work_experience, and CVSkill rows.

Usage:
    python manage.py sync_cv_extractions
    python manage.py sync_cv_extractions --dry-run
    python manage.py sync_cv_extractions --cv-ids 1 2 3
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync CVExtractionRecord results to CV table"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without writing")
        parser.add_argument("--cv-ids", nargs="+", type=int, help="Only sync specific CV IDs")

    def handle(self, *args, **options):
        from apps.cvs.models import CVExtractionRecord
        from apps.cvs.services.cv_batch_processor import _apply_result_to_cv

        dry_run = options["dry_run"]
        cv_id_filter = options.get("cv_ids")

        qs = CVExtractionRecord.objects.filter(status=CVExtractionRecord.STATUS_DONE).select_related("cv")
        if cv_id_filter:
            qs = qs.filter(cv_id__in=cv_id_filter)

        # Keep only the latest record per CV (highest id = most recent batch)
        latest: dict[int, CVExtractionRecord] = {}
        for rec in qs.order_by("id"):
            latest[rec.cv_id] = rec

        self.stdout.write(f"Found {len(latest)} CVs with done extraction records")
        if dry_run:
            self.stdout.write("(dry-run — no changes written)")

        ok = err = 0
        for cv_id, rec in latest.items():
            if not rec.result:
                self.stderr.write(f"  CV #{cv_id}: result is empty, skipping")
                err += 1
                continue

            if dry_run:
                role = rec.result.get("role_category", "?")
                sen = rec.result.get("seniority", "?")
                n_skills = len(rec.result.get("skills") or [])
                self.stdout.write(f"  CV #{cv_id}: role={role}, seniority={sen}, skills={n_skills}")
                ok += 1
                continue

            try:
                _apply_result_to_cv(cv_id, rec.result)
                ok += 1
            except Exception as exc:
                self.stderr.write(f"  CV #{cv_id} failed: {exc}")
                err += 1

        verb = "Would sync" if dry_run else "Synced"
        self.stdout.write(self.style.SUCCESS(f"{verb} {ok} CVs ({err} errors)"))
