"""Persistent schedule config for verify_job_status / extract_job_dates."""

from __future__ import annotations

from django.db import models


def _default_hours():
    return [2, 14]


class VerifierSchedule(models.Model):
    """Singleton-per-command config + active-run tracking."""

    COMMAND_VERIFY = "verify_job_status"
    COMMAND_EXTRACT = "extract_job_dates"
    COMMAND_MORNING = "morning_refresh"
    COMMAND_CHOICES = [
        (COMMAND_VERIFY, "verify_job_status"),
        (COMMAND_EXTRACT, "extract_job_dates"),
        (COMMAND_MORNING, "morning_refresh"),
    ]

    command = models.CharField(max_length=32, choices=COMMAND_CHOICES, unique=True)

    enabled = models.BooleanField(default=False)
    batch_size = models.IntegerField(default=100)
    batches_per_day = models.IntegerField(default=2)
    # Explicit hours-of-day in UTC; takes priority over batches_per_day when set.
    hours_utc = models.JSONField(default=_default_hours)
    use_no_auth_check = models.BooleanField(default=False)
    headless = models.BooleanField(default=True)
    platform = models.CharField(max_length=32, default="linkedin")

    # Active-run trio. Set when a subprocess is spawned; cleared on exit.
    current_run_pid = models.IntegerField(null=True, blank=True)
    current_run_started_at = models.DateTimeField(null=True, blank=True)
    current_run_log_path = models.CharField(max_length=500, blank=True, default="")

    # Daemon bookkeeping — the UTC date last on which an hour fired.
    last_fired_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "verifier_schedules"
        ordering = ["command"]

    def __str__(self):
        flag = "ON" if self.enabled else "off"
        return f"{self.command} [{flag}] {self.batch_size}/batch · hrs={self.hours_utc}"
