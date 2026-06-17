"""Adapter calling the existing matching pipeline for an Employee.

Returns a list of dicts ``{job_id, score, matched_skills, missing_skills}`` for
the top K jobs. ``missing_skills`` powers the explainability panel (feature 014)
and is sourced directly from the matching engine, which already computes it.
Falls back to an empty list when the matching service is unavailable so the
bulk-upload flow degrades gracefully.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _jobs_to_dicts(result: Any) -> list[dict]:
    if isinstance(result, dict) and "by_platform" in result:
        # per-platform ranking: flatten each platform's top-K into one list,
        # dedup by job_id, preserving per-platform order. Each platform keeps its
        # own top-K so small platforms aren't crowded out of the persisted set.
        jobs, seen = [], set()
        for plat_jobs in result["by_platform"].values():
            for j in plat_jobs:
                jid = j.get("job_id")
                if jid is not None and jid not in seen:
                    seen.add(jid)
                    jobs.append(j)
    else:
        jobs = result.get("jobs", []) if isinstance(result, dict) else (result or [])
    return [
        {
            "job_id": j.get("job_id"),
            # source_url is the real link between the engine's JDExtractionRecord
            # space and the admin Job catalog — kept so matches resolve to the
            # right Job (engine job_id rarely equals Job.pk).
            "source_url": j.get("source_url") or "",
            "score": j.get("score", 0.0),
            "matched_skills": j.get("matched_skills", []),
            "missing_skills": j.get("missing_skills", []),
            "covered_skills": j.get("covered_skills", {}),
            "score_breakdown": j.get("score_breakdown", {}),
            "dim_scores": j.get("dim_scores") or {},
        }
        for j in jobs
        if j.get("job_id") is not None
    ]


def rematch_employee(employee: Any, top_k: int = 30, per_platform: bool = False,
                     per_platform_k: int = 50) -> list[dict]:
    """Re-match using the employee's already-parsed skills/seniority — **no LLM
    call** — through the same GNN pipeline. The CV file's text is re-extracted
    (no LLM) so the CV-node embedding matches the full path; falls back to a
    skills-joined string for employees without a file. Cheap enough to run in
    bulk / on a schedule when the catalog changes.

    ``per_platform``: rank top-``per_platform_k`` WITHIN each platform separately
    (so every platform is represented), then flatten for persistence. When False,
    keeps the original single global top-``top_k`` ranking."""
    try:
        from apps.employees.parsers import extract_text_from_cv
        from apps.matching.services import match_cv_data  # type: ignore

        cv_text = extract_text_from_cv(employee.cv_file) if employee.cv_file else ""
        result = match_cv_data(
            skills=list(employee.skills or []),
            seniority=int(employee.seniority),
            experience_years=float(employee.experience_years or 0),
            text=cv_text or None,
            top_k=top_k,
            position=employee.position or "",  # 025: deterministic role source
            group_by_platform=per_platform,
            per_platform_k=per_platform_k,
        )
        return _jobs_to_dicts(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Re-match unavailable for employee %s: %s", employee.pk, exc)
        return []
