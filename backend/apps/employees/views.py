import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status as drf_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.employees.models import Employee, EmployeeJobMatch
from apps.employees.permissions import IsAdminUserRole, IsHRStaff
from apps.employees.serializers import (
    EmployeeDetailSerializer,
    EmployeeJobMatchSerializer,
    EmployeeListSerializer,
)


logger = logging.getLogger(__name__)

MAX_BULK_FILES = 50


_parse_pool: ThreadPoolExecutor | None = None
_parse_pool_lock = threading.Lock()


def _get_parse_pool() -> ThreadPoolExecutor:
    global _parse_pool
    if _parse_pool is None:
        with _parse_pool_lock:
            if _parse_pool is None:
                _parse_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cvparse")
    return _parse_pool


def _process_employee(employee_id: int) -> None:
    """Kick off parse + match without blocking the request.

    Prefers Celery; when it isn't installed / the broker is down (dev), the work
    runs in a small background thread pool so the upload returns immediately and
    the UI can poll for results.
    """
    try:
        # Import inside the try: when Celery is absent the task symbol doesn't
        # exist, and we still want the background fallback.
        from apps.employees.tasks import parse_and_match_employee

        parse_and_match_employee.delay(employee_id)
    except Exception:  # noqa: BLE001 — no Celery / broker down: parse in a thread
        from apps.employees.tasks import _do_parse_and_match

        def _run() -> None:
            try:
                _do_parse_and_match(employee_id)
            except Exception:  # noqa: BLE001
                logger.warning("Background parse failed for %s", employee_id, exc_info=True)
            finally:
                from django.db import connection

                connection.close()

        _get_parse_pool().submit(_run)


