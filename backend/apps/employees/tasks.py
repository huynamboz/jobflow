"""Celery tasks for the Employee MVP.

``parse_and_match_employee`` is enqueued after each Employee record is
created (single or bulk). It parses the CV, populates structured fields,
and creates EmployeeJobMatch records for the top-K suggested jobs.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.employees.matching import match_employee_to_jobs
from apps.employees.models import Employee, EmployeeJobMatch
from apps.employees.parsers import parse_cv_file

logger = logging.getLogger(__name__)


def _do_parse_and_match(employee_id: int) -> dict:
    """Synchronous worker — also reused by the management command."""
    try:
        emp = Employee.objects.get(pk=employee_id)
    except Employee.DoesNotExist:
        return {"employee_id": employee_id, "skipped": "not_found"}

    parsed = parse_cv_file(emp.cv_file) if emp.cv_file else {}
    if parsed:
        emp.skills = parsed.get("skills", emp.skills)
        if "seniority" in parsed:
            emp.seniority = parsed["seniority"]
        if "experience_years" in parsed:
            emp.experience_years = parsed["experience_years"]
        emp.parsed_at = timezone.now()
        emp.is_parse_failed = False
    else:
        emp.is_parse_failed = bool(emp.cv_file)  # only mark failed if there was a file
    emp.save()

    matches = match_employee_to_jobs(emp, top_k=30)
    created = 0
    for m in matches:
        _, was_created = EmployeeJobMatch.objects.update_or_create(
            employee=emp,
            job_id=m["job_id"],
            defaults={
                "status": EmployeeJobMatch.Status.SUGGESTED,
                "match_score": float(m.get("score", 0.0)),
                "matched_skills": m.get("matched_skills", []),
            },
        )
        if was_created:
            created += 1
    return {"employee_id": employee_id, "matches_total": len(matches), "matches_created": created}


try:
    from celery import shared_task  # type: ignore
except ImportError:  # pragma: no cover - celery optional in some envs
    shared_task = None  # type: ignore


if shared_task is not None:

    @shared_task(bind=True, max_retries=2, default_retry_delay=120)
    def parse_and_match_employee(self, employee_id: int):
        try:
            return _do_parse_and_match(employee_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("parse_and_match_employee failed for %s", employee_id)
            raise self.retry(exc=exc)
