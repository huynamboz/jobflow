# Data Model: Employee MVP

**Date**: 2026-05-22

## E1: Employee (`apps.employees.models.Employee`)

```python
class Employee(models.Model):
    class Status(models.TextChoices):
        BENCH = "bench", "On bench"
        PURSUING = "pursuing", "Pursuing"
        PLACED = "placed", "Placed"
        INACTIVE = "inactive", "Inactive"

    # Identity
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")

    # Profile (parsed from CV)
    position = models.CharField(max_length=200, blank=True, default="")
    seniority = models.IntegerField(
        choices=Job.Seniority.choices, default=Job.Seniority.MID
    )
    experience_years = models.FloatField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)  # ["python", "django", ...]

    # CV file
    cv_file = models.FileField(upload_to="employee_cvs/", null=True, blank=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    is_parse_failed = models.BooleanField(default=False)

    # Pipeline
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.BENCH, db_index=True
    )
    notes = models.TextField(blank=True, default="")

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employees"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(email__gt=""),
                name="uniq_employee_email_nonblank",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]
```

## E2: EmployeeJobMatch (`apps.employees.models.EmployeeJobMatch`)

```python
class EmployeeJobMatch(models.Model):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        PURSUING = "pursuing", "Pursuing"
        APPLIED = "applied", "Applied"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="matches"
    )
    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="employee_matches"
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.SUGGESTED, db_index=True
    )
    match_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    matched_skills = models.JSONField(default=list, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_matches",
    )
    notes = models.TextField(max_length=500, blank=True, default="")

    # Lifecycle timestamps (snapshot khi đổi status)
    applied_at = models.DateTimeField(null=True, blank=True)
    won_at = models.DateTimeField(null=True, blank=True)
    lost_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employee_job_matches"
        ordering = ["-match_score", "-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "job"], name="uniq_emp_job"),
        ]
        indexes = [
            models.Index(fields=["employee", "status", "-match_score"]),
            models.Index(fields=["status", "-updated_at"]),
        ]
```

## E3: User notification fields (extend `apps.users.User`)

```python
class User(AbstractUser):
    role = models.CharField(...)
    notify_daily_digest = models.BooleanField(default=True)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
```

Migration thêm 2 cột; backfill `unsubscribe_token` cho rows hiện tại (Django auto-generate default cho new + manual data migration cho existing).

## E4: Serializers

```python
class EmployeeListSerializer(serializers.ModelSerializer):
    match_count = serializers.IntegerField(read_only=True)  # annotated

    class Meta:
        model = Employee
        fields = ("id", "full_name", "email", "position", "seniority",
                  "status", "skills", "match_count", "created_at")

class EmployeeDetailSerializer(serializers.ModelSerializer):
    matches_count_by_status = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = "__all__"

    def get_matches_count_by_status(self, obj):
        return dict(
            obj.matches.values_list("status").annotate(c=Count("id"))
        )


class EmployeeJobMatchSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = EmployeeJobMatch
        fields = ("id", "employee", "employee_name", "job", "status", "match_score",
                  "matched_skills", "assigned_to", "notes",
                  "applied_at", "won_at", "lost_at",
                  "created_at", "updated_at")
        read_only_fields = ("id", "employee", "job", "match_score", "matched_skills",
                            "applied_at", "won_at", "lost_at", "created_at", "updated_at")
```

## E5: ViewSet patterns

```python
class EmployeeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHRStaff]
    filterset_fields = ["status", "seniority"]
    search_fields = ["full_name", "email", "position"]

    def get_queryset(self):
        return Employee.objects.annotate(
            match_count=Count("matches", filter=Q(matches__status="suggested"))
        )

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser])
    def bulk_upload(self, request):
        files = request.FILES.getlist("files")
        if len(files) > 50:
            raise ValidationError("Max 50 files per batch")
        employees = []
        for f in files:
            emp = Employee.objects.create(
                full_name=f.name.rsplit(".", 1)[0],
                cv_file=f,
                created_by=request.user,
            )
            # Enqueue async parse + match generation
            from apps.employees.tasks import parse_and_match_employee
            parse_and_match_employee.delay(emp.id)
            employees.append(emp)
        return Response(EmployeeListSerializer(employees, many=True).data, status=201)

    @action(detail=True, methods=["post"])
    def rescore(self, request, pk=None):
        """Re-run matching for this employee."""
        from apps.employees.tasks import parse_and_match_employee
        parse_and_match_employee.delay(int(pk))
        return Response({"status": "queued"})


class EmployeeJobMatchViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHRStaff]
    filterset_fields = ["status", "employee_id", "job_id", "assigned_to"]

    def get_queryset(self):
        return EmployeeJobMatch.objects.select_related("employee", "job", "assigned_to")

    def perform_update(self, serializer):
        instance = serializer.save()
        # Auto-transition timestamps + Employee.status
        new_status = serializer.validated_data.get("status")
        if new_status == "applied" and not instance.applied_at:
            instance.applied_at = timezone.now()
            instance.save(update_fields=["applied_at"])
        if new_status == "won":
            instance.won_at = timezone.now()
            instance.save(update_fields=["won_at"])
            instance.employee.status = "placed"
            instance.employee.save(update_fields=["status"])
        if new_status == "lost":
            instance.lost_at = timezone.now()
            instance.save(update_fields=["lost_at"])
```

