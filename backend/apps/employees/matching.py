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
            "dim_scores": j.get("dim_scores") or {},
        }
        for j in jobs
        if j.get("job_id") is not None
    ]


def match_employee_to_jobs(employee: Any, top_k: int = 30) -> list[dict]:
    """Full match via the CV-text path (LLM parses the surrogate text). Used
    right after a CV is (re)parsed."""
    try:
        from apps.matching.services import match_cv_text  # type: ignore

        cv_text = _employee_to_cv_text(employee)
        return _jobs_to_dicts(match_cv_text(cv_text=cv_text, top_k=top_k))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Matching service unavailable for employee %s: %s", employee.pk, exc)
        return []


def rematch_employee(employee: Any, top_k: int = 30) -> list[dict]:
    """Re-match using the employee's already-parsed skills/seniority — **no LLM
    call** — through the same GNN pipeline. The CV file's text is re-extracted
    (no LLM) so the CV-node embedding matches the full path; falls back to a
    skills-joined string for employees without a file. Cheap enough to run in
    bulk / on a schedule when the catalog changes."""
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
        )
        return _jobs_to_dicts(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Re-match unavailable for employee %s: %s", employee.pk, exc)
        return []


def _employee_to_cv_text(employee: Any) -> str:
    """Compose a CV-like text from employee fields for matchers that want text."""
    skills = ", ".join(employee.skills or [])
    bits = [
        employee.full_name or "",
        employee.position or "",
        f"Seniority: {employee.get_seniority_display() if hasattr(employee, 'get_seniority_display') else employee.seniority}",
        f"Experience: {employee.experience_years or 0} years",
        f"Skills: {skills}",
    ]
    return "\n".join(b for b in bits if b)
