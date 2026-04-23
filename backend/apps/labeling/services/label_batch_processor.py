"""Background batch processor for LLM pair labeling."""

from __future__ import annotations

import atexit
import logging
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_cancel_events: dict[int, threading.Event] = {}
_threads: dict[int, threading.Thread] = {}
_active_pools: dict[int, ThreadPoolExecutor] = {}
_lock = threading.Lock()

WORKERS = 3


def _shutdown_all() -> None:
    """Cancel all running label batches — called on SIGTERM/SIGINT/atexit."""
    with _lock:
        events = list(_cancel_events.values())
        pools = list(_active_pools.values())
    for event in events:
        event.set()
    for pool in pools:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


atexit.register(_shutdown_all)

try:
    _prev_sigterm = signal.getsignal(signal.SIGTERM)

    def _signal_handler(signum, frame) -> None:
        _shutdown_all()
        if callable(_prev_sigterm) and _prev_sigterm not in (signal.SIG_DFL, signal.SIG_IGN):
            _prev_sigterm(signum, frame)

    signal.signal(signal.SIGTERM, _signal_handler)
except (OSError, ValueError):
    pass


def start_batch(batch_id: int, workers: int = WORKERS) -> None:
    with _lock:
        old_event  = _cancel_events.get(batch_id)
        old_thread = _threads.get(batch_id)

    if old_event and not old_event.is_set():
        old_event.set()
    if old_thread and old_thread.is_alive():
        old_thread.join(timeout=10)

    cancel_event = threading.Event()
    thread = threading.Thread(target=_run, args=(batch_id, cancel_event, workers), daemon=True)
    with _lock:
        _cancel_events[batch_id] = cancel_event
        _threads[batch_id] = thread
    thread.start()


def cancel_batch(batch_id: int) -> bool:
    with _lock:
        event = _cancel_events.get(batch_id)
    if event:
        event.set()
        return True
    return False


def is_running(batch_id: int) -> bool:
    with _lock:
        return batch_id in _cancel_events


def _label_one(pair_id: int) -> tuple[dict | None, str | None]:
    """Label a single pair. Returns (label_dict, error_msg)."""
    from apps.labeling.models import PairQueue
    from apps.labeling.services.llm_label_extractor import extract_label
    from apps.cvs.models import CV
    from apps.jobs.models import JDExtractionRecord
    from dataclasses import asdict

    try:
        pair = (
            PairQueue.objects
            .select_related("cv", "job")
            .get(id=pair_id)
        )
        cv  = pair.cv
        job = pair.job

        # Fetch full text from source models — text_summary is truncated to 600 chars
        try:
            cv_src = CV.objects.only("parsed_text", "raw_text").get(id=cv.cv_id)
            cv_full_text = cv_src.parsed_text or cv_src.raw_text or ""
        except CV.DoesNotExist:
            cv_full_text = cv.text_summary or ""

        try:
            jd_src = JDExtractionRecord.objects.only("combined_text").get(id=job.job_id)
            job_full_text = jd_src.combined_text or ""
        except JDExtractionRecord.DoesNotExist:
            job_full_text = job.text_summary or ""

        result = extract_label(
            cv_role=cv.role_category,
            cv_seniority=cv.seniority,
            cv_experience=cv.experience_years,
            cv_education=cv.education,
            cv_skills=cv.skills or [],
            cv_text=cv_full_text,
            job_title=job.title,
            job_role=job.role_category,
            job_seniority=job.seniority,
            job_experience_min=job.experience_min,
            job_experience_max=job.experience_max,
            job_skills=job.skills or [],
            job_text=job_full_text,
        )
        return asdict(result), None
    except Exception as exc:
        return None, str(exc)[:500]


def _run(batch_id: int, cancel_event: threading.Event, workers: int = WORKERS) -> None:
    # django.setup() must NOT be called here — Django is already initialised by
    # the web server process and calling setup() again in a thread re-triggers
    # every AppConfig.ready(), including the one that resets running batches to
    # "cancelled", which immediately kills the batch we just started.
    from django.db.models import F
    from apps.labeling.models import LabelingBatch, PairQueue, PairStatus, HumanLabel

    try:
        pending_ids = list(
            PairQueue.objects
            .filter(status=PairStatus.PENDING)
            .order_by("priority", "id")
            .values_list("id", flat=True)
        )

        # Sync counters with actual DB state — guards against restarts where
        # a previous run already created some labels and updated done_count,
        # but total was re-snapshotted to a smaller pending count.
        already_done = HumanLabel.objects.filter(batch_id=batch_id).count()
        LabelingBatch.objects.filter(id=batch_id).update(
            status=LabelingBatch.STATUS_RUNNING,
            total=already_done + len(pending_ids),
            done_count=already_done,
        )
        logger.info("LabelingBatch #%d: %d pending pairs to label", batch_id, len(pending_ids))

        pool = ThreadPoolExecutor(max_workers=workers)
        with _lock:
            _active_pools[batch_id] = pool
        future_to_pair: dict = {}
        cancelled = False
        CHUNK = workers * 2

        try:
            for i in range(0, len(pending_ids), CHUNK):
                if cancel_event.is_set():
                    cancelled = True
                    break
                for pair_id in pending_ids[i:i + CHUNK]:
                    if cancel_event.is_set():
                        cancelled = True
                        break
                    future_to_pair[pool.submit(_label_one, pair_id)] = pair_id
                if cancelled:
                    break

            for future in as_completed(future_to_pair):
                if cancel_event.is_set():
                    cancelled = True
                    for f in future_to_pair:
                        f.cancel()
                    break

                pair_id = future_to_pair[future]
                label_dict, error_msg = future.result()

                if label_dict is not None:
                    HumanLabel.objects.create(
                        pair_id=pair_id,
                        batch_id=batch_id,
                        skill_fit=label_dict["skill_fit"],
                        seniority_fit=label_dict["seniority_fit"],
                        experience_fit=label_dict["experience_fit"],
                        domain_fit=label_dict["domain_fit"],
                        overall=label_dict["overall"],
                        labeled_by=None,
                    )
                    PairQueue.objects.filter(id=pair_id).update(status=PairStatus.LABELED)
                    LabelingBatch.objects.filter(id=batch_id).update(done_count=F("done_count") + 1)
                else:
                    LabelingBatch.objects.filter(id=batch_id).update(error_count=F("error_count") + 1)
                    logger.warning("Pair #%d (batch %d) failed: %s", pair_id, batch_id, error_msg)
        finally:
            with _lock:
                _active_pools.pop(batch_id, None)
            pool.shutdown(wait=False, cancel_futures=True) if cancelled else pool.shutdown(wait=True)

        final_status = (
            LabelingBatch.STATUS_CANCELLED if cancel_event.is_set()
            else LabelingBatch.STATUS_DONE
        )
        LabelingBatch.objects.filter(id=batch_id).update(status=final_status)

    except Exception as exc:
        logger.error("LabelingBatch %d crashed: %s", batch_id, exc)
        LabelingBatch.objects.filter(id=batch_id).update(status=LabelingBatch.STATUS_ERROR)
    finally:
        with _lock:
            _cancel_events.pop(batch_id, None)
            _threads.pop(batch_id, None)
