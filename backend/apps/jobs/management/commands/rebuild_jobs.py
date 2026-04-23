"""
Management command: rebuild_jobs

Three-step pipeline to produce a clean, deduplicated job table:

  Step 1 – Dedup existing jobs
    For each unique LinkedIn job ID keep the record with the most skills;
    delete all other duplicates (cascade-deletes their JobSkill rows).

  Step 2 – Apply extraction results to matched jobs
    For the ~318 jobs whose source_url matches a done JDExtractionRecord,
    overwrite job_type / seniority / salary / experience / skills with the
    LLM-cleaned values.

  Step 3 – Import unmatched extraction records as new jobs
    For each of the ~6,749 done records that have no matching job yet,
    create a new Job (+ Company, Platform) from raw_data + result.

Usage:
    python manage.py rebuild_jobs
    python manage.py rebuild_jobs --dry-run
    python manage.py rebuild_jobs --skip-dedup
    python manage.py rebuild_jobs --skip-apply
    python manage.py rebuild_jobs --skip-import
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from django.db import transaction

from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)

_VIEW_ID_RE = re.compile(r"/(?:jobs/)?view/(\d+)/?")

WORK_MODES = {"remote", "hybrid", "on-site"}
EMPLOYMENT_TYPES = {"full-time", "part-time", "contract"}
VALID_JOB_TYPES = WORK_MODES | EMPLOYMENT_TYPES | {"other"}

PLATFORM_MAP = {
    "linkedin": {"name": "LinkedIn", "base_url": "https://linkedin.com"},
    "indeed": {"name": "Indeed", "base_url": "https://indeed.com"},
    "glassdoor": {"name": "Glassdoor", "base_url": "https://glassdoor.com"},
}


def _url_key(url: str) -> str:
    m = _VIEW_ID_RE.search(url)
    if m:
        return m.group(1)
    return url.split("?")[0].rstrip("/")


def _clamp(val, lo, hi, default):
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return default


def _pick_job_type(raw_job_type: str, result_job_type: str) -> str:
    """
    raw_job_type may be 'on-site, full-time' — prefer work mode if present,
    otherwise fall back to LLM-extracted employment type.
    """
    raw_lower = (raw_job_type or "").lower()
    for mode in WORK_MODES:
        if mode in raw_lower:
            return mode
    jt = (result_job_type or "other").lower().strip()
    return jt if jt in VALID_JOB_TYPES else "other"


class Command(BaseCommand):
    help = "Deduplicate jobs, apply LLM extractions, and import unmatched extraction records"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run",      action="store_true", help="Preview without writing")
        parser.add_argument("--skip-dedup",   action="store_true", help="Skip step 1 (dedup)")
        parser.add_argument("--skip-apply",   action="store_true", help="Skip step 2 (apply extractions)")
        parser.add_argument("--skip-import",  action="store_true", help="Skip step 3 (import new jobs)")

    def handle(self, *args, **options):
        from ml_service.data.skill_normalization import SkillNormalizer
        from apps.skills.models import Skill

        dry = options["dry_run"]
        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be written\n"))

        self.stdout.write("Loading skill taxonomy…")
        normalizer = SkillNormalizer()
        skill_cache = {s.canonical_name: s for s in Skill.objects.all()}
        self.stdout.write(f"  {len(skill_cache)} canonical skills\n")

        if not options["skip_dedup"]:
            self._step_dedup(dry)
        if not options["skip_apply"]:
            self._step_apply(normalizer, skill_cache, dry)
        if not options["skip_import"]:
            self._step_import(normalizer, skill_cache, dry)

        self.stdout.write(self.style.SUCCESS("\nDone."))

    # ── Step 1: Deduplicate ───────────────────────────────────────────────────

    def _step_dedup(self, dry: bool):
        from apps.jobs.models import Job, JobSkill

        self.stdout.write("Step 1 — Deduplicating jobs…")

        # Group job IDs by url_key; also keep jobs without source_url as-is
        groups: dict[str, list[tuple[int, int]]] = defaultdict(list)  # key → [(job_id, skills_count)]
        for job_id, url in Job.objects.exclude(source_url="").values_list("id", "source_url"):
            key = _url_key(url)
            skill_count = JobSkill.objects.filter(job_id=job_id).count()
            groups[key].append((job_id, skill_count))

        to_delete: list[int] = []
        for key, entries in groups.items():
            if len(entries) <= 1:
                continue
            # Keep the job with most skills; tie-break: highest id (most recent)
            entries.sort(key=lambda x: (x[1], x[0]), reverse=True)
            to_delete.extend(jid for jid, _ in entries[1:])

        self.stdout.write(f"  {len(to_delete)} duplicate jobs to delete")
        if not dry and to_delete:
            # Delete in batches to avoid huge IN clause
            batch_size = 500
            deleted = 0
            for i in range(0, len(to_delete), batch_size):
                batch = to_delete[i : i + batch_size]
                n, _ = Job.objects.filter(id__in=batch).delete()
                deleted += n
            self.stdout.write(f"  Deleted {deleted} records")
        self.stdout.write("")

    # ── Step 2: Apply extractions → matched jobs ──────────────────────────────

    def _step_apply(self, normalizer, skill_cache, dry: bool):
        from apps.jobs.models import Job, JobSkill, JDExtractionRecord

        self.stdout.write("Step 2 — Applying extraction results to matched jobs…")

        # Build url_key → job_id map (post-dedup, each key maps to exactly 1 job)
        key_to_job: dict[str, int] = {}
        for job_id, url in Job.objects.exclude(source_url="").values_list("id", "source_url"):
            key_to_job[_url_key(url)] = job_id

        records = (
            JDExtractionRecord.objects
            .filter(status=JDExtractionRecord.STATUS_DONE)
            .exclude(result=None)
            .exclude(source_url="")
        )

        matched = updated = skipped = 0
        for rec in records:
            job_id = key_to_job.get(_url_key(rec.source_url))
            if not job_id:
                skipped += 1
                continue
            matched += 1
            if not dry:
                self._apply_result_to_job(job_id, rec.raw_data, rec.result, normalizer, skill_cache)
                updated += 1

        self.stdout.write(f"  matched={matched}, updated={updated}, no-match={skipped}\n")

    def _apply_result_to_job(self, job_id, raw_data, result, normalizer, skill_cache):
        from apps.jobs.models import Job, JobSkill

        raw_jt = raw_data.get("job_type", "")
        res_jt = result.get("job_type", "other")
        job_type = _pick_job_type(raw_jt, res_jt)

        exp_min_raw = result.get("experience_min")
        exp_max_raw = result.get("experience_max")

        Job.objects.filter(id=job_id).update(
            seniority=_clamp(result.get("seniority"), 0, 5, 2),
            job_type=job_type,
            salary_min=int(result.get("salary_min") or 0),
            salary_max=int(result.get("salary_max") or 0),
            salary_currency=(result.get("salary_currency") or "USD")[:10],
            role_category=(result.get("role_category") or "other")[:20],
            experience_min=float(exp_min_raw) if exp_min_raw is not None else None,
            experience_max=float(exp_max_raw) if exp_max_raw is not None else None,
        )
        self._replace_skills(job_id, result.get("skills") or [], normalizer, skill_cache)

    # ── Step 3: Import unmatched extraction records ───────────────────────────

    def _step_import(self, normalizer, skill_cache, dry: bool):
        from apps.jobs.models import Job, JDExtractionRecord
        from apps.jobs.services.platform_service import PlatformService

        self.stdout.write("Step 3 — Importing unmatched extraction records as new jobs…")

        # Current set of url keys already in DB
        existing_keys = {
            _url_key(url)
            for url in Job.objects.exclude(source_url="").values_list("source_url", flat=True)
        }

        unmatched = [
            rec for rec in (
                JDExtractionRecord.objects
                .filter(status=JDExtractionRecord.STATUS_DONE)
                .exclude(result=None)
                .exclude(source_url="")
            )
            if _url_key(rec.source_url) not in existing_keys
        ]

        self.stdout.write(f"  {len(unmatched)} records to import")
        if dry:
            return

        created = failed = 0
        for rec in unmatched:
            try:
                self._import_record(rec, normalizer, skill_cache, PlatformService)
                created += 1
            except Exception as exc:
                logger.warning("Failed to import record #%s: %s", rec.id, exc)
                failed += 1
            if (created + failed) % 500 == 0:
                self.stdout.write(f"  …{created} created, {failed} failed")

        self.stdout.write(f"  Imported {created}, failed {failed}\n")

    def _import_record(self, rec, normalizer, skill_cache, PlatformService):
        from apps.jobs.models import Job, JobSkill

        raw = rec.raw_data
        result = rec.result

        source = (raw.get("source") or "linkedin").lower()
        platform_info = PLATFORM_MAP.get(source, {"name": source.title(), "base_url": ""})
        platform = PlatformService.get_or_create_platform(**platform_info)

        extra = raw.get("extra") or {}
        company = PlatformService.get_or_create_company(
            name=raw.get("company") or "Unknown",
            platform=platform,
            logo_url=raw.get("company_logo_url") or "",
            profile_url=raw.get("company_url") or "",
            industry=extra.get("company_industry") or "",
            size=extra.get("company_size") or "",
        )

        raw_jt = raw.get("job_type", "")
        res_jt = result.get("job_type", "other")
        job_type = _pick_job_type(raw_jt, res_jt)

        fingerprint = raw.get("fingerprint") or rec.content_hash or ""
        title = (result.get("title") or raw.get("title") or "")[:500]
        description = (raw.get("description") or "")[:10000]
        location = (result.get("location") or raw.get("location") or "")[:300]
        applicant_count = raw.get("applicant_count") or ""
        date_posted = raw.get("date_posted") or None

        exp_min_raw = result.get("experience_min")
        exp_max_raw = result.get("experience_max")

        with transaction.atomic():
            job, created = Job.objects.get_or_create(
                platform=platform,
                fingerprint=fingerprint,
                defaults=dict(
                    company=company,
                    title=title,
                    description=description,
                    location=location,
                    seniority=_clamp(result.get("seniority"), 0, 5, 2),
                    job_type=job_type,
                    salary_min=int(result.get("salary_min") or 0),
                    salary_max=int(result.get("salary_max") or 0),
                    salary_currency=(result.get("salary_currency") or "USD")[:10],
                    role_category=(result.get("role_category") or "other")[:20],
                    experience_min=float(exp_min_raw) if exp_min_raw is not None else None,
                    experience_max=float(exp_max_raw) if exp_max_raw is not None else None,
                    source_url=rec.source_url or "",
                    applicant_count=str(applicant_count)[:100],
                    date_posted=date_posted,
                    is_active=True,
                ),
            )
            if created:
                self._replace_skills(job.id, result.get("skills") or [], normalizer, skill_cache)

    # ── Shared: replace skills ────────────────────────────────────────────────

    def _replace_skills(self, job_id, skills, normalizer, skill_cache):
        from apps.jobs.models import JobSkill

        rows = []
        for s in skills:
            if isinstance(s, dict):
                name = s.get("name", "")
                importance = _clamp(s.get("importance", 3), 1, 5, 3)
            else:
                name = str(s)
                importance = 3

            canonical = normalizer.normalize(name)
            if canonical and canonical in skill_cache:
                rows.append(JobSkill(
                    job_id=job_id,
                    skill=skill_cache[canonical],
                    importance=importance,
                ))

        if rows:
            JobSkill.objects.filter(job_id=job_id).delete()
            JobSkill.objects.bulk_create(rows, ignore_conflicts=True)
