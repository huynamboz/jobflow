"""Celery tasks for HR daily digest emails.

Production schedule via Celery beat; for local dev/testing use::

    python manage.py send_hr_digest --user-id <id>
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

User = get_user_model()


def _build_digest_context(user) -> dict | None:
    """Gather content for one HR recipient. Returns None if nothing to send."""
    from apps.employees.models import Employee, EmployeeJobMatch

    yesterday = timezone.now() - timedelta(days=1)

    new_matches = list(
        EmployeeJobMatch.objects.filter(status="suggested", created_at__gte=yesterday)
        .select_related("employee", "job")
        .order_by("-match_score")[:10]
    )
    pipeline_changes = list(
        EmployeeJobMatch.objects.filter(status__in=["won", "lost"], updated_at__gte=yesterday)
        .select_related("employee", "job")
        .order_by("-updated_at")[:20]
    )

    if not new_matches and not pipeline_changes:
        return None

    kpi = {
        "bench": Employee.objects.filter(status="bench").count(),
        "pursuing": Employee.objects.filter(status="pursuing").count(),
        "placed_week": Employee.objects.filter(
            status="placed", updated_at__gte=yesterday
        ).count(),
    }

    return {
        "user": user,
        "new_matches": new_matches,
        "pipeline_changes": pipeline_changes,
        "kpi": kpi,
        "unsubscribe_url": f"{settings.FRONTEND_BASE_URL}/unsubscribe/{user.unsubscribe_token}",
        "frontend_base": settings.FRONTEND_BASE_URL,
    }


def _send_one(user) -> dict:
    """Render + send digest to one HR/admin user. Used by Celery + management cmd."""
    from django.core.mail import EmailMultiAlternatives

    if user.role not in ("admin", "recruiter"):
        return {"user_id": user.pk, "skipped": "wrong_role"}
    if not user.notify_daily_digest:
        return {"user_id": user.pk, "skipped": "unsubscribed"}

    context = _build_digest_context(user)
    if context is None:
        return {"user_id": user.pk, "skipped": "no_content"}

    html = render_to_string("emails/hr_daily_digest.html", context)
    text = strip_tags(html)
    msg = EmailMultiAlternatives(
        subject="[JobFlow HR] Daily pipeline digest",
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)

    return {
        "user_id": user.pk,
        "sent_to": user.email,
        "new_matches": len(context["new_matches"]),
        "pipeline_changes": len(context["pipeline_changes"]),
    }


try:
    from celery import shared_task  # type: ignore
except ImportError:  # pragma: no cover
    shared_task = None  # type: ignore


if shared_task is not None:

    @shared_task(bind=True, max_retries=3, default_retry_delay=300)
    def send_hr_daily_digest_task(self, user_id: int):
        try:
            user = User.objects.get(pk=user_id)
            return _send_one(user)
        except User.DoesNotExist:
            return {"user_id": user_id, "skipped": "user_missing"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("hr digest failed for user %s", user_id)
            raise self.retry(exc=exc)

    @shared_task
    def schedule_hr_digests():
        """Fan-out: enqueue one send task per eligible user."""
        ids = list(
            User.objects.filter(role__in=["admin", "recruiter"], notify_daily_digest=True)
            .values_list("id", flat=True)
        )
        for uid in ids:
            send_hr_daily_digest_task.delay(uid)
        return {"enqueued": len(ids)}
