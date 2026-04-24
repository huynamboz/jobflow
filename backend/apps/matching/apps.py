import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MatchingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.matching"

    def ready(self):
        # Pre-warm inference engine in background so first user request is fast
        threading.Thread(target=self._warmup, daemon=True).start()

    @staticmethod
    def _warmup():
        try:
            from apps.matching.services.matching_service import _get_engine
            _get_engine()
            logger.info("Inference engine warmed up.")
            print("[ML] Inference engine warmed up and ready.", flush=True)
        except Exception as e:
            logger.warning("Engine warm-up skipped: %s", e)
            print(f"[ML] Engine warm-up skipped: {e}", flush=True)
