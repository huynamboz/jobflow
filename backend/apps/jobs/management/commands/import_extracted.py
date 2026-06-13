"""Import agent-extracted job files into the Job catalog — NO LLM call.

Reads data/extracted/<provider>/<YYYY-MM-DD>.json, where each item is a crawled
RawJob dict plus an "extracted" block (seniority, role_category, job_type,
experience_min/max, skills:[{name,importance}]) produced by the extract workflow.
JobService.save_raw_job(raw, extracted=...) writes Job + JobSkill without calling
the LLM.

Usage:
    python manage.py import_extracted
    python manage.py import_extracted --provider remotive --date 2026-06-12
    python manage.py import_extracted --dry-run
"""
import glob
import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.jobs.services import JobService
from ml_service.crawler.storage import _dict_to_raw_job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import agent-extracted job files (data/extracted) into the Job catalog (no LLM)"

    def add_arguments(self, parser):
        parser.add_argument("--in-dir", type=str, default="", help="Root (default <BASE_DIR>/data/extracted)")
        parser.add_argument("--provider", type=str, default="", help="Only this provider folder")
        parser.add_argument("--date", type=str, default="", help="Only <date>.json files")
        parser.add_argument("--dry-run", action="store_true", help="Count only, don't write DB")

    def handle(self, *args, **options):
        root = Path(options["in_dir"]) if options["in_dir"] else Path(settings.BASE_DIR) / "data" / "extracted"
        provider = options["provider"] or "*"
        date = options["date"] or "*"
        files = sorted(glob.glob(str(root / provider / f"{date}.json")))

        if not files:
            self.stdout.write(self.style.WARNING(f"No files under {root}/{provider}/{date}.json"))
            return

        svc = JobService()
        g_created = g_dup = g_fail = g_noextract = 0

        for f in files:
            try:
                jobs = json.loads(Path(f).read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f"  {f}: read failed ({e})"))
                continue

            created = dup = fail = noextract = 0
            for j in jobs:
                ex = j.get("extracted")
                if ex is None:
                    noextract += 1
                try:
                    # dry_run runs the real dedup + non-tech checks read-only (no writes)
                    job = svc.save_raw_job(_dict_to_raw_job(j), extracted=ex or {},
                                           dry_run=options["dry_run"])
                    if job:
                        created += 1
                    else:
                        dup += 1   # duplicate OR filtered (non-tech: role 'other' + <2 skills)
                except Exception as e:  # noqa: BLE001
                    fail += 1
                    logger.warning("import_extracted failed for %r: %s", (j.get("title") or "")[:60], e)

            label = f"{Path(f).parent.name}/{Path(f).name}"
            self.stdout.write(f"  {label}: {created} {'(dry)' if options['dry_run'] else 'created'}, "
                              f"{dup} dup/filtered, {fail} failed, {noextract} no-extract")
            g_created += created; g_dup += dup; g_fail += fail; g_noextract += noextract

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {g_created} {'(dry)' if options['dry_run'] else 'created'}, "
            f"{g_dup} dup, {g_fail} failed, {g_noextract} without extracted block."
        ))
