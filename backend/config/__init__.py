# Ensure Celery app loads when Django starts so @shared_task can find it.
# Wrapped in try/except — celery is optional for non-notification dev work.
try:
    from .celery import app as celery_app  # noqa: F401

    __all__ = ("celery_app",)
except ImportError:  # pragma: no cover - celery not installed
    pass
