"""VectorRetriever (feature 027, Stage A) — in-memory vectorized recall.

Replaces the O(N) Python loop. The recall signal is a vectorized PROXY of the
full composite (not just embeddings): it mirrors base_score = α·gnn + β·skill +
γ·seniority + δ·domain with the SERVING weights, where the only non-vectorizable
term — the GNN decoder — is approximated by embedding cosine. Measured finding
(research D2′): pure-embedding recall fails because δ=0.40 domain + skill
dominate the composite; including them restores recall@shortlist ≈ 1.0 at small
RETRIEVE_K. The exact composite (real decoder + penalties) still runs on the
shortlist, so quality/calibration are unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch

    from ml_service.graph.schema import CVData
    from ml_service.inference.engine import InferenceEngine

_EPS = 1e-8


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + _EPS)


class VectorRetriever:
    def __init__(self, engine: "InferenceEngine", w_gnn: float, w_text: float) -> None:
        self._engine = engine
        # blend inside the gnn term (mirrors _gnn_score_fast: 0.6·gnn + 0.4·text)
        self._w_gnn = float(w_gnn)
        self._w_text = float(w_text)
        # recall features are built lazily in shortlist() (and rebuilt after any
        # pool reload that invalidates them) — nothing to do here.

    def _domain_vec(self, cv_role: str) -> np.ndarray:
        """Vectorized _role_domain_fit(cv_role, job) over the pool: 1.0 same role,
        0.7 related, 0.5 unknown role, 0.0 mismatch. Computed via a per-category
        lookup (≤ ~11 categories) then gathered onto the per-job role array."""
        eng = self._engine
        related = eng._RELATED_DOMAINS
        cats = set(eng._job_role_cat)
        score = {}
        for c in cats:
            if c:
                score[c] = 1.0 if cv_role == c else (0.7 if (cv_role, c) in related else 0.0)
            else:
                score[c] = 0.5
        return np.array([score[c] for c in eng._job_role_cat], dtype=np.float32)

    def shortlist(
        self,
        cv: "CVData",
        cv_text_vec: np.ndarray,
        cv_gnn_emb: "torch.Tensor | None",
        k: int,
    ) -> list[tuple[int, float]]:
        eng = self._engine
        n = len(eng._jobs)
        if n == 0:
            return []

        # composite-proxy features are built lazily and invalidated (set to None)
        # on every pool install — rebuild here if a reload cleared them.
        if getattr(eng, "_recall_vocab", None) is None:
            eng._build_recall_features()

        # --- gnn term (decoder proxy): 0.6·emb-cos + 0.4·text-cos (text-only → text) ---
        text_cos = eng._job_text_unit @ _unit(np.asarray(cv_text_vec, dtype=np.float32))  # (N,)
        if eng._job_emb_unit is not None and cv_gnn_emb is not None:
            gnn_cos = eng._job_emb_unit @ _unit(cv_gnn_emb.detach().cpu().numpy().astype(np.float32))
            gnn_term = self._w_gnn * gnn_cos + self._w_text * text_cos
        else:
            gnn_term = text_cos

        # --- skill term: direct-match weighted overlap (semantic bonus dropped for recall) ---
        cv_skill_vec = np.zeros(len(eng._recall_vocab), dtype=np.float32)
        for sk in cv.skills:
            ci = eng._recall_vocab.get(sk)
            if ci is not None:
                cv_skill_vec[ci] = 1.0
        skill = (eng._job_skill_mat @ cv_skill_vec) / eng._job_skill_total          # (N,) in [0,1]

        # --- seniority term: max(0, 1 - 0.4·|Δ|) ---
        sen = np.maximum(0.0, 1.0 - 0.4 * np.abs(float(int(cv.seniority)) - eng._job_seniority_arr))

        # --- domain term (δ, the dominant weight) ---
        domain = self._domain_vec(eng._cv_role(cv))

        # blend with the SERVING hybrid weights so recall ranks ≈ the composite
        recall = (eng._alpha * gnn_term + eng._beta * skill
                  + eng._gamma * sen + eng._delta * domain)

        k_eff = min(max(0, k), n)
        if k_eff == 0:
            return []
        idx = np.arange(n) if k_eff >= n else np.argpartition(-recall, k_eff - 1)[:k_eff]
        order = idx[np.argsort(-recall[idx], kind="stable")]
        return [(int(i), float(recall[i])) for i in order]
