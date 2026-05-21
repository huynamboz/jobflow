from __future__ import annotations

import numpy as np

from ml_benchmark.baselines.base import Scorer
from ml_benchmark.embedding.base import EmbeddingProvider
from ml_benchmark.graph.schema import CVData, JobData


class CosineSimilarityScorer(Scorer):
    """Cosine similarity between CV and Job text embeddings."""

    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embed = embedding_provider

    def score(self, cv: CVData, job: JobData) -> float:
        vecs = self._embed.encode([cv.text, job.text])
        cv_vec, job_vec = vecs[0], vecs[1]
        norm_cv = np.linalg.norm(cv_vec)
        norm_job = np.linalg.norm(job_vec)
        if norm_cv == 0 or norm_job == 0:
            return 0.0
        return float(np.dot(cv_vec, job_vec) / (norm_cv * norm_job))

    def score_batch(self, cvs: list[CVData], jobs: list[JobData]) -> list[float]:
        if not cvs:
            return []
        texts = [cv.text for cv in cvs] + [job.text for job in jobs]
        vecs = self._embed.encode(texts)
        n = len(cvs)
        cv_vecs = vecs[:n]
        job_vecs = vecs[n:]
        # Normalize
        cv_norms = np.linalg.norm(cv_vecs, axis=1, keepdims=True)
        job_norms = np.linalg.norm(job_vecs, axis=1, keepdims=True)
        cv_norms = np.where(cv_norms == 0, 1.0, cv_norms)
        job_norms = np.where(job_norms == 0, 1.0, job_norms)
        cv_vecs = cv_vecs / cv_norms
        job_vecs = job_vecs / job_norms
        # Element-wise dot product for paired (cv_i, job_i)
        scores = np.sum(cv_vecs * job_vecs, axis=1)
        return scores.tolist()
