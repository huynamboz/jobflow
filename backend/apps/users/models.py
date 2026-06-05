import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CANDIDATE = "candidate"
        RECRUITER = "recruiter"
        ADMIN = "admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CANDIDATE)

    # Notification preferences (feature 012-employee-mvp)
    notify_daily_digest = models.BooleanField(default=True)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        db_table = "users"
