from rest_framework import serializers

from apps.employees.models import Employee, EmployeeCV, EmployeeJobMatch
from apps.jobs.serializers import JobListSerializer


class EmployeeCVSerializer(serializers.ModelSerializer):
    """A CV version — file URL + its own parse + active flag (027)."""

    filename = serializers.SerializerMethodField()
    skills_count = serializers.SerializerMethodField()
    parsing = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeCV
        fields = (
            "id", "employee", "cv_file", "filename", "label",
            "position", "seniority", "experience_years", "skills", "skills_count",
            "parsed_at", "is_parse_failed", "parsing", "is_active", "created_at",
        )
        read_only_fields = fields

    def get_filename(self, obj) -> str:
        import os
        return os.path.basename(obj.cv_file.name) if obj.cv_file else ""

    def get_skills_count(self, obj) -> int:
        return len(obj.skills or [])

    def get_parsing(self, obj) -> bool:
        # freshly uploaded, parse not finished and not failed yet
        return obj.parsed_at is None and not obj.is_parse_failed


class EmployeeListSerializer(serializers.ModelSerializer):
    match_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Employee
        fields = (
            "id", "full_name", "email", "position", "seniority",
            "experience_years", "skills",
            "is_parse_failed", "parsed_at", "match_count", "created_at",
        )


class EmployeeDetailSerializer(serializers.ModelSerializer):
    matches_count_by_status = serializers.SerializerMethodField()
    matches_count_by_platform = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id", "full_name", "email", "phone", "position",
            "seniority", "experience_years", "skills",
            "cv_file", "parsed_at", "is_parse_failed",
            "notes", "created_by",
            "matches_count_by_status", "matches_count_by_platform",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "cv_file", "parsed_at", "is_parse_failed",
            "created_by", "matches_count_by_status", "matches_count_by_platform",
            "created_at", "updated_at",
        )

    def get_matches_count_by_status(self, obj):
        from django.db.models import Count

        rows = obj.matches.values("status").annotate(c=Count("id"))
        return {row["status"]: row["c"] for row in rows}

    def get_matches_count_by_platform(self, obj):
        """Per-platform match counts (excluding dismissed) for the filter chips —
        [{name, slug, count}], descending by count."""
        from django.db.models import Count

        from apps.employees.models import EmployeeJobMatch

        rows = (
            obj.matches.exclude(status="dismissed")
            .exclude(status__in=EmployeeJobMatch.APPLIED_STATUSES)  # match the hide-applied list
            .values("job__platform__name", "job__platform__slug", "job__platform__logo_url")
            .annotate(c=Count("id"))
            .order_by("-c")
        )
        return [
            {"name": r["job__platform__name"] or "Unknown",
             "slug": r["job__platform__slug"] or "",
             "logo": r["job__platform__logo_url"] or "",
             "count": r["c"]}
            for r in rows
        ]


class EmployeeJobMatchSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = EmployeeJobMatch
        fields = (
            "id", "employee", "employee_name", "job",
            "status", "match_score", "matched_skills",
            "missing_skills", "covered_skills", "score_breakdown", "seniority_gap", "dim_scores",
            "assigned_to", "notes",
            "applied_at", "won_at", "lost_at",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "employee", "job",
            "match_score", "matched_skills",
            "missing_skills", "covered_skills", "score_breakdown", "seniority_gap", "dim_scores",
            "applied_at", "won_at", "lost_at",
            "created_at", "updated_at",
        )
