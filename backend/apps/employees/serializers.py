from rest_framework import serializers

from apps.employees.models import Employee, EmployeeJobMatch
from apps.jobs.serializers import JobListSerializer


class EmployeeListSerializer(serializers.ModelSerializer):
    match_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Employee
        fields = (
            "id", "full_name", "email", "position", "seniority",
            "experience_years", "skills", "status",
            "is_parse_failed", "parsed_at", "match_count", "created_at",
        )


class EmployeeDetailSerializer(serializers.ModelSerializer):
    matches_count_by_status = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id", "full_name", "email", "phone", "position",
            "seniority", "experience_years", "skills",
            "cv_file", "parsed_at", "is_parse_failed",
            "status", "notes", "created_by",
            "matches_count_by_status",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "cv_file", "parsed_at", "is_parse_failed",
            "created_by", "matches_count_by_status",
            "created_at", "updated_at",
        )

    def get_matches_count_by_status(self, obj):
        from django.db.models import Count

        rows = obj.matches.values("status").annotate(c=Count("id"))
        return {row["status"]: row["c"] for row in rows}


class EmployeeJobMatchSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = EmployeeJobMatch
        fields = (
            "id", "employee", "employee_name", "job",
            "status", "match_score", "matched_skills",
            "missing_skills", "seniority_gap",
            "assigned_to", "notes",
            "applied_at", "won_at", "lost_at",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "employee", "job",
            "match_score", "matched_skills",
            "missing_skills", "seniority_gap",
            "applied_at", "won_at", "lost_at",
            "created_at", "updated_at",
        )
