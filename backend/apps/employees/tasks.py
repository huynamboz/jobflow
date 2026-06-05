"""Celery tasks for the Employee MVP.

``parse_and_match_employee`` is enqueued after each Employee record is
created (single or bulk). It parses the CV, populates structured fields,
and creates EmployeeJobMatch records for the top-K suggested jobs.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.employees.matching import match_employee_to_jobs, rematch_employee
from apps.employees.models import Employee, EmployeeJobMatch
from apps.employees.parsers import parse_cv_file

logger = logging.getLogger(__name__)


def _persist_matches(emp: Employee, matches: list[dict]) -> dict:
    """Upsert match rows. New rows start as ``suggested``; existing rows keep
    their HR-set pipeline status (only score/skills/gap are refreshed) — re-
    matching must never reset pursuing/applied/won/lost."""
    from apps.jobs.models import Job

    created = 0
    skipped = 0
    for m in matches:
        job = Job.objects.filter(pk=m["job_id"]).first()
        if job is None:
            # Engine job_id space may not map onto a Job row; skip rather than
            # raise an integrity error so the rest of the batch still lands.
            skipped += 1
            continue
        seniority_gap = None
        if job.seniority is not None and emp.seniority is not None:
            seniority_gap = int(job.seniority) - int(emp.seniority)
        scores = {
            "match_score": float(m.get("score", 0.0)),
            "matched_skills": m.get("matched_skills", []),
            "missing_skills": m.get("missing_skills", []),
            "seniority_gap": seniority_gap,
        }
        _, was_created = EmployeeJobMatch.objects.update_or_create(
            employee=emp,
            job=job,
            defaults=scores,  # update: refresh scores, preserve status
            create_defaults={**scores, "status": EmployeeJobMatch.Status.SUGGESTED},
        )
        if was_created:
            created += 1
    return {
        "employee_id": emp.id,
        "matches_total": len(matches),
        "matches_created": created,
        "matches_skipped": skipped,
    }


def _do_rematch(employee_id: int) -> dict:
    """Re-match only (no CV re-parse, no LLM) — fast, schedule-friendly."""
    try:
        emp = Employee.objects.get(pk=employee_id)
    except Employee.DoesNotExist:
        return {"employee_id": employee_id, "skipped": "not_found"}
    if not emp.skills:
        return {"employee_id": employee_id, "skipped": "no_skills"}
    return _persist_matches(emp, rematch_employee(emp, top_k=30))


def _do_parse_and_match(employee_id: int) -> dict:
    """Synchronous worker — also reused by the management command."""
    try:
        emp = Employee.objects.get(pk=employee_id)
    except Employee.DoesNotExist:
        return {"employee_id": employee_id, "skipped": "not_found"}

    parsed = parse_cv_file(emp.cv_file) if emp.cv_file else {}
    if parsed:
        # Identity fields — only overwrite when the CV gave us something.
        if parsed.get("full_name"):
            emp.full_name = parsed["full_name"]
        if parsed.get("position"):
            emp.position = parsed["position"]
        if parsed.get("phone"):
            emp.phone = parsed["phone"]
        email = parsed.get("email")
        if email and not Employee.objects.filter(email=email).exclude(pk=emp.pk).exists():
            emp.email = email  # respect the unique-email constraint

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

    return _persist_matches(emp, match_employee_to_jobs(emp, top_k=30))


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
