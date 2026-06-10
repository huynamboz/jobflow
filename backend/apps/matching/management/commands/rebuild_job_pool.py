"""Rebuild the matcher's job pool from the live Job catalog (feature 018).

Builds JobData from `Job` + `JobSkill`, inductively encodes the job nodes into
the GNN engine (no retraining), and persists a shareable on-disk snapshot the
live server hot-reloads. Run after the overnight crawl + skill extraction, or
manually before trusting it in production.

    python manage.py rebuild_job_pool                 # full rebuild + save snapshot
    python manage.py rebuild_job_pool --limit 50 --dry-run   # smoke test, no save
    python manage.py rebuild_job_pool --no-save       # rebuild in-process only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Rebuild the engine job pool from the live Job catalog (inductive, no retrain)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Build only the first N jobs (smoke test).")
        parser.add_argument("--dry-run", action="store_true", help="Build + encode, report counts, do not save the snapshot.")
        parser.add_argument("--no-save", action="store_true", help="Rebuild the in-process pool only; do not save the snapshot.")

    def handle(self, *args, **opts):
        from apps.matching.services.matching_service import _get_engine, build_jobdata_from_db
        from ml_service.inference import job_pool_snapshot

        self.stdout.write("Building JobData from the live catalog…")
        jobs = build_jobdata_from_db(limit=opts["limit"])
        if not jobs:
            raise CommandError("No jobs with skills found — nothing to build.")
        self.stdout.write(f"  {len(jobs)} jobs with skills")

        engine = _get_engine()
        report = engine.rebuild_job_pool(jobs)
        self.stdout.write(self.style.SUCCESS(
            f"Encoded pool: {report.num_jobs} jobs, "
            f"{report.skill_skipped_edges} skill-skipped edges, "
            f"{report.encode_seconds}s"
        ))

        if opts["dry_run"] or opts["no_save"]:
            self.stdout.write("Snapshot NOT saved (%s)." % ("--dry-run" if opts["dry_run"] else "--no-save"))
            return

        path = engine.snapshot_job_pool(
            job_pool_snapshot.DEFAULT_DIR, skill_skipped_edges=report.skill_skipped_edges
        )
        self.stdout.write(self.style.SUCCESS(f"Snapshot saved → {path}"))
