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


def match_employee_to_jobs(employee: Any, top_k: int = 30) -> list[dict]:
    try:
        # Construct a "CV text" surrogate from the parsed employee fields and
        # delegate to the matching engine. ``match_cv_text`` returns
        # ``{"cv_info": {...}, "jobs": [{job_id, score, matched_skills,
        # missing_skills, ...}]}``.
        from apps.matching.services import match_cv_text  # type: ignore

        cv_text = _employee_to_cv_text(employee)
        result = match_cv_text(cv_text=cv_text, top_k=top_k)
        jobs = result.get("jobs", []) if isinstance(result, dict) else (result or [])
        return [
            {
                "job_id": j.get("job_id"),
                "score": j.get("score", 0.0),
                "matched_skills": j.get("matched_skills", []),
                "missing_skills": j.get("missing_skills", []),
            }
            for j in jobs
            if j.get("job_id") is not None
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Matching service unavailable for employee %s: %s", employee.pk, exc)
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
