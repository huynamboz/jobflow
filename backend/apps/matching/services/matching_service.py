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
_pgvector_version = None  # feature 027: last pgvector pool version loaded into the engine


def _get_engine():
    """Lazy-load InferenceEngine singleton."""
    global _engine
    if _engine is not None:
        # feature 027: hot-reload from the pgvector store (the source of truth)
        # when an incremental rebuild upserted deltas — no restart needed.
        try:
            _maybe_reload_from_pgvector(_engine)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pgvector hot-reload skipped: %s", exc)
        # Feature 018: snapshot fallback hot-reload (used when pgvector is absent).
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
            retrieval_mode=getattr(settings, "RETRIEVAL_MODE", "exact"),  # feature 027
            retrieve_k=getattr(settings, "RETRIEVE_K", 1000),
        )
        logger.info("ML engine ready: %d CVs, %d jobs", _engine.num_cvs, _engine.num_jobs)

        # feature 027 (chuẩn prod): pgvector is the pool's source of truth. Load
        # the serving pool from the store (catalog JobData + precomputed embeddings)
        # rather than the on-disk snapshot. Falls back to the snapshot/checkpoint
        # pool already loaded by from_checkpoint if the store is empty/unavailable.
        pool_source = "pgvector" if _load_pool_from_pgvector(_engine) else "snapshot/checkpoint"

        # Override checkpoint job skills with DB canonical skills (more accurate)
        try:
            _refresh_job_skills_from_db(_engine)
        except Exception as e:
            logger.warning("Job skill refresh skipped: %s", e)

        # feature 027: visible one-line summary (logger.info is suppressed by runserver)
        print(f"[ML] retrieval={getattr(settings,'RETRIEVAL_MODE','exact')} "
              f"retrieve_k={getattr(settings,'RETRIEVE_K',1000)} pool_source={pool_source} "
              f"jobs={_engine.num_jobs}", flush=True)

        return _engine


def _maybe_reload_from_pgvector(engine) -> None:
    """Reload the pool from pgvector if its version changed since we last loaded
    (an incremental rebuild upserted deltas). Cheap version poll; full reload only
    on change."""
    global _pgvector_version
    from ml_service.inference import pgvector_store
    if not pgvector_store.available():
        return
    ver = pgvector_store.pool_version(engine.model_signature)
    if ver != _pgvector_version and ver != "0:0":
        logger.info("pgvector pool changed (%s → %s) — reloading", _pgvector_version, ver)
        _load_pool_from_pgvector(engine)


