"""Persisted job-pool snapshot.

Lets the live server process and the maintenance (``rebuild_job_pool`` /
``morning_refresh``) process share the latest inductively-encoded job pool —
without retraining and without a server restart. A snapshot is only trusted if
its ``model_sig`` matches the engine's loaded model (the job embeddings live in
the same latent space as that model's CV embeddings).

Layout (``checkpoints/job_pool/``):
    jobs.json          list[JobData] (same serialization as the checkpoint)
    job_embeddings.pt  torch.Tensor [N, H]  — GNN job embeddings, order == jobs.json
    job_text_vecs.npy  np.ndarray [N, 384] — sentence-embeddings of each job text
    meta.json          {count, model_sig, skill_skipped_edges, source, built_at}
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path

import numpy as np
import torch

from ml_service.graph.schema import JobData
from ml_service.inference.checkpoint import _dict_to_job, _job_to_dict

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path("checkpoints/job_pool")


def save(
    directory: Path | str,
    jobs: list[JobData],
    embeddings: torch.Tensor,
    text_vecs: np.ndarray,
    model_sig: str,
    *,
    skill_skipped_edges: int = 0,
) -> Path:
    """Atomically write the snapshot. Writes to a temp sibling dir then swaps it
    into place, so a reader never observes a partial set and a crash mid-write
    leaves the previous snapshot intact."""
    directory = Path(directory)
    if not (len(jobs) == embeddings.shape[0] == text_vecs.shape[0]):
        raise ValueError("save: jobs/embeddings/text_vecs length mismatch")

    tmp = directory.with_name(directory.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    with open(tmp / "jobs.json", "w", encoding="utf-8") as f:
        json.dump([_job_to_dict(j) for j in jobs], f, ensure_ascii=False)
    torch.save(embeddings.detach().cpu(), tmp / "job_embeddings.pt")
    np.save(tmp / "job_text_vecs.npy", np.asarray(text_vecs, dtype=np.float32))
    meta = {
        "count": len(jobs),
        "model_sig": model_sig,
        "skill_skipped_edges": int(skill_skipped_edges),
        "source": "live",
        "built_at": time.time(),
    }
    with open(tmp / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Swap tmp -> directory atomically (rename can't overwrite a non-empty dir on
    # POSIX, so move the old one aside first, then delete it).
    if directory.exists():
        old = directory.with_name(directory.name + ".old")
        if old.exists():
            shutil.rmtree(old)
        os.replace(directory, old)
        os.replace(tmp, directory)
        shutil.rmtree(old, ignore_errors=True)
    else:
        os.replace(tmp, directory)

    logger.info("job_pool snapshot saved: %d jobs → %s", len(jobs), directory)
    return directory


def load(
    directory: Path | str,
    model_sig: str,
) -> tuple[list[JobData], torch.Tensor, np.ndarray] | None:
    """Load the snapshot if present AND its model_sig matches. Returns
    (jobs, embeddings, text_vecs) or None (caller falls back to checkpoint jobs)."""
    directory = Path(directory)
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("model_sig") != model_sig:
            logger.warning(
                "job_pool snapshot model_sig mismatch (%s != %s) — ignoring",
                meta.get("model_sig"), model_sig,
            )
            return None
        with open(directory / "jobs.json", encoding="utf-8") as f:
            jobs = [_dict_to_job(d) for d in json.load(f)]
        embeddings = torch.load(directory / "job_embeddings.pt", weights_only=False)
        text_vecs = np.load(directory / "job_text_vecs.npy")
        if not (len(jobs) == embeddings.shape[0] == text_vecs.shape[0]):
            logger.warning("job_pool snapshot length mismatch — ignoring")
            return None
        return jobs, embeddings, text_vecs
    except Exception as exc:  # noqa: BLE001
        logger.warning("job_pool snapshot load failed: %s", exc)
        return None


def mtime(directory: Path | str) -> float:
    """Modification time of the snapshot (0.0 if absent). Used for hot-reload."""
    p = Path(directory) / "meta.json"
    return p.stat().st_mtime if p.exists() else 0.0
