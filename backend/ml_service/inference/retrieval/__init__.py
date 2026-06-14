"""Retrieval seam (feature 027): swappable candidate retrievers behind RETRIEVAL_MODE.

`get_retriever(mode, engine)` returns the implementation for the given mode. The
engine builds one at load and calls `.shortlist(...)` in match_cv. Config
(weights) is read from the environment with safe defaults so ml_service stays
Django-decoupled; settings.py documents/overrides them.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ml_service.inference.engine import InferenceEngine
    from ml_service.inference.retrieval.base import Retriever


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def get_retriever(mode: str, engine: "InferenceEngine") -> "Retriever":
    """Build the retriever for `mode` (exact | vector).

    Note: a per-request pgvector ANN retriever was prototyped and measured
    (feature 027 Stage B) but removed — it needed a 2× larger shortlist (the ANN
    ranks by embedding only, missing the domain/skill terms), so it ran MORE of
    the expensive decoder re-scores than the in-memory `vector` retriever for no
    latency win. pgvector remains the pool STORE (load-at-startup + upsert), just
    not a retriever.
    """
    mode = (mode or "exact").lower()
    if mode == "vector":
        from ml_service.inference.retrieval.vector import VectorRetriever
        return VectorRetriever(engine, w_gnn=_envf("RECALL_W_GNN", 0.6), w_text=_envf("RECALL_W_TEXT", 0.4))
    # exact / unknown → exact (safe default + A/B baseline)
    from ml_service.inference.retrieval.exact import ExactRetriever
    return ExactRetriever(engine)