def _load_pool_from_pgvector(engine) -> bool:
    """Load the serving pool from the pgvector store: catalog JobData aligned with
    the precomputed embeddings by job_id. A job in the catalog but not yet in the
    store (encoded after the last rebuild) is simply not rankable until the next
    rebuild upserts it. Returns True if the pool was loaded from the store."""
    global _pgvector_version
    try:
        import numpy as np
        import torch

        from ml_service.inference import pgvector_store
        if not pgvector_store.available():
            return False
        stored = pgvector_store.fetch_pool(engine.model_signature)
        if not stored:
            return False
        jobs = build_jobdata_from_db()
        aj, gnn, txt = [], [], []
        for j in jobs:
            e = stored.get(j.job_id)
            if e is None or e[1] is None:
                continue
            aj.append(j); gnn.append(e[0]); txt.append(e[1])
        if not aj:
            return False
        engine.set_job_pool(
            aj,
            torch.tensor(np.asarray(gnn, dtype=np.float32)),
            np.asarray(txt, dtype=np.float32),
        )
        _pgvector_version = pgvector_store.pool_version(engine.model_signature)
        logger.info("pgvector pool: %d rankable (catalog %d, stored %d) ver=%s",
                    len(aj), len(jobs), len(stored), _pgvector_version)
        return True
    except Exception as exc:  # noqa: BLE001 — never break startup on a store issue
        logger.warning("pgvector pool load failed (%s) — keeping snapshot/checkpoint pool", exc)
        return False


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
            "covered_skills":  {k: v for k, v in (r.covered_skills or {}).items()},
            "score_breakdown": dict(r.score_breakdown or {}),
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
                "salary_period":   job.salary_period or "unknown",
                "salary_usd_annual_min": int(job.salary_usd_annual_min or 0),
                "salary_usd_annual_max": int(job.salary_usd_annual_max or 0),
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
        from apps.jobs.services.salary_normalizer import canonical_period, normalize_salary_range
        _smin = int(res.get("salary_min") or raw.get("salary_min") or 0)
        _smax = int(res.get("salary_max") or raw.get("salary_max") or 0)
        _scur = res.get("salary_currency") or "USD"
        _sper = canonical_period(res.get("salary_type") or raw.get("salary_interval"))
        _usd_min, _usd_max = normalize_salary_range(_smin, _smax, _scur, _sper)
        enriched.append({
            **common,
            "title":           title,
            "company_name":    res.get("company") or raw.get("company") or "",
            "location":        res.get("location") or raw.get("location") or "",
            "job_type":        res.get("job_type") or raw.get("job_type") or "",
            "salary_min":      _smin,
            "salary_max":      _smax,
            "salary_currency": _scur,
            "salary_period":   _sper,
            "salary_usd_annual_min": _usd_min,
            "salary_usd_annual_max": _usd_max,
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


def _dedup_by_title_company(enriched: list[dict]) -> list[dict]:
    """021/A9 serving guard: drop repeats of the same posting (normalized
    title + company) beyond the first — the catalog can contain duplicate rows
    the cleanup hasn't caught (cross-platform reposts)."""
    seen: set[tuple[str, str]] = set()
    out = []
    for item in enriched:
        key = ((item.get("title") or "").strip().lower(),
               (item.get("company_name") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _rank_by_platform(engine, cv, per_platform_k: int = 50) -> dict:
    """Rank the CV WITHIN each platform separately → {platform_name: [jobs]}.

    Encodes the CV once, then reranks each platform's pool slice independently so
    a small platform (e.g. Remotive, 23 jobs) isn't crowded out of a single global
    top-K by larger platforms' higher-ranked matches. Each slice goes through the
    SAME exact composite + reranker + Platt pipeline (model untouched)."""
    from collections import defaultdict

    from apps.jobs.models import Job

    pool = engine._jobs
    if not pool:
        return {}
    plat_by_id = dict(
        Job.objects.filter(id__in=[j.job_id for j in pool]).values_list("id", "platform__name")
    )
    idxs_by_plat: dict[str, set] = defaultdict(set)
    for i, jd in enumerate(pool):
        idxs_by_plat[plat_by_id.get(jd.job_id) or "Unknown"].add(i)

    precomputed = engine.encode_cv(cv)  # GNN inductive encode ONCE, reused per slice
    out: dict[str, list] = {}
    for name in sorted(idxs_by_plat):
        idxs = idxs_by_plat[name]
        # over-fetch (×2) so the lifecycle filter doesn't shrink a slice below k
        raw = engine.match_cv(cv, top_k=per_platform_k * 2, restrict_idxs=idxs, precomputed=precomputed)
        out[name] = _dedup_by_title_company(_enrich(_apply_lifecycle_filter(raw)))[:per_platform_k]
    return out


def match_cv_text(cv_text: str, top_k: int = 10, group_by_platform: bool = False,
                  per_platform_k: int = 50) -> dict:
    """Match CV text against all jobs. Returns {cv_info, jobs} — or, with
    ``group_by_platform``, {cv_info, by_platform: {platform: [jobs]}}."""
    parser = _get_parser()
    cv_data = parser.parse_text(cv_text, cv_id=-1)
    engine = _get_engine()
    if group_by_platform:
        return {"cv_info": _cv_info(cv_data), "by_platform": _rank_by_platform(engine, cv_data, per_platform_k)}
    # Over-fetch so the lifecycle filter doesn't shrink the response below top_k.
    raw = engine.match_cv(cv_data, top_k=top_k * 2)
    jobs = _dedup_by_title_company(_enrich(_apply_lifecycle_filter(raw)))[:top_k]
    return {"cv_info": _cv_info(cv_data), "jobs": jobs}


def match_cv_file(file_path: str, top_k: int = 10, group_by_platform: bool = False,
                  per_platform_k: int = 50) -> dict:
    """Parse CV file (PDF/DOCX) and match against all jobs. Returns {cv_info, jobs}
    — or, with ``group_by_platform``, {cv_info, by_platform: {platform: [jobs]}}."""
    parser = _get_parser()
    cv_data = parser.parse_file(file_path)
    if not cv_data.skills:
        empty = {"by_platform": {}} if group_by_platform else {"jobs": []}
        return {"cv_info": _cv_info(cv_data), **empty}

    engine = _get_engine()
    if group_by_platform:
        return {"cv_info": _cv_info(cv_data), "by_platform": _rank_by_platform(engine, cv_data, per_platform_k)}
    raw = engine.match_cv(cv_data, top_k=top_k * 2)
    jobs = _dedup_by_title_company(_enrich(_apply_lifecycle_filter(raw)))[:top_k]
    return {"cv_info": _cv_info(cv_data), "jobs": jobs}


def build_jobdata_from_db(limit: int | None = None):
    """Build engine ``JobData`` from the live ``Job`` catalog (feature 018).

    Maps ``Job`` + ``JobSkill`` → ``JobData`` with ``job_id = Job.id`` (the single
    match identifier going forward). Jobs with no skills are skipped — they can't
    form graph edges and would only get a text-only embedding. Skill names are
    taken from the ``Skill`` rows; any not in the model's catalog are dropped at
    encode time (graceful)."""
    from apps.jobs.models import Job
    from ml_service.graph.schema import JobData, SeniorityLevel

    # Exclude lifecycle=expired explicitly so a verified-dead job never ranks even
    # if the legacy is_active flag drifts out of sync.
    qs = (Job.objects.filter(is_active=True)
          .exclude(lifecycle=Job.LIFECYCLE_EXPIRED)
          .prefetch_related("job_skills__skill").order_by("id"))
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
        # GNN job-node salary feature wants a CONSISTENT scale: the model was
        # trained on USD-annual salaries, so feed the normalized USD-annual value
        # (fall back to the raw number when we couldn't normalize it).
        sal_min = int(job.salary_usd_annual_min or job.salary_min or 0)
        sal_max = int(job.salary_usd_annual_max or job.salary_max or 0)
        jobs.append(
            JobData(
                job_id=job.id,
                seniority=SeniorityLevel(max(0, min(5, int(job.seniority)))),
                skills=skills,
                skill_importances=importances,
                salary_min=sal_min,
                salary_max=sal_max,
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
    position: str = "",
    group_by_platform: bool = False,
    per_platform_k: int = 50,
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

    # 025: role decided HERE, once, from stable structured fields (skills +
    # position/title) — never from the free text, whose "Skills: react, ..."
    # dumps used to trip the title regexes and flip the role per call path.
    from ml_service.inference.role_classifier import infer_role

    cv = CVData(
        cv_id=-1,
        seniority=SeniorityLevel(max(0, min(5, int(seniority)))),
        experience_years=float(experience_years or 0),
        education=EducationLevel(education),
        skills=tuple(canonical),
        skill_proficiencies=tuple(3 for _ in canonical),
        text=embed_text,
        role_category=infer_role(tuple(canonical), position or ""),
    )
    engine = _get_engine()
    if group_by_platform:
        return {"cv_info": _cv_info(cv), "by_platform": _rank_by_platform(engine, cv, per_platform_k)}
    raw = engine.match_cv(cv, top_k=top_k * 2)
    jobs = _dedup_by_title_company(_enrich(_apply_lifecycle_filter(raw)))[:top_k]
    return {"cv_info": _cv_info(cv), "jobs": jobs}


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
