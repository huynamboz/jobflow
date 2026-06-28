from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.jobs.models import Job


class Employee(models.Model):
    """A staffer of the company whose CV is on file. Not a Django User.

    Owned + managed by HR/admin users. Application progress lives on each
    EmployeeJobMatch (the job pipeline), not on the employee.
    """

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
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return self.full_name


class EmployeeCV(models.Model):
    """A versioned CV (PDF) for an employee with its OWN parse result.

    An employee can hold several CV versions; exactly one is ``is_active`` at a
    time and its parsed fields are mirrored onto the parent ``Employee`` row —
    which is what the matching engine reads — so ranking stays unchanged.
    Switching the active version copies that version's parse onto the employee
    and re-matches. (Feature 027.)
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="cvs"
    )
    cv_file = models.FileField(upload_to="employee_cvs/")
    label = models.CharField(max_length=200, blank=True, default="")

    # per-version parse snapshot (the ranking-relevant fields)
    position = models.CharField(max_length=200, blank=True, default="")
    seniority = models.IntegerField(
        choices=Job.Seniority.choices, default=Job.Seniority.MID
    )
    experience_years = models.FloatField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    is_parse_failed = models.BooleanField(default=False)

    is_active = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "employee_cvs"
        ordering = ["-is_active", "-created_at"]
        constraints = [
            # at most one active CV per employee
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_active=True),
                name="uniq_active_cv_per_employee",
            ),
        ]

    def __str__(self) -> str:
        return f"CV<{self.employee_id}> {self.label or self.cv_file.name}"


class EmployeeJobMatch(models.Model):
    """Tracks a (employee, job) match through the staffing pipeline."""

    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        PURSUING = "pursuing", "Pursuing"
        APPLIED = "applied", "Applied"            # submitted, awaiting client
        WON = "won", "Accepted"                   # client accepted → project won
        IN_PROGRESS = "in_progress", "In progress"  # team is delivering the project
        COMPLETED = "completed", "Completed"      # project delivered / done
        LOST = "lost", "Rejected"                 # client rejected
        # HR marked this job as a bad fit — hidden from the browser, kept out of
        # re-ranking, and retained as a negative label for future training.
        DISMISSED = "dismissed", "Not a fit"

    # Statuses meaning an application was already sent — hidden from the suggestion
    # browse on the employee detail (they live on the job-tracking pipeline instead).
    APPLIED_STATUSES = ("applied", "won", "in_progress", "completed", "lost")

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
    # 025: subset of missing_skills the employee likely covers via a RELATED
    # skill (skill graph) → {"html_css": "sass"}. Display-only nuance.
    covered_skills = models.JSONField(default=dict, blank=True)
    # 025: provenance of the overall score (stage-1 components+weights, reranker,
    # gates, rank_score) — renders as "How this score is computed" on the UI.
    score_breakdown = models.JSONField(default=dict, blank=True)
    seniority_gap = models.IntegerField(null=True, blank=True)
    # Per-dimension fit from the reranker: skill_fit / experience_fit /
    # seniority_fit / domain_fit → "good" | "ok" | "weak". Empty until (re)matched.
    dim_scores = models.JSONField(default=dict, blank=True)
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