class EmployeeViewSet(viewsets.ModelViewSet):
    """CRUD employees. Bulk upload + re-score actions."""

    permission_classes = [IsAuthenticated, IsHRStaff]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["status", "seniority"]
    search_fields = ["full_name", "email", "position"]

    def get_queryset(self):
        return Employee.objects.annotate(
            match_count=Count("matches", filter=Q(matches__status="suggested"))
        )

    def get_serializer_class(self):
        if self.action == "list":
            return EmployeeListSerializer
        return EmployeeDetailSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        # Feature 1.3: a manual HR edit means the record has been reviewed, so a
        # prior parse failure is considered resolved.
        instance = serializer.save()
        if instance.is_parse_failed:
            instance.is_parse_failed = False
            instance.save(update_fields=["is_parse_failed", "updated_at"])

    def destroy(self, request, *args, **kwargs):
        if not IsAdminUserRole().has_permission(request, self):
            raise PermissionDenied("Only admin role can delete employees.")
        return super().destroy(request, *args, **kwargs)

    @action(
        detail=False,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        url_path="bulk_upload",
    )
    def bulk_upload(self, request):
        files = request.FILES.getlist("files")
        if not files:
            raise ValidationError("No files provided (field name: 'files').")
        if len(files) > MAX_BULK_FILES:
            return Response(
                {"success": False, "error": {"message": f"Max {MAX_BULK_FILES} files per batch."}},
                status=drf_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        created = []
        for f in files:
            stem = f.name.rsplit(".", 1)[0]
            emp = Employee.objects.create(
                full_name=stem[:200] or "Unnamed",
                cv_file=f,
                created_by=request.user,
            )
            # Parse + match (async via Celery, sync fallback when it is down).
            try:
                _process_employee(emp.id)
            except Exception:  # noqa: BLE001 — never fail the upload over parsing
                logger.warning("Parse/match failed for employee %s", emp.id, exc_info=True)
            created.append(emp)

        data = EmployeeListSerializer(created, many=True).data
        return Response({"success": True, "data": data}, status=drf_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rescore")
    def rescore(self, request, pk=None):
        try:
            _process_employee(int(pk))
            return Response({"success": True, "status": "queued"})
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"success": False, "error": {"message": str(exc)}},
                status=drf_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=True, methods=["post"], url_path="rematch")
    def rematch(self, request, pk=None):
        """Refresh job matches against the current catalog — no CV re-parse / no
        LLM, and keeps each match's pipeline status. Runs **synchronously** (the
        GNN engine is warm, so this is quick) so the client gets a definitive
        'done' instead of guessing."""
        from apps.employees.tasks import _do_rematch

        try:
            result = _do_rematch(int(pk))
            return Response({"success": True, "data": result})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Re-match failed for employee %s", pk, exc_info=True)
            return Response(
                {"success": False, "error": {"message": str(exc)}},
                status=drf_status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class MatchPagination(PageNumberPagination):
    """Allow the client to choose the page size (e.g. the employee job browser
    pulls the top 10 by score, then 10 more on demand)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class EmployeeJobMatchViewSet(viewsets.ModelViewSet):
    """List/update match records.

    Shadow model (feature 014):
    - Employee.status is NEVER changed automatically by a match transition; HR
      sets it manually. A frontman who wins a job stays on bench to apply again.
    - Marking a match ``applied`` guards against another employee already
      fronting the same job (soft warning via HTTP 409 unless ``confirm_duplicate``).
    """

    serializer_class = EmployeeJobMatchSerializer
    permission_classes = [IsAuthenticated, IsHRStaff]
    pagination_class = MatchPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "employee", "job", "assigned_to"]

    def get_queryset(self):
        qs = EmployeeJobMatch.objects.select_related(
            "employee", "job", "job__company", "assigned_to"
        )
        # Multi-status filter for the job-tracking view, e.g.
        # ?statuses=applied,won,lost.
        statuses = self.request.query_params.get("statuses")
        if statuses:
            wanted = [s.strip() for s in statuses.split(",") if s.strip()]
            return qs.filter(status__in=wanted)
        # Dismissed ("not a fit") jobs are hidden everywhere unless explicitly
        # requested with ?status=dismissed.
        if self.request.query_params.get("status") != EmployeeJobMatch.Status.DISMISSED:
            qs = qs.exclude(status=EmployeeJobMatch.Status.DISMISSED)
        return qs

    def destroy(self, request, *args, **kwargs):
        if not IsAdminUserRole().has_permission(request, self):
            raise PermissionDenied("Only admin role can delete matches.")
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        new_status = request.data.get("status")
        confirm_duplicate = str(request.data.get("confirm_duplicate", "")).lower() in (
            "1", "true", "yes",
        )
        # US3: warn before two employees front the same job.
        if new_status == "applied" and not confirm_duplicate:
            frontman = (
                EmployeeJobMatch.objects.filter(
                    job_id=instance.job_id,
                    status__in=["applied", "won"],
                )
                .exclude(pk=instance.pk)
                .select_related("employee")
                .first()
            )
            if frontman is not None:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "DUPLICATE_APPLY",
                            "message": "This job has already been applied to by another employee.",
                            "frontman": {
                                "employee_id": frontman.employee_id,
                                "employee_name": frontman.employee.full_name,
                                "match_id": frontman.pk,
                                "status": frontman.status,
                            },
                        },
                    },
                    status=drf_status.HTTP_409_CONFLICT,
                )
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.save()
        new_status = serializer.validated_data.get("status")
        if not new_status:
            return
        now = timezone.now()
        updates = []
        if new_status == "applied" and not instance.applied_at:
            instance.applied_at = now
            updates.append("applied_at")
        if new_status == "won" and not instance.won_at:
            # US4: winning a job does NOT place the frontman — record the
            # timestamp only; Employee.status is left untouched.
            instance.won_at = now
            updates.append("won_at")
        if new_status == "lost" and not instance.lost_at:
            instance.lost_at = now
            updates.append("lost_at")
        if updates:
            instance.save(update_fields=updates + ["updated_at"])


class DashboardView(APIView):
    """Operational HR-staffing dashboard (feature 016).

    One round-trip returning the five blocks the morning workflow needs:
    KPI strip, action queue, pipeline funnel, alerts, recent activity.
    """

    permission_classes = [IsAuthenticated, IsHRStaff]
    STALE_APPLIED_DAYS = 7
    HIGH_SCORE = 0.8

    def get(self, request):
        from apps.jobs.models import Job

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        day_ago = now - timedelta(days=1)
        stale_before = now - timedelta(days=self.STALE_APPLIED_DAYS)

        engaged_statuses = ["pursuing", "applied", "won"]

        # --- Block 1: KPI strip ---
        active_emp = Employee.objects.exclude(status="inactive").count()
        engaged = (
            Employee.objects.filter(matches__status__in=engaged_statuses)
            .distinct()
            .count()
        )
        kpi = {
            "utilization_pct": round(100 * engaged / active_emp) if active_emp else 0,
            "bench_count": Employee.objects.filter(status="bench").count(),
            "in_progress": EmployeeJobMatch.objects.filter(
                status__in=["pursuing", "applied"]
            ).count(),
            "won_this_week": EmployeeJobMatch.objects.filter(won_at__gte=week_ago).count(),
            "lost_this_week": EmployeeJobMatch.objects.filter(lost_at__gte=week_ago).count(),
            "new_jobs_24h": Job.objects.filter(created_at__gte=day_ago).count(),
            "new_jobs_7d": Job.objects.filter(created_at__gte=week_ago).count(),
        }

        # --- Block 2: Action queue ---
        top_new = list(
            Employee.objects.annotate(
                new_count=Count("matches", filter=Q(matches__status="suggested"))
            )
            .filter(new_count__gt=0)
            .order_by("-new_count")[:5]
            .values("id", "full_name", "new_count")
        )
        bench_stale_rows = (
            Employee.objects.filter(status="bench")
            .annotate(
                active_opps=Count(
                    "matches", filter=Q(matches__status__in=engaged_statuses)
                )
            )
            .filter(active_opps=0)
            .order_by("created_at")[:5]
        )
        bench_stale = [
            {
                "id": e.id,
                "full_name": e.full_name,
                "days_on_bench": (now - e.created_at).days,
            }
            for e in bench_stale_rows
        ]
        stale_applied = [
            {
                "match_id": m.id,
                "employee_id": m.employee_id,
                "employee_name": m.employee.full_name,
                "job_title": m.job.title,
                "days_since_applied": (now - m.applied_at).days if m.applied_at else None,
            }
            for m in EmployeeJobMatch.objects.filter(
                status="applied", applied_at__lt=stale_before
            ).select_related("employee", "job").order_by("applied_at")[:5]
        ]
        action_queue = {
            "top_new_matches": top_new,
            "bench_stale": bench_stale,
            "stale_applied": stale_applied,
        }

        # --- Block 3: Pipeline funnel ---
        funnel = {s: 0 for s in ["suggested", "pursuing", "applied", "won", "lost"]}
        for row in EmployeeJobMatch.objects.values("status").annotate(c=Count("id")):
            funnel[row["status"]] = row["c"]

        # --- Block 4: Alerts ---
        parse_failed = list(
            Employee.objects.filter(is_parse_failed=True)[:10].values("id", "full_name")
        )
        high_score_unapplied = [
            {
                "match_id": m.id,
                "employee_id": m.employee_id,
                "employee_name": m.employee.full_name,
                "job_title": m.job.title,
                "score": round(m.match_score, 2),
            }
            for m in EmployeeJobMatch.objects.filter(
                status="suggested", match_score__gte=self.HIGH_SCORE
            ).select_related("employee", "job").order_by("-match_score")[:5]
        ]
        expiring_pursuing = [
            {
                "match_id": m.id,
                "employee_id": m.employee_id,
                "employee_name": m.employee.full_name,
                "job_title": m.job.title,
                "lifecycle": m.job.lifecycle,
            }
            for m in EmployeeJobMatch.objects.filter(
                status__in=["pursuing", "applied"],
                job__lifecycle__in=[Job.LIFECYCLE_STALE, Job.LIFECYCLE_EXPIRED],
            ).select_related("employee", "job")[:5]
        ]
        alerts = {
            "parse_failed": parse_failed,
            "high_score_unapplied": high_score_unapplied,
            "expiring_pursuing": expiring_pursuing,
        }

        # --- Block 5: Recent activity ---
        recent_won_lost = [
            {
                "match_id": m.id,
                "employee_name": m.employee.full_name,
                "job_title": m.job.title,
                "status": m.status,
                "when": (m.won_at or m.lost_at or m.updated_at).isoformat(),
            }
            for m in EmployeeJobMatch.objects.filter(
                status__in=["won", "lost"]
            ).select_related("employee", "job").order_by("-updated_at")[:5]
        ]
        recent_jobs = [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company.name if j.company else "",
                "created_at": j.created_at.isoformat(),
            }
            for j in Job.objects.select_related("company").order_by("-created_at")[:5]
        ]
        recent_employees = list(
            Employee.objects.order_by("-created_at")[:5].values(
                "id", "full_name", "created_at"
            )
        )
        recent = {
            "won_lost": recent_won_lost,
            "new_jobs": recent_jobs,
            "new_employees": recent_employees,
        }

        return Response(
            {
                "success": True,
                "data": {
                    "kpi": kpi,
                    "action_queue": action_queue,
                    "funnel": funnel,
                    "alerts": alerts,
                    "recent": recent,
                },
            }
        )


class PipelineKpiView(APIView):
    permission_classes = [IsAuthenticated, IsHRStaff]

    def get(self, request):
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        emp_rows = Employee.objects.values("status").annotate(c=Count("id"))
        emp_status = {row["status"]: row["c"] for row in emp_rows}

        match_rows = (
            EmployeeJobMatch.objects.filter(updated_at__gte=week_ago)
            .values("status")
            .annotate(c=Count("id"))
        )
        match_status = {row["status"]: row["c"] for row in match_rows}

        top_pursuing = list(
            Employee.objects.filter(status="pursuing")
            .annotate(
                active_matches=Count(
                    "matches",
                    filter=Q(matches__status__in=["pursuing", "applied"]),
                )
            )
            .order_by("-active_matches")[:10]
            .values("id", "full_name", "active_matches")
        )

        return Response(
            {
                "success": True,
                "data": {
                    "employees": emp_status,
                    "matches_this_week": match_status,
                    "top_employees_pursuing": top_pursuing,
                },
            }
        )
