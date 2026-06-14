"""ExactRetriever (feature 027) — the A/B parity baseline.

Reproduces today's stage-1 behaviour: score the FULL pool with the exact
composite `_score_pair_fast`, return the top-k. With RETRIEVAL_MODE=exact and
k ≥ retrieve_n, the engine's final results are byte-for-byte identical to the
pre-027 code. O(N) Python — only for parity/rollback, not the hot path.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch

    from ml_service.graph.schema import CVData
    from ml_service.inference.engine import InferenceEngine


class ExactRetriever:
    def __init__(self, engine: "InferenceEngine") -> None:
        self._engine = engine

    def shortlist(
        self,
        cv: "CVData",
        cv_text_vec: np.ndarray,
        cv_gnn_emb: "torch.Tensor | None",
        k: int,
    ) -> list[tuple[int, float]]:
        eng = self._engine
        scored: list[tuple[int, float]] = []
        for i, job in enumerate(eng._jobs):
            score, _comps = eng._score_pair_fast(cv, job, i, cv_text_vec, cv_gnn_emb)
            scored.append((i, float(score)))
        # top-k by composite, descending; tie-break by job_idx for determinism
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[: max(0, k)]
