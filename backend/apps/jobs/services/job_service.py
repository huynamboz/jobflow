"""Job service: RawJob → DB (Platform + Company + Job + Skills)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.db import transaction

from apps.jobs.models import Job, JobSkill, Platform
from apps.jobs.services.platform_service import PlatformService
from apps.skills.services import SkillService

if TYPE_CHECKING:
    from ml_service.crawler.base import RawJob

logger = logging.getLogger(__name__)

# Map crawl source names to platform info
_PLATFORM_MAP = {
    "indeed": {"name": "Indeed", "base_url": "https://indeed.com", "logo_url": "https://www.google.com/s2/favicons?domain=indeed.com&sz=128"},
    "linkedin": {"name": "LinkedIn", "base_url": "https://linkedin.com", "logo_url": "https://www.google.com/s2/favicons?domain=linkedin.com&sz=128"},
    "adzuna": {"name": "Adzuna", "base_url": "https://adzuna.com", "logo_url": "https://www.google.com/s2/favicons?domain=adzuna.com&sz=128"},
    "remotive": {"name": "Remotive", "base_url": "https://remotive.com", "logo_url": "https://www.google.com/s2/favicons?domain=remotive.com&sz=128"},
    "freelancer": {"name": "Freelancer", "base_url": "https://freelancer.com", "logo_url": "https://www.google.com/s2/favicons?domain=freelancer.com&sz=128"},
    "remoteok": {"name": "RemoteOK", "base_url": "https://remoteok.com", "logo_url": "https://www.google.com/s2/favicons?domain=remoteok.com&sz=128"},
}


class JobService:
    """Save crawled jobs to DB with auto-create Platform/Company/Skills."""

    def __init__(self):
        from ml_service.crawler.storage import compute_fingerprint
        from ml_service.data.skill_normalization import SkillNormalizer

        self._normalizer = SkillNormalizer()
        self._compute_fingerprint = compute_fingerprint
        self._skill_service = SkillService()

    def _llm_extract(self, raw: "RawJob") -> dict:
        """Call the LLM JD extractor → a plain dict (or {} on failure)."""
        from apps.jobs.services.llm_jd_extractor import extract as llm_jd_extract
        try:
            r = llm_jd_extract(f"{raw.title}\n\n{raw.description}".strip())
        except Exception as e:  # noqa: BLE001 — still import the job, just without rich fields
            logger.warning("LLM JD extraction failed for %r: %s", (raw.title or "")[:60], e)
            return {}
        return {
            "seniority": r.seniority, "role_category": r.role_category, "job_type": r.job_type,
            "experience_min": r.experience_min, "experience_max": r.experience_max,
            "salary_min": r.salary_min, "salary_max": r.salary_max,
            "salary_type": r.salary_type, "skills": r.skills,
        }

    def save_raw_job(self, raw: "RawJob", extracted: dict | None = None,
                     skip_non_tech: bool = True, dry_run: bool = False) -> "Job | bool | None":
        """Save a single RawJob to DB. `extracted` (pre-computed JD fields) skips
        the LLM; pass None to extract via LLM. With `skip_non_tech`, drops noise
        jobs (role 'other' with < 2 canonical skills — won't rank anyway).
        Returns Job, or None if duplicate / filtered.

        With `dry_run=True`, runs the SAME dedup + non-tech checks read-only (no
        platform/company/job rows written) and returns True for "would import",
        None for "would be skipped" — so a preview reflects real DB dedup."""
        # Get or create platform (read-only in dry_run — a missing platform means
        # no existing jobs for it, so the fingerprint can't be a duplicate).
        source = raw.source or "unknown"
        platform_info = _PLATFORM_MAP.get(source, {"name": source.title(), "base_url": ""})
        if dry_run:
            slug = re.sub(r"[^a-z0-9]+", "-", platform_info["name"].lower()).strip("-")
            platform = Platform.objects.filter(slug=slug).first()
        else:
            platform = PlatformService.get_or_create_platform(**platform_info)

        # Compute fingerprint
        fingerprint = self._compute_fingerprint(raw)

        # Check duplicate per platform (skip if platform doesn't exist yet in dry_run)
        if platform is not None and Job.objects.filter(platform=platform, fingerprint=fingerprint).exists():
            return None

        # Get or create company (with industry/size from extra) — skip writes in dry_run
        extra = raw.extra if hasattr(raw, "extra") and isinstance(raw.extra, dict) else {}
        company = None
        if not dry_run:
            company = PlatformService.get_or_create_company(
                name=raw.company,
                platform=platform,
                logo_url=getattr(raw, "company_logo_url", ""),
                profile_url=getattr(raw, "company_url", ""),
                industry=extra.get("company_industry", ""),
                size=extra.get("company_size", ""),
            )

        # Structured fields. `extracted` may be supplied pre-computed (e.g. by the
        # agent-extract pipeline → import_extracted) to skip the LLM; otherwise we
        # call the LLM JD extractor here (one call per job).
        if extracted is None:
            extracted = self._llm_extract(raw)

        seniority = extracted.get("seniority")
        if seniority is None:
            seniority = Job.Seniority.MID
        role_category = (extracted.get("role_category") or "other")
        exp_min = extracted.get("experience_min")
        exp_max = extracted.get("experience_max")
        # Prefer the provider's real salary; fall back to the extracted one. The
        # pay period follows whichever source supplied the number, so the USD-annual
        # equivalent is computed against the right interval.
        from apps.jobs.services.salary_normalizer import canonical_period, normalize_salary_range
        if raw.salary_min or raw.salary_max:
            salary_min = int(raw.salary_min or 0)
            salary_max = int(raw.salary_max or 0)
            salary_period = canonical_period(getattr(raw, "salary_interval", None))
        else:
            salary_min = int(extracted.get("salary_min") or 0)
            salary_max = int(extracted.get("salary_max") or 0)
            salary_period = canonical_period(extracted.get("salary_type"))
        usd_annual_min, usd_annual_max = normalize_salary_range(
            salary_min, salary_max, raw.salary_currency, salary_period)

        # job_type: provider value first, else extracted, normalized to a valid choice
        jt_raw = (getattr(raw, "job_type", "") or extracted.get("job_type") or "").lower()
        job_type = Job.JobType.OTHER
        for choice in Job.JobType.values:
            if choice and choice in jt_raw:
                job_type = choice
                break

        # Normalize skills to canonical names (unknown → dropped) up front.
        norm_skills: list[tuple[str, int]] = []
        for s in (extracted.get("skills") or []):
            if not isinstance(s, dict):
                continue
            name = self._normalizer.normalize((s.get("name") or "").strip())
            if name:
                norm_skills.append((name, max(1, min(5, int(s.get("importance") or 3)))))

        # Filter noise: a role-'other' job with < 2 canonical skills won't rank
        # (pool needs ≥2 skills) — usually a non-IT posting that leaked in.
        if skip_non_tech and role_category == "other" and len(norm_skills) < 2:
            return None

        # Passed dedup + non-tech checks → would import. Stop here in dry_run.
        if dry_run:
            return True

        with transaction.atomic():
            job = Job.objects.create(
                platform=platform,
                company=company,
                title=raw.title,
                description=raw.description[:10000],
                location=raw.location,
                seniority=seniority,
                job_type=job_type,
                role_category=role_category,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=raw.salary_currency,
                salary_period=salary_period,
                salary_usd_annual_min=usd_annual_min,
                salary_usd_annual_max=usd_annual_max,
                experience_min=exp_min,
                experience_max=exp_max,
                source_url=raw.source_url,
                fingerprint=fingerprint,
                applicant_count=getattr(raw, "applicant_count", ""),
                date_posted=raw.date_posted,
            )
            for name, importance in norm_skills:
                skill = self._skill_service.get_or_create(name)
                if skill:
                    JobSkill.objects.get_or_create(
                        job=job, skill=skill, defaults={"importance": importance},
                    )

        return job

    def save_raw_jobs_batch(self, raws: list["RawJob"]) -> dict:
        """Save multiple RawJobs. Returns stats."""
        created = 0
        skipped = 0
        failed = 0

        for raw in raws:
            try:
                job = self.save_raw_job(raw)
                if job:
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Failed to save job '%s': %s", raw.title[:50], e)
                failed += 1

        logger.info("Saved %d jobs (skipped %d duplicates, %d failed)", created, skipped, failed)
        return {"created": created, "skipped": skipped, "failed": failed}

    @staticmethod
    def to_job_data(job: Job):
        """Convert Django Job model → ml_service JobData."""
        from ml_service.graph.schema import JobData

        skills = tuple(job.job_skills.values_list("skill__canonical_name", flat=True))
        importances = tuple(job.job_skills.values_list("importance", flat=True))

        return JobData(
            job_id=job.id,
            seniority=job.seniority,
            skills=skills,
            skill_importances=importances,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            text=f"{job.title}. {job.description[:2000]}",
        )

    @staticmethod
    def get_all_job_data() -> list:
        """Query all active jobs and convert to JobData list."""
        from ml_service.graph.schema import JobData

        jobs = (Job.objects.filter(is_active=True)
                .exclude(lifecycle=Job.LIFECYCLE_EXPIRED)
                .prefetch_related("job_skills__skill"))
        result = []
        for job in jobs:
            skills = tuple(js.skill.canonical_name for js in job.job_skills.all())
            importances = tuple(js.importance for js in job.job_skills.all())
            if len(skills) >= 2:
                result.append(JobData(
                    job_id=job.id,
                    seniority=job.seniority,
                    skills=skills,
                    skill_importances=importances,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    text=f"{job.title}. {job.description[:2000]}",
                ))
        return result
