"""Celery application factory.

Reads ``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND`` from Django settings.
Tasks live in ``apps.notifications.tasks`` (and any other app's ``tasks`` module
will be auto-discovered).
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("jobflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover - smoke only
    print(f"Request: {self.request!r}")
