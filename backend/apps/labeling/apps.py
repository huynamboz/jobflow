from django.apps import AppConfig


class LabelingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.labeling"
    label = "labeling"

    def ready(self):
        # On server start, any batch still marked "running" was interrupted —
        # reset it so the UI shows the correct state and the user can restart.
        try:
            from apps.labeling.models import LabelingBatch
            stale = LabelingBatch.objects.filter(status=LabelingBatch.STATUS_RUNNING)
            count = stale.update(status=LabelingBatch.STATUS_CANCELLED)
            if count:
                import logging
                logging.getLogger(__name__).warning(
                    "Reset %d stale running batch(es) to cancelled on startup", count
                )
        except Exception:
            pass
