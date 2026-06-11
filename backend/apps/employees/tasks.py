"""Celery tasks for the Employee MVP.

``parse_and_match_employee`` is enqueued after each Employee record is
created (single or bulk). It parses the CV, populates structured fields,
and creates EmployeeJobMatch records for the top-K suggested jobs.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.employees.matching import rematch_employee
from apps.employees.models import Employee, EmployeeJobMatch
from apps.employees.parsers import parse_cv_file

logger = logging.getLogger(__name__)

# How many top-ranked jobs to store per employee. The list is ranked by the GNN,
# so larger = a longer tail of lower-relevance jobs for HR to browse.
MATCH_TOP_K = 100


def _persist_matches(emp: Employee, matches: list[dict]) -> dict:
    """Upsert match rows. New rows start as ``suggested``; existing rows keep
    their HR-set pipeline status (only score/skills/gap are refreshed) — re-
    matching must never reset pursuing/applied/won/lost.

    Stale ``suggested`` matches no longer in the fresh top-K are pruned so the
    list stays = the current ranking (HR-engaged + dismissed rows are kept)."""
    from apps.jobs.models import Job

    created = 0
    skipped = 0
    persisted_ids: list[int] = []
    for m in matches:
        # Feature 018: the engine job_id is a live Job.id, so resolve by pk
        # directly (no more skipped gap). A source_url fallback stays for the
        # legacy frozen-checkpoint pool (JDExtractionRecord-id space).
        job = Job.objects.filter(pk=m["job_id"]).first()
        if job is None:
            url = m.get("source_url")
            job = Job.objects.filter(source_url=url).first() if url else None
        if job is None:
            skipped += 1
            continue
        seniority_gap = None
        if job.seniority is not None and emp.seniority is not None:
            seniority_gap = int(job.seniority) - int(emp.seniority)
        scores = {
            "match_score": float(m.get("score", 0.0)),
            "matched_skills": m.get("matched_skills", []),
            "missing_skills": m.get("missing_skills", []),
            "covered_skills": m.get("covered_skills", {}),
            "score_breakdown": m.get("score_breakdown", {}),
            "seniority_gap": seniority_gap,
            "dim_scores": m.get("dim_scores", {}),
        }
        _, was_created = EmployeeJobMatch.objects.update_or_create(
            employee=emp,
            job=job,
            defaults=scores,  # update: refresh scores, preserve status
            create_defaults={**scores, "status": EmployeeJobMatch.Status.SUGGESTED},
        )
        persisted_ids.append(job.id)
        if was_created:
            created += 1

    # Prune stale suggestions: drop suggested rows no longer in the fresh top-K
    # (keeps everything HR has touched + dismissed labels).
    pruned = 0
    if persisted_ids:
        pruned, _ = (
            EmployeeJobMatch.objects.filter(
                employee=emp, status=EmployeeJobMatch.Status.SUGGESTED
            )
            .exclude(job_id__in=persisted_ids)
            .delete()
        )

    return {
        "employee_id": emp.id,
        "matches_total": len(matches),
        "matches_created": created,
        "matches_skipped": skipped,
        "matches_pruned": pruned,
    }


def _do_rematch(employee_id: int) -> dict:
    """Re-match only (no CV re-parse, no LLM) — fast, schedule-friendly."""
    try:
        emp = Employee.objects.get(pk=employee_id)
    except Employee.DoesNotExist:
        return {"employee_id": employee_id, "skipped": "not_found"}
    if not emp.skills:
        return {"employee_id": employee_id, "skipped": "no_skills"}
    return _persist_matches(emp, rematch_employee(emp, top_k=MATCH_TOP_K))


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

    # 025: after the parse above the employee's skills/position are stored —
    # match through the SAME deterministic path as scheduled re-matches
    # (match_cv_data). The old route synthesized a "Skills: ..." text and
    # LLM-parsed it AGAIN: a second LLM call whose output could drift from the
    # stored fields, making upload-time scores differ from rematch-time scores.
    return _persist_matches(emp, rematch_employee(emp, top_k=MATCH_TOP_K))


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
