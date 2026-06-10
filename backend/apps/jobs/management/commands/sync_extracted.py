"""
Management command: sync_extracted

Syncs LLM-extracted clean data back into the Job and CV models.

  Jobs : JDExtractionRecord.result  → Job fields + JobSkill rows
           matched by Job.source_url  == JDExtractionRecord.source_url

  CVs  : CVExtractionRecord.result  → CV fields + CVSkill rows
           matched directly via CVExtractionRecord.cv FK

Usage:
    python manage.py sync_extracted
    python manage.py sync_extracted --jobs-only
    python manage.py sync_extracted --cvs-only
    python manage.py sync_extracted --dry-run
"""

import re

from django.core.management.base import BaseCommand


JOB_TYPE_VALUES = {"full-time", "part-time", "contract", "remote", "hybrid", "on-site", "other"}

# Matches LinkedIn /jobs/view/1234567890/ and generic /view/ID/ patterns
_VIEW_ID_RE = re.compile(r"/(?:jobs/)?view/(\d+)/?")


def _clamp_int(val, lo=0, hi=5, default=2) -> int:
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return default


def _seniority_from_years(years: float) -> int:
    if years < 0.5:
        return 0
    if years < 2:
        return 1
    if years < 5:
        return 2
    if years < 8:
        return 3
    if years < 12:
        return 4
    return 5


