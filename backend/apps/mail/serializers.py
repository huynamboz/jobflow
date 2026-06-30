"""Serializers for mail-link (026). The password column is NEVER exposed."""
from rest_framework import serializers

from apps.mail.models import EmailLog, EmployeeMailCredential, Notification


class CredentialStatusSerializer(serializers.ModelSerializer):
    linked = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeMailCredential
        # password_encrypted intentionally absent (FR-002 / SC-006)
        fields = ("linked", "employee", "gmail_address", "status", "last_error", "linked_at")

    def get_linked(self, obj) -> bool:
        return True


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = ("id", "direction", "from_addr", "to_addr", "subject", "body_text",
                  "is_bounce", "cv_attached", "status", "error", "created_at")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "type", "title", "body_preview", "link_url", "employee", "read_at", "created_at")


class EmailLogListSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", default="")
    job_title = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    company_logo = serializers.SerializerMethodField()

    class Meta:
        model = EmailLog
        fields = ("id", "employee", "employee_name", "match", "job_title",
                  "company_name", "company_logo", "direction",
                  "from_addr", "to_addr", "subject", "is_bounce", "cv_attached",
                  "status", "error", "created_at")

    @staticmethod
    def _job(obj):
        return obj.match.job if obj.match and obj.match.job_id else None

    def get_job_title(self, obj) -> str:
        job = self._job(obj)
        return job.title if job else ""

    def get_company_name(self, obj) -> str:
        job = self._job(obj)
        return job.company.name if job and job.company_id else ""

    def get_company_logo(self, obj) -> str:
        job = self._job(obj)
        return (job.company.logo_url or "") if job and job.company_id else ""
