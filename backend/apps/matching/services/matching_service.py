"""Matching service — singleton wrapper around ml_service InferenceEngine.

CV parsing uses LLMCVParser (LLM-based extraction) instead of the rule-based CVParser.
Loads model and parser once, reuses across requests.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_engine = None
_parser = None
_lock = threading.Lock()


def _get_engine():
    """Lazy-load InferenceEngine singleton."""
    global _engine
    if _engine is not None:
        # Feature 018: pick up a newer live job-pool snapshot without a restart.
        try:
            _engine.maybe_reload_job_pool()
        except Exception as exc:  # noqa: BLE001
            logger.warning("job-pool hot-reload skipped: %s", exc)
        return _engine

    with _lock:
        if _engine is not None:
            return _engine

        from ml_service.data.skill_normalization import SkillNormalizer
        from ml_service.embedding import get_provider
        from ml_service.inference import InferenceEngine

        logger.info("Loading ML engine from %s...", settings.ML_CHECKPOINT_DIR)
        normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
        provider = get_provider()

        _engine = InferenceEngine.from_checkpoint(
            settings.ML_CHECKPOINT_DIR,
            normalizer=normalizer,
            embedding_provider=provider,
        )
        logger.info("ML engine ready: %d CVs, %d jobs", _engine.num_cvs, _engine.num_jobs)

        # Override checkpoint job skills with DB canonical skills (more accurate)
        try:
            _refresh_job_skills_from_db(_engine)
        except Exception as e:
            logger.warning("Job skill refresh skipped: %s", e)

        return _engine


def _refresh_job_skills_from_db(engine) -> None:
    """No-op: engine job_id = JDExtractionRecord.id, not Job.id.

    JobSkill is keyed by Job.id, which differs from JDExtractionRecord.id after
    rebuild_jobs deleted duplicates and reassigned IDs. Checkpoint skills are
    already LLM-extracted canonical skills from the labeling pipeline — no refresh needed.
    """
    logger.info("Skill refresh skipped: checkpoint already has LLM-canonical skills.")


def _get_parser():
    """Lazy-load LLMCVParser singleton."""
    global _parser
    if _parser is not None:
        return _parser

    with _lock:
        if _parser is not None:
            return _parser

        from ml_service.data.skill_normalization import SkillNormalizer
        from apps.matching.services.llm_cv_parser import LLMCVParser

        normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
        _parser = LLMCVParser(normalizer)
        return _parser


_SOFT_SKILLS = frozenset({
    "communication", "teamwork", "leadership", "problem_solving",
    "time_management", "agile", "security",
})


def _clean_title(raw: str) -> str:
    """Return first non-empty line of title (strips LinkedIn card metadata)."""
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return raw.strip()


def _filter_soft_skills(skills: list[str]) -> list[str]:
    return [s for s in skills if s not in _SOFT_SKILLS]


# Re-export for callers that already imported from this module.
from apps.matching.lifecycle_filter import filter_active_jobs as _filter_active_jobs  # noqa: E402, F401


def _build_lifecycle_map(jd_ids: list[int]) -> dict[int, str]:
    """Build {jd_id: lifecycle} by joining JDExtractionRecord.source_url with
    Job.source_url. Falls back to 'unverified' on missing matches.

    Returns an empty dict if anything in the lookup chain fails; the caller
    treats this as "everything stays".
    """
    try:
        from apps.jobs.models import JDExtractionRecord, Job
        jd_rows = list(
            JDExtractionRecord.objects.filter(id__in=jd_ids).values("id", "source_url")
        )
        url_to_jd_ids: dict[str, list[int]] = {}
        for r in jd_rows:
            url = (r["source_url"] or "").strip()
            if url:
                url_to_jd_ids.setdefault(url, []).append(r["id"])
        if not url_to_jd_ids:
            return {}
        job_rows = Job.objects.filter(source_url__in=url_to_jd_ids.keys()).values(
            "source_url", "lifecycle"
        )
        lifecycle_map: dict[int, str] = {}
        for row in job_rows:
            for jd_id in url_to_jd_ids.get(row["source_url"], ()):
                lifecycle_map[jd_id] = row["lifecycle"]
        return lifecycle_map
    except Exception:
        logger.exception("Failed to build lifecycle map; matching results will not be filtered")
        return {}


def _enrich(results) -> list[dict]:
    """Enrich raw match results with job metadata.

    Feature 018: the engine `job_id` is now a live `Job.id` (job pool rebuilt from
    the catalog), so metadata comes straight from `Job`. A legacy fallback to
    `JDExtractionRecord`/`LabelingJob` is kept for any id that doesn't resolve to a
    live Job (e.g. the frozen checkpoint pool when no snapshot has been built yet),
    so this works during the transition either way."""
    from apps.jobs.models import JDExtractionRecord, Job
    from apps.labeling.models import LabelingJob

    ids = [r.job_id for r in results]
    job_map = {j.id: j for j in Job.objects.select_related("company").filter(id__in=ids)}

    legacy_ids = [i for i in ids if i not in job_map]
    jd_map = {jd.id: jd for jd in JDExtractionRecord.objects.filter(id__in=legacy_ids)} if legacy_ids else {}
    lj_map = {lj.job_id: lj for lj in LabelingJob.objects.filter(job_id__in=legacy_ids)} if legacy_ids else {}

    enriched = []
    for r in results:
        common = {
            "job_id":          r.job_id,
            "score":           r.score,
            "eligible":        r.eligible,
            "match_level":     r.match_level,
            "dim_scores":      r.dim_scores,
            "matched_skills":  _filter_soft_skills(list(r.matched_skills)),
            "missing_skills":  _filter_soft_skills(list(r.missing_skills)),
            "seniority_match": r.seniority_match,
        }

        job = job_map.get(r.job_id)
        if job is not None:
            enriched.append({
                **common,
                "title":           _clean_title(job.title or r.title or ""),
                "company_name":    (job.company.name if job.company_id else "") or "",
                "location":        job.location or "",
                "job_type":        job.job_type or "",
                "salary_min":      int(job.salary_min or 0),
                "salary_max":      int(job.salary_max or 0),
                "salary_currency": job.salary_currency or "USD",
                "role_category":   job.role_category or "",
                "experience_min":  job.experience_min,
                "experience_max":  job.experience_max,
                "source_url":      job.source_url or "",
            })
            continue

        # ---- legacy JDExtractionRecord / LabelingJob fallback ----
        jd  = jd_map.get(r.job_id)
        lj  = lj_map.get(r.job_id)
        res = (jd.result   or {}) if jd else {}
        raw = (jd.raw_data or {}) if jd else {}
        title = _clean_title(
            (lj.title if lj else None) or res.get("title") or raw.get("title") or r.title or ""
        )
        enriched.append({
            **common,
            "title":           title,
            "company_name":    res.get("company") or raw.get("company") or "",
            "location":        res.get("location") or raw.get("location") or "",
            "job_type":        res.get("job_type") or raw.get("job_type") or "",
            "salary_min":      int(res.get("salary_min") or raw.get("salary_min") or 0),
            "salary_max":      int(res.get("salary_max") or raw.get("salary_max") or 0),
            "salary_currency": res.get("salary_currency") or "USD",
            "role_category":   (lj.role_category if lj else None) or "",
            "experience_min":  (lj.experience_min if lj else None) or res.get("experience_min"),
            "experience_max":  (lj.experience_max if lj else None) or res.get("experience_max"),
            "source_url":      (jd.source_url if jd else None) or raw.get("source_url") or raw.get("job_url") or "",
        })
    return enriched


def _cv_info(cv_data) -> dict:
    return {
        "skills": list(cv_data.skills),
        "seniority": cv_data.seniority.name,
        "experience_years": cv_data.experience_years,
        "education": cv_data.education.name,
    }


def _apply_lifecycle_filter(results):
    """Drop expired jobs (lifecycle filter). Preserves original ranking order."""
    jd_ids = [r.job_id for r in results]
    if not jd_ids:
        return results
    lifecycle_map = _build_lifecycle_map(jd_ids)
    if not lifecycle_map:  # build failed or no DB rows — keep all
        return results
    keep_ids = set(_filter_active_jobs(jd_ids, lifecycle_map=lifecycle_map))
    return [r for r in results if r.job_id in keep_ids]


def match_cv_text(cv_text: str, top_k: int = 10) -> dict:
    """Match CV text against all jobs. Returns {cv_info, jobs}."""
    parser = _get_parser()
    cv_data = parser.parse_text(cv_text, cv_id=-1)
    engine = _get_engine()
    # Over-fetch so the lifecycle filter doesn't shrink the response below top_k.
    raw = engine.match_cv(cv_data, top_k=top_k * 2)
    filtered = _apply_lifecycle_filter(raw)[:top_k]
    return {"cv_info": _cv_info(cv_data), "jobs": _enrich(filtered)}


def match_cv_file(file_path: str, top_k: int = 10) -> dict:
    """Parse CV file (PDF/DOCX) and match against all jobs. Returns {cv_info, jobs}."""
    parser = _get_parser()
    cv_data = parser.parse_file(file_path)
    if not cv_data.skills:
        return {"cv_info": _cv_info(cv_data), "jobs": []}

    engine = _get_engine()
    raw = engine.match_cv(cv_data, top_k=top_k * 2)
    filtered = _apply_lifecycle_filter(raw)[:top_k]
    return {"cv_info": _cv_info(cv_data), "jobs": _enrich(filtered)}


def build_jobdata_from_db(limit: int | None = None):
    """Build engine ``JobData`` from the live ``Job`` catalog (feature 018).

    Maps ``Job`` + ``JobSkill`` → ``JobData`` with ``job_id = Job.id`` (the single
    match identifier going forward). Jobs with no skills are skipped — they can't
    form graph edges and would only get a text-only embedding. Skill names are
    taken from the ``Skill`` rows; any not in the model's catalog are dropped at
    encode time (graceful)."""
    from apps.jobs.models import Job
    from ml_service.graph.schema import JobData, SeniorityLevel

    qs = Job.objects.filter(is_active=True).prefetch_related("job_skills__skill").order_by("id")
    if limit:
        qs = qs[:limit]

    jobs: list = []
    for job in qs:
        pairs = [(js.skill.canonical_name, int(js.importance)) for js in job.job_skills.all() if js.skill_id]
        if not pairs:
            continue
        skills = tuple(name for name, _ in pairs)
        importances = tuple(imp for _, imp in pairs)
        text = f"{job.title}. {job.description}".strip()
        jobs.append(
            JobData(
                job_id=job.id,
                seniority=SeniorityLevel(max(0, min(5, int(job.seniority)))),
                skills=skills,
                skill_importances=importances,
                salary_min=int(job.salary_min or 0),
                salary_max=int(job.salary_max or 0),
                text=text,
                # 021/A1: without these the experience gate + experience_fit were
                # silent no-ops on the whole live pool.
                experience_min=float(job.experience_min or 0.0),
                experience_max=float(job.experience_max) if job.experience_max is not None else None,
                role_category=(job.role_category or "").lower(),
            )
        )
    return jobs


def match_cv_data(
    skills: list[str],
    seniority: int,
    experience_years: float = 0.0,
    education: int = 2,
    text: str | None = None,
    top_k: int = 10,
) -> dict:
    """Match using already-structured CV fields, **skipping the LLM parse**, then
    run the exact same GNN pipeline (``engine.match_cv``) as the full CV path.

    ``text`` is the CV free-text used for the CV-node sentence embedding — pass
    the original CV text (re-extracted from the file, no LLM) for parity with the
    full path; it is truncated to 500 words exactly like ``LLMCVParser``. When no
    text is given it falls back to a skills-joined string (skill graph signal is
    unaffected either way). ``education``/proficiency default when not stored.
    Returns {cv_info, jobs}."""
    from ml_service.graph.schema import CVData, EducationLevel, SeniorityLevel

    canonical = [s for s in (skills or []) if s]
    if not canonical:
        return {"cv_info": {}, "jobs": []}

    if text:
        words = text.split()
        embed_text = " ".join(words[:500]) if len(words) > 500 else text
    else:
        embed_text = ", ".join(canonical)

    cv = CVData(
        cv_id=-1,
        seniority=SeniorityLevel(max(0, min(5, int(seniority)))),
        experience_years=float(experience_years or 0),
        education=EducationLevel(education),
        skills=tuple(canonical),
        skill_proficiencies=tuple(3 for _ in canonical),
        text=embed_text,
    )
    engine = _get_engine()
    raw = engine.match_cv(cv, top_k=top_k * 2)
    filtered = _apply_lifecycle_filter(raw)[:top_k]
    return {"cv_info": _cv_info(cv), "jobs": _enrich(filtered)}


def parse_cv_file(file_path: str) -> dict:
    """Parse CV file and return structured data (debug)."""
    parser = _get_parser()
    cv = parser.parse_file(file_path)
    return {
        "seniority": cv.seniority.name,
        "experience_years": cv.experience_years,
        "education": cv.education.name,
        "skills": list(cv.skills),
    }


def parse_cv_text(cv_text: str) -> dict:
    """Parse CV text and return structured data (debug)."""
    parser = _get_parser()
    cv = parser.parse_text(cv_text)
    return {
        "seniority": cv.seniority.name,
        "experience_years": cv.experience_years,
        "education": cv.education.name,
        "skills": list(cv.skills),
    }