class Command(BaseCommand):
    help = "Sync JDExtractionRecord and CVExtractionRecord results into Job and CV models"

    def add_arguments(self, parser):
        parser.add_argument("--jobs-only", action="store_true", help="Sync jobs only")
        parser.add_argument("--cvs-only",  action="store_true", help="Sync CVs only")
        parser.add_argument("--dry-run",   action="store_true", help="Preview without writing")

    def handle(self, *args, **options):
        from ml_service.data.skill_normalization import SkillNormalizer
        from apps.skills.models import Skill

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be written"))

        self.stdout.write("Loading skill taxonomy...")
        normalizer  = SkillNormalizer()
        skill_cache = {s.canonical_name: s for s in Skill.objects.all()}
        self.stdout.write(f"  {len(skill_cache)} canonical skills loaded")

        if not options["cvs_only"]:
            self._sync_jobs(normalizer, skill_cache, dry_run)
        if not options["jobs_only"]:
            self._sync_cvs(normalizer, skill_cache, dry_run)

    # ── Jobs ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _url_key(url: str) -> str:
        """Extract a stable key from a job URL, ignoring tracking params.

        For LinkedIn  /jobs/view/1234567/ → '1234567'
        For others    full URL is used as-is.
        """
        m = _VIEW_ID_RE.search(url)
        if m:
            return m.group(1)
        # Strip query string for generic URLs
        return url.split("?")[0].rstrip("/")

    def _sync_jobs(self, normalizer, skill_cache, dry_run):
        from apps.jobs.models import Job, JobSkill, JDExtractionRecord

        self.stdout.write("\nSyncing jobs...")

        # Build url_key → job_id map
        url_key_to_job_id: dict[str, int] = {}
        for job_id, url in Job.objects.exclude(source_url="").values_list("id", "source_url"):
            key = self._url_key(url)
            url_key_to_job_id[key] = job_id

        self.stdout.write(f"  {len(url_key_to_job_id)} jobs with source_url in DB")

        records = list(
            JDExtractionRecord.objects
            .filter(status=JDExtractionRecord.STATUS_DONE)
            .exclude(result=None)
            .exclude(source_url="")
            .only("id", "source_url", "result")
        )
        self.stdout.write(f"  {len(records)} done JDExtractionRecords with source_url")

        matched = skipped = updated = 0
        for rec in records:
            key    = self._url_key(rec.source_url)
            job_id = url_key_to_job_id.get(key)
            if not job_id:
                skipped += 1
                continue
            matched += 1

            r = rec.result
            seniority   = _clamp_int(r.get("seniority"), 0, 5, 2)
            job_type    = r.get("job_type") or "other"
            if job_type not in JOB_TYPE_VALUES:
                job_type = "other"
            salary_min  = int(r.get("salary_min") or 0)
            salary_max  = int(r.get("salary_max") or 0)
            currency    = (r.get("salary_currency") or "USD")[:10]
            role_cat    = (r.get("role_category") or "other")[:20]
            title       = (r.get("title") or "")[:500]
            exp_min_raw = r.get("experience_min")
            exp_max_raw = r.get("experience_max")
            exp_min     = float(exp_min_raw) if exp_min_raw is not None else None
            exp_max     = float(exp_max_raw) if exp_max_raw is not None else None

            if not dry_run:
                update_kwargs = dict(
                    seniority=seniority,
                    job_type=job_type,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=currency,
                    role_category=role_cat,
                    experience_min=exp_min,
                    experience_max=exp_max,
                )
                if title:
                    update_kwargs["title"] = title
                Job.objects.filter(id=job_id).update(**update_kwargs)

                self._replace_job_skills(
                    job_id, r.get("skills") or [], normalizer, skill_cache
                )
                updated += 1

        self.stdout.write(
            f"  matched={matched}, skipped(no url match)={skipped}, updated={updated}"
        )
        self._report_dropped_skills()
        no_url_count = JDExtractionRecord.objects.filter(
            status=JDExtractionRecord.STATUS_DONE
        ).exclude(result=None).filter(source_url="").count()
        if no_url_count:
            self.stdout.write(
                f"  {no_url_count} records skipped (no source_url in extraction record)"
            )

    # 023/3.2 (A10/A11): skills the normalizer can't map were dropped SILENTLY —
    # that's how catalog jobs end up with degenerate 2-skill profiles that fool
    # every skill feature. Count and report every drop.
    _dropped_skills: dict[str, int] = {}

    def _replace_job_skills(self, job_id, skills, normalizer, skill_cache):
        from apps.jobs.models import JobSkill

        rows = []
        for s in skills:
            name       = s["name"] if isinstance(s, dict) else str(s)
            importance = int(s.get("importance", 3)) if isinstance(s, dict) else 3
            canonical  = normalizer.normalize(name)
            if canonical and canonical in skill_cache:
                rows.append(JobSkill(
                    job_id=job_id,
                    skill=skill_cache[canonical],
                    importance=max(1, min(5, importance)),
                ))
            else:
                key = name.strip().lower()
                self._dropped_skills[key] = self._dropped_skills.get(key, 0) + 1

        if rows:
            JobSkill.objects.filter(job_id=job_id).delete()
            JobSkill.objects.bulk_create(rows, ignore_conflicts=True)

    def _report_dropped_skills(self):
        if not self._dropped_skills:
            return
        total = sum(self._dropped_skills.values())
        top = sorted(self._dropped_skills.items(), key=lambda x: -x[1])[:15]
        self.stdout.write(self.style.WARNING(
            f"  SKILL DROPS (A10): {total} mentions of {len(self._dropped_skills)} "
            f"non-catalog skills dropped. Top: "
            + ", ".join(f"{n}×{c}" for n, c in top)
            + " — extend ml_service/data/skill-alias.json if these matter."
        ))

    # ── CVs ───────────────────────────────────────────────────────────────────

    def _sync_cvs(self, normalizer, skill_cache, dry_run):
        from apps.cvs.models import CV, CVSkill, CVExtractionRecord

        self.stdout.write("\nSyncing CVs...")

        # One extraction record per CV — keep the latest done record per CV
        cv_to_rec: dict[int, CVExtractionRecord] = {}
        for rec in (
            CVExtractionRecord.objects
            .filter(status=CVExtractionRecord.STATUS_DONE)
            .exclude(result=None)
            .order_by("cv_id", "-id")   # latest first per cv
            .only("id", "cv_id", "result")
        ):
            if rec.cv_id not in cv_to_rec:
                cv_to_rec[rec.cv_id] = rec

        self.stdout.write(f"  {len(cv_to_rec)} CVs with done extraction records")

        updated = 0
        for cv_id, rec in cv_to_rec.items():
            r = rec.result

            exp_years   = float(r.get("experience_years") or 0)
            seniority_raw = r.get("seniority", -1)
            if not isinstance(seniority_raw, int) or seniority_raw < 0:
                seniority = _seniority_from_years(exp_years)
            else:
                seniority = _clamp_int(seniority_raw, 0, 5, 2)

            education   = _clamp_int(r.get("education"), 0, 4, 2)
            role_cat    = (r.get("role_category") or "other")[:20]
            name        = (r.get("name") or "")[:200]
            work_exp    = r.get("work_experience") or []

            if not dry_run:
                CV.objects.filter(id=cv_id).update(
                    candidate_name=name,
                    seniority=seniority,
                    experience_years=exp_years,
                    education=education,
                    role_category=role_cat,
                    work_experience=work_exp,
                )
                self._replace_cv_skills(
                    cv_id, r.get("skills") or [], normalizer, skill_cache
                )
                updated += 1

        self.stdout.write(f"  updated={updated}")
        self.stdout.write(self.style.SUCCESS("\nDone!"))

    def _replace_cv_skills(self, cv_id, skills, normalizer, skill_cache):
        from apps.cvs.models import CVSkill

        rows = []
        for s in skills:
            name        = s["name"] if isinstance(s, dict) else str(s)
            proficiency = int(s.get("proficiency", 3)) if isinstance(s, dict) else 3
            canonical   = normalizer.normalize(name)
            if canonical and canonical in skill_cache:
                rows.append(CVSkill(
                    cv_id=cv_id,
                    skill=skill_cache[canonical],
                    proficiency=max(1, min(5, proficiency)),
                ))

        if rows:
            CVSkill.objects.filter(cv_id=cv_id).delete()
            CVSkill.objects.bulk_create(rows, ignore_conflicts=True)
