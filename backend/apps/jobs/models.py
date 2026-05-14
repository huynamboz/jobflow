from django.db import models
from django.utils import timezone


class Platform(models.Model):
    """Job platform: LinkedIn, Indeed, Adzuna, Remotive, etc."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)  # "linkedin", "indeed"
    base_url = models.URLField(max_length=500, blank=True, default="")
    logo_url = models.URLField(max_length=1000, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platforms"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Company(models.Model):
    """Company that posts jobs. Can appear on multiple platforms."""

    name = models.CharField(max_length=300, db_index=True)
    logo_url = models.URLField(max_length=1000, blank=True, default="")
    website_url = models.URLField(max_length=1000, blank=True, default="")
    industry = models.CharField(max_length=200, blank=True, default="")
    size = models.CharField(max_length=100, blank=True, default="")  # "11-50", "1000+"
    location = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # M2M with Platform through CompanyPlatform
    platforms = models.ManyToManyField(Platform, through="CompanyPlatform", blank=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CompanyPlatform(models.Model):
    """Company presence on a specific platform (profile URL, etc.)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="platform_profiles")
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name="company_profiles")
    profile_url = models.URLField(max_length=1000, blank=True, default="")  # e.g. LinkedIn company page

    class Meta:
        db_table = "company_platforms"
        unique_together = ("company", "platform")

    def __str__(self):
        return f"{self.company.name} @ {self.platform.name}"


class Job(models.Model):
    """Job posting from a specific platform."""

    class Seniority(models.IntegerChoices):
        INTERN = 0
        JUNIOR = 1
        MID = 2
        SENIOR = 3
        LEAD = 4
        MANAGER = 5

    class JobType(models.TextChoices):
        FULL_TIME = "full-time"
        PART_TIME = "part-time"
        CONTRACT = "contract"
        REMOTE = "remote"
        HYBRID = "hybrid"
        ON_SITE = "on-site"
        OTHER = "other"

    # Relations
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name="jobs", null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs", null=True, blank=True)

    # Core fields
    title = models.CharField(max_length=500)
    description = models.TextField()
    location = models.CharField(max_length=300, blank=True, default="")
    seniority = models.IntegerField(choices=Seniority.choices, default=Seniority.MID)
    job_type = models.CharField(max_length=20, choices=JobType.choices, default=JobType.OTHER, blank=True)

    # Salary
    salary_min = models.IntegerField(default=0)
    salary_max = models.IntegerField(default=0)
    salary_currency = models.CharField(max_length=10, default="USD")

    # Extracted / enriched fields
    role_category = models.CharField(max_length=20, blank=True, default="other")
    experience_min = models.FloatField(null=True, blank=True)
    experience_max = models.FloatField(null=True, blank=True)

    # Source
    source_url = models.URLField(max_length=1000, blank=True, default="")
    fingerprint = models.CharField(max_length=32, db_index=True, blank=True, default="")
    applicant_count = models.CharField(max_length=100, blank=True, default="")

    # Skills (M2M through JobSkill)
    skills = models.ManyToManyField("skills.Skill", through="JobSkill", blank=True)

    # Status (legacy — kept for v1 backward compat; new code reads `lifecycle`)
    is_active = models.BooleanField(default=True)

    # Lifecycle tracking (spec 001-linkedin-job-verifier)
    LIFECYCLE_ACTIVE = "active"
    LIFECYCLE_STALE = "stale"
    LIFECYCLE_EXPIRED = "expired"
    LIFECYCLE_UNVERIFIED = "unverified"
    LIFECYCLE_CHOICES = [
        (LIFECYCLE_ACTIVE, "Active"),
        (LIFECYCLE_STALE, "Stale"),
        (LIFECYCLE_EXPIRED, "Expired"),
        (LIFECYCLE_UNVERIFIED, "Unverified"),
    ]
    lifecycle = models.CharField(
        max_length=20, choices=LIFECYCLE_CHOICES, default=LIFECYCLE_ACTIVE, db_index=True
    )
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    verification_attempts = models.IntegerField(default=0)
    verification_backoff_until = models.DateTimeField(null=True, blank=True, db_index=True)

    # Timestamps
    date_posted = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "jobs"
        ordering = ["-created_at"]
        # Dedup per platform (same fingerprint on same platform = duplicate)
        unique_together = ("platform", "fingerprint")
        indexes = [
            models.Index(fields=["platform", "lifecycle"], name="jobs_platform_lifecycle_idx"),
        ]

    def __str__(self):
        company_name = self.company.name if self.company else "Unknown"
        return f"{self.title} @ {company_name}"


class JobSkill(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="job_skills")
    skill = models.ForeignKey("skills.Skill", on_delete=models.CASCADE, related_name="job_skills")
    importance = models.IntegerField(default=3)  # 1-5

    class Meta:
        db_table = "job_skills"
        unique_together = ("job", "skill")


class JDExtractionBatch(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_ERROR, "Error"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    file_path = models.CharField(max_length=1000)
    fields_config = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total = models.IntegerField(default=0)
    done_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    workers = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jd_extraction_batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch #{self.id} ({self.status})"


class JDExtractionRecord(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"),
        (STATUS_ERROR, "Error"),
    ]

    batch = models.ForeignKey(JDExtractionBatch, on_delete=models.CASCADE, related_name="records")
    index = models.IntegerField()
    raw_data = models.JSONField(default=dict)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    combined_text = models.TextField(blank=True, default="")
    content_hash = models.CharField(max_length=32, db_index=True, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result = models.JSONField(null=True, blank=True)
    error_msg = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jd_extraction_records"
        ordering = ["index"]


class VerifierRunLog(models.Model):
    """One row per `verify_job_status` / `extract_job_dates` invocation.

    Powers the recent-runs table and per-day outcomes stacked-bar chart
    on the admin dashboard. See specs/003-admin-dashboard-v2/data-model.md.
    """

    COMMAND_VERIFY = "verify_job_status"
    COMMAND_EXTRACT = "extract_job_dates"
    COMMAND_CHOICES = [
        (COMMAND_VERIFY, "verify_job_status"),
        (COMMAND_EXTRACT, "extract_job_dates"),
    ]

    command = models.CharField(max_length=32, choices=COMMAND_CHOICES, db_index=True)
    platform = models.CharField(max_length=32, db_index=True)
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField()
    batch_size_requested = models.IntegerField()
    total_examined = models.IntegerField()
    skipped_unsupported_url = models.IntegerField(default=0)
    counts_by_outcome = models.JSONField(default=dict)
    session_expired_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    dry_run = models.BooleanField(default=False)

    class Meta:
        db_table = "verifier_run_logs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["command", "started_at"], name="verifier_run_cmd_time_idx"),
        ]

    def __str__(self):
        return f"{self.command}@{self.started_at:%Y-%m-%d %H:%M} n={self.total_examined}"

    @property
    def wall_clock_seconds(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0