## E6: Pipeline KPI endpoint

```python
class PipelineKpiView(APIView):
    permission_classes = [IsHRStaff]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        week_ago = now - timedelta(days=7)

        return Response({
            "success": True,
            "data": {
                "employees": dict(Employee.objects.values_list("status").annotate(c=Count("id"))),
                "matches_this_week": dict(
                    EmployeeJobMatch.objects.filter(updated_at__gte=week_ago)
                    .values_list("status").annotate(c=Count("id"))
                ),
                "top_employees_pursuing": list(
                    Employee.objects.filter(status="pursuing")
                    .annotate(active_matches=Count("matches", filter=Q(matches__status__in=["pursuing", "applied"])))
                    .order_by("-active_matches")[:10]
                    .values("id", "full_name", "active_matches")
                ),
            }
        })
```

## E7: Tasks (Celery)

```python
@shared_task(bind=True, max_retries=2)
def parse_and_match_employee(self, employee_id: int):
    """Parse CV → extract skills → generate top-K Match records."""
    emp = Employee.objects.get(pk=employee_id)
    try:
        # Step 1: parse CV (reuse existing CV parser from apps.cvs)
        from apps.cvs.parser_service import parse_cv_file  # adapter
        parsed = parse_cv_file(emp.cv_file)
        emp.skills = parsed.get("skills", [])
        emp.seniority = parsed.get("seniority", emp.seniority)
        emp.experience_years = parsed.get("experience_years")
        emp.parsed_at = timezone.now()
        emp.save()

        # Step 2: call matching API → create Match records for top K
        from apps.matching.services import match_employee_to_jobs  # adapter
        matches = match_employee_to_jobs(employee=emp, top_k=30)
        for m in matches:
            EmployeeJobMatch.objects.update_or_create(
                employee=emp, job_id=m["job_id"],
                defaults={
                    "status": "suggested",
                    "match_score": m["score"],
                    "matched_skills": m.get("matched_skills", []),
                },
            )
        return {"employee_id": employee_id, "matches": len(matches)}
    except Exception as exc:
        emp.is_parse_failed = True
        emp.save(update_fields=["is_parse_failed"])
        logger.exception("parse_and_match failed for employee %s", employee_id)
        raise self.retry(exc=exc, countdown=60)
```

## E8: HR digest task

```python
@shared_task
def schedule_hr_digests():
    user_ids = User.objects.filter(
        role__in=["admin", "recruiter"],
        notify_daily_digest=True,
    ).values_list("id", flat=True)
    for uid in user_ids:
        send_hr_daily_digest_task.delay(uid)


@shared_task(bind=True, max_retries=3)
def send_hr_daily_digest_task(self, user_id: int):
    user = User.objects.get(pk=user_id)
    yesterday = timezone.now() - timedelta(days=1)

    new_matches = EmployeeJobMatch.objects.filter(
        status="suggested",
        created_at__gte=yesterday,
    ).select_related("employee", "job").order_by("-match_score")[:10]

    pipeline_changes = EmployeeJobMatch.objects.filter(
        status__in=["won", "lost"],
        updated_at__gte=yesterday,
    ).select_related("employee", "job")

    if not new_matches and not pipeline_changes:
        return {"skipped": "no_content"}

    kpi = {
        "bench": Employee.objects.filter(status="bench").count(),
        "pursuing": Employee.objects.filter(status="pursuing").count(),
        "placed_week": Employee.objects.filter(status="placed", updated_at__gte=yesterday).count(),
    }

    html = render_to_string("emails/hr_daily_digest.html", {
        "user": user,
        "new_matches": new_matches,
        "pipeline_changes": pipeline_changes,
        "kpi": kpi,
        "unsubscribe_url": f"{settings.FRONTEND_BASE_URL}/unsubscribe/{user.unsubscribe_token}",
        "frontend_base": settings.FRONTEND_BASE_URL,
    })
    send_mail(
        subject="[JobFlow HR] Daily pipeline digest",
        message=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html,
    )
    return {"sent_to": user.email, "new_matches": len(new_matches)}
```

## E9: Frontend types (TS)

```typescript
// admin/src/types/employee.types.ts

export type EmployeeStatus = "bench" | "pursuing" | "placed" | "inactive";

export interface Employee {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  seniority: number;
  experience_years: number | null;
  skills: string[];
  status: EmployeeStatus;
  cv_file: string | null;
  is_parse_failed: boolean;
  match_count?: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

// admin/src/types/match.types.ts

export type MatchStatus = "suggested" | "pursuing" | "applied" | "won" | "lost";

export interface EmployeeJobMatch {
  id: number;
  employee: number;
  employee_name: string;
  job: { id: number; title: string; company_name: string; location: string };
  status: MatchStatus;
  match_score: number;
  matched_skills: string[];
  assigned_to: number | null;
  notes: string;
  applied_at: string | null;
  won_at: string | null;
  lost_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineKpi {
  employees: Record<EmployeeStatus, number>;
  matches_this_week: Record<MatchStatus, number>;
  top_employees_pursuing: Array<{ id: number; full_name: string; active_matches: number }>;
}
```
