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
