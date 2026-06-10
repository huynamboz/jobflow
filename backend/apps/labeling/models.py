from django.db import models


class LabelingCV(models.Model):
    cv_id            = models.IntegerField(unique=True)   # = CV.id
    source           = models.CharField(max_length=50, default="linkedin")
    role_category    = models.CharField(max_length=20, blank=True, default="other")
    skills           = models.JSONField(default=list)     # [{"name": str, "proficiency": int}]
    seniority        = models.CharField(max_length=20, default="MID")
    experience_years = models.FloatField(default=0.0)
    education        = models.CharField(max_length=20, default="BACHELOR")
    text_summary     = models.TextField(default="")
    pdf_path         = models.CharField(max_length=500, blank=True, default="")
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_cv"

    def __str__(self):
        return f"CV#{self.cv_id} ({self.seniority})"


class LabelingJob(models.Model):
    job_id         = models.IntegerField(unique=True)   # = Job.id
    title          = models.CharField(max_length=200, default="")
    role_category  = models.CharField(max_length=20, blank=True, default="other")
    skills         = models.JSONField(default=list)     # [{"name": str, "importance": int}]
    seniority      = models.CharField(max_length=20, default="MID")
    experience_min = models.FloatField(default=0.0)
    experience_max = models.FloatField(null=True, blank=True)
    salary_min     = models.IntegerField(null=True, blank=True)
    salary_max     = models.IntegerField(null=True, blank=True)
    text_summary   = models.TextField(default="")
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_job"

    def __str__(self):
        return f"Job#{self.job_id}: {self.title}"


class LabelingBatch(models.Model):
    STATUS_RUNNING   = "running"
    STATUS_DONE      = "done"
    STATUS_ERROR     = "error"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_RUNNING,   "Running"),
        (STATUS_DONE,      "Done"),
        (STATUS_ERROR,     "Error"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    total      = models.IntegerField(default=0)
    done_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    workers    = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"LabelBatch #{self.id} ({self.status})"


class SelectionReason(models.TextChoices):
    MEDIUM_OVERLAP = "medium_overlap", "Medium Overlap"
    HIGH_OVERLAP   = "high_overlap",   "High Overlap"
    HARD_NEGATIVE  = "hard_negative",  "Hard Negative"
    RANDOM         = "random",         "Random"
    # Feature 022: decision-boundary buckets (master plan Đợt 1)
    CROSS_DOMAIN_HARD_NEG  = "cross_domain_hard_neg",  "Cross-Domain Hard Negative"
    RELATED_SKILL_POSITIVE = "related_skill_positive", "Related-Skill Positive"
    SENIORITY_HARD_NEG     = "seniority_hard_neg",     "Seniority Hard Negative"
    MISSING_MUST_HAVE      = "missing_must_have",      "Missing Must-Have"
    BOUNDARY_MEDIUM        = "boundary_medium",        "Boundary Medium"


class PairStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    LABELED = "labeled", "Labeled"
    SKIPPED = "skipped", "Skipped"


REASON_PRIORITY = {
    SelectionReason.MEDIUM_OVERLAP: 1,
    SelectionReason.HIGH_OVERLAP:   2,
    SelectionReason.HARD_NEGATIVE:  3,
    SelectionReason.RANDOM:         4,
    # 022 buckets: label before RANDOM-era leftovers, after the legacy core
    SelectionReason.CROSS_DOMAIN_HARD_NEG:  5,
    SelectionReason.RELATED_SKILL_POSITIVE: 6,
    SelectionReason.SENIORITY_HARD_NEG:     7,
    SelectionReason.MISSING_MUST_HAVE:      8,
    SelectionReason.BOUNDARY_MEDIUM:        9,
}


class PairQueue(models.Model):
    cv                  = models.ForeignKey(LabelingCV, on_delete=models.CASCADE, related_name="pairs")
    job                 = models.ForeignKey(LabelingJob, on_delete=models.CASCADE, related_name="pairs")
    skill_overlap_score = models.FloatField(default=0.0)
    bm25_score          = models.FloatField(default=0.0)
    selection_reason    = models.CharField(max_length=30, choices=SelectionReason.choices)
    priority            = models.IntegerField(default=4)
    status              = models.CharField(max_length=20, choices=PairStatus.choices, default=PairStatus.PENDING)
    split               = models.CharField(max_length=10, default="train")
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_pair_queue"
        unique_together = ("cv", "job")
        ordering = ["priority", "cv_id"]

    def __str__(self):
        return f"Pair CV#{self.cv_id}–Job#{self.job_id} [{self.status}]"


class LabelValue(models.IntegerChoices):
    NOT_SUITABLE = 0, "Không phù hợp"
    SUITABLE     = 1, "Phù hợp"
    STRONG_FIT   = 2, "Rất phù hợp"


class DimScore(models.IntegerChoices):
    BAD  = 0, "Không phù hợp"
    OK   = 1, "Tạm được"
    GOOD = 2, "Tốt"


class HumanLabel(models.Model):
    pair           = models.ForeignKey(PairQueue, on_delete=models.CASCADE, related_name="labels")
    batch          = models.ForeignKey(LabelingBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="labels")
    skill_fit      = models.IntegerField(choices=DimScore.choices)
    seniority_fit  = models.IntegerField(choices=DimScore.choices)
    experience_fit = models.IntegerField(choices=DimScore.choices)
    domain_fit     = models.IntegerField(choices=DimScore.choices)
    overall        = models.IntegerField(choices=LabelValue.choices)
    note           = models.TextField(blank=True, default="")
    labeled_by     = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_human_label"

    @property
    def binary_label(self) -> int:
        return 1 if self.overall >= 1 else 0

    def __str__(self):
        return f"Label for Pair#{self.pair_id} overall={self.overall}"
