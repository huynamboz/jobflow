from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.jobs.models import Job


class Employee(models.Model):
    """A staffer of the company whose CV is on file. Not a Django User.

    Owned + managed by HR/admin users; tracked through bench/pursuing/placed.
    """

    class Status(models.TextChoices):
        BENCH = "bench", "On bench"
        PURSUING = "pursuing", "Pursuing"
        PLACED = "placed", "Placed"
        INACTIVE = "inactive", "Inactive"

    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")

    position = models.CharField(max_length=200, blank=True, default="")
    seniority = models.IntegerField(
        choices=Job.Seniority.choices, default=Job.Seniority.MID
    )
    experience_years = models.FloatField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)

    cv_file = models.FileField(upload_to="employee_cvs/", null=True, blank=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    is_parse_failed = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.BENCH, db_index=True
    )
    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
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

    def __str__(self) -> str:
        return self.full_name


class EmployeeJobMatch(models.Model):
    """Tracks a (employee, job) match through the staffing pipeline."""

    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        PURSUING = "pursuing", "Pursuing"
        APPLIED = "applied", "Applied"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        # HR marked this job as a bad fit — hidden from the browser, kept out of
        # re-ranking, and retained as a negative label for future training.
        DISMISSED = "dismissed", "Not a fit"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="matches"
    )
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="employee_matches"
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.SUGGESTED,
        db_index=True,
    )
    match_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    matched_skills = models.JSONField(default=list, blank=True)
    # Explainability (feature 014): skills the job requires but the employee lacks,
    # and the seniority distance (job_seniority - employee_seniority); null when unknown.
    missing_skills = models.JSONField(default=list, blank=True)
    seniority_gap = models.IntegerField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_matches",
    )
    notes = models.TextField(max_length=500, blank=True, default="")

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

    def __str__(self) -> str:
        return f"{self.employee_id} → job {self.job_id} ({self.status})"
