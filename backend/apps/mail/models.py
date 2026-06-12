"""Mail-link models (026): credential, email log, in-app notification."""
from __future__ import annotations

from django.db import models

from apps.employees.models import Employee, EmployeeJobMatch
from apps.mail import crypto


class EmployeeMailCredential(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [(STATUS_ACTIVE, "Active"), (STATUS_ERROR, "Error")]

    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="mail_credential")
    gmail_address = models.EmailField(unique=True)
    # Fernet ciphertext — NEVER serialize / log this column (026 FR-002).
    password_encrypted = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    last_error = models.TextField(blank=True, default="")
    last_polled_at = models.DateTimeField(null=True, blank=True)  # 026: IMAP poll watermark + UI "last sync"
    linked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employee_mail_credentials"

    def set_password(self, plaintext: str) -> None:
        self.password_encrypted = crypto.encrypt(plaintext)

    def get_password(self) -> str:
        return crypto.decrypt(self.password_encrypted)

    def __repr__(self) -> str:  # never leak the secret
        return f"<EmployeeMailCredential employee={self.employee_id} {self.gmail_address} [{self.status}]>"

    __str__ = __repr__


class EmailLog(models.Model):
    OUT, IN = "out", "in"
    DIRECTION_CHOICES = [(OUT, "Outgoing"), (IN, "Incoming")]
    SENT, FAILED, RECEIVED = "sent", "failed", "received"
    STATUS_CHOICES = [(SENT, "Sent"), (FAILED, "Failed"), (RECEIVED, "Received")]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="emails")
    match = models.ForeignKey(EmployeeJobMatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="emails")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    from_addr = models.EmailField()
    to_addr = models.EmailField(blank=True, default="")
    subject = models.TextField(blank=True, default="")
    body_text = models.TextField(blank=True, default="")
    message_id = models.TextField(db_index=True)              # self-generated for OUT
    in_reply_to = models.TextField(blank=True, default="", db_index=True)  # matched OUT id for IN
    is_bounce = models.BooleanField(default=False)
    cv_attached = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_logs"
        ordering = ["created_at"]


class Notification(models.Model):
    MAIL_REPLY, MAIL_BOUNCE = "mail_reply", "mail_bounce"
    TYPE_CHOICES = [(MAIL_REPLY, "Mail reply"), (MAIL_BOUNCE, "Mail bounce")]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body_preview = models.TextField(blank=True, default="")
    link_url = models.TextField(blank=True, default="")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
