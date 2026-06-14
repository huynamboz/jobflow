"""Incremental pool diff (feature 027 Stage C).

content_hash captures every JobData field that affects the encoding (canonical
skills + importances, seniority, encode text) — identical hash ⇒ identical
embedding, so an unchanged job is never re-encoded.
"""
from __future__ import annotations

import hashlib

from ml_service.graph.schema import JobData


def content_hash(job: JobData) -> str:
    key = repr((tuple(job.skills), tuple(job.skill_importances), int(job.seniority), job.text))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:64]


def diff(jobs: list[JobData], stored: dict[int, str]):
    """Return (to_encode, to_evict_ids, current_hashes).

    to_encode  — jobs new or whose content changed (need encoding + upsert).
    to_evict   — stored job_ids no longer in the live catalog (delete from store).
    current    — {job_id: content_hash} for the whole live set.
    """
    current = {j.job_id: content_hash(j) for j in jobs}
    to_encode = [j for j in jobs if current[j.job_id] != stored.get(j.job_id)]
    cur_ids = set(current)
    to_evict = [jid for jid in stored if jid not in cur_ids]
    return to_encode, to_evict, current
