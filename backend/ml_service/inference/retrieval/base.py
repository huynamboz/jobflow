"""Retriever interface (feature 027). See specs/027-job-retrieval-scaling/contracts/retriever.md.

A Retriever produces a candidate *shortlist* of pool job indices for one CV. It
governs RECALL only — the engine re-scores the shortlist with the exact 4-term
composite + reranker + Platt calibration, unchanged. So two retrievers that
return the same set yield identical final results regardless of `recall_sim`.

Implementations (selected by RETRIEVAL_MODE):
  exact    — full composite over all N (today's loop); the A/B parity baseline.
  vector   — in-memory matmul over precomputed unit-norm pool matrices (Stage A).
  pgvector — Postgres ANN (Stage B).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:  # avoid a runtime import cycle (engine imports the factory)
    import torch

    from ml_service.graph.schema import CVData


class Retriever(Protocol):
    """Selects ≤ k pool indices to hand to exact scoring."""

    def shortlist(
        self,
        cv: "CVData",
        cv_text_vec: np.ndarray,            # (384,) MiniLM CV text vector
        cv_gnn_emb: "torch.Tensor | None",  # (D,) inductive CV GNN emb; None in text-only mode
        k: int,
    ) -> list[tuple[int, float]]:
        """Return [(job_idx, recall_sim)], len ≤ k, descending by recall_sim.

        Contract:
        - job_idx indexes engine._jobs (so downstream scoring is unchanged).
        - only pool-eligible jobs are ever returned (the pool already enforces this).
        - bounded by k; fewer only if the pool has fewer jobs.
        - recall_sim orders the shortlist; it does NOT replace the final score.
        - deterministic given the pool (ties broken by job_idx).
        """
        ...
