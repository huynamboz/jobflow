from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status as drf_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
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


MAX_BULK_FILES = 50


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
            # Enqueue async parse + match generation
            try:
                from apps.employees.tasks import parse_and_match_employee

                parse_and_match_employee.delay(emp.id)
            except Exception:  # noqa: BLE001 — celery may be down in dev
                pass
            created.append(emp)

        data = EmployeeListSerializer(created, many=True).data
        return Response({"success": True, "data": data}, status=drf_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rescore")
    def rescore(self, request, pk=None):
        try:
            from apps.employees.tasks import parse_and_match_employee

            parse_and_match_employee.delay(int(pk))
            return Response({"success": True, "status": "queued"})
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"success": False, "error": {"message": str(exc)}},
                status=drf_status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class EmployeeJobMatchViewSet(viewsets.ModelViewSet):
    """List/update match records. Auto-transition timestamps + Employee.status."""

    serializer_class = EmployeeJobMatchSerializer
    permission_classes = [IsAuthenticated, IsHRStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "employee", "job", "assigned_to"]

    def get_queryset(self):
        return EmployeeJobMatch.objects.select_related(
            "employee", "job", "job__company", "assigned_to"
        )

    def destroy(self, request, *args, **kwargs):
        if not IsAdminUserRole().has_permission(request, self):
            raise PermissionDenied("Only admin role can delete matches.")
        return super().destroy(request, *args, **kwargs)

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
            instance.won_at = now
            updates.append("won_at")
            # Auto-transition Employee
            if instance.employee.status != Employee.Status.PLACED:
                instance.employee.status = Employee.Status.PLACED
                instance.employee.save(update_fields=["status", "updated_at"])
        if new_status == "lost" and not instance.lost_at:
            instance.lost_at = now
            updates.append("lost_at")
        if new_status == "pursuing" and instance.employee.status == Employee.Status.BENCH:
            instance.employee.status = Employee.Status.PURSUING
            instance.employee.save(update_fields=["status", "updated_at"])
        if updates:
            instance.save(update_fields=updates + ["updated_at"])


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
