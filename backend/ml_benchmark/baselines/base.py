from __future__ import annotations

from abc import ABC, abstractmethod

from ml_benchmark.graph.schema import CVData, JobData


class Scorer(ABC):
    """Abstract base class for CV-Job scoring baselines."""

    @abstractmethod
    def score(self, cv: CVData, job: JobData) -> float:
        """Return a relevance score for a (cv, job) pair."""

    def score_batch(self, cvs: list[CVData], jobs: list[JobData]) -> list[float]:
        """Score a batch of (cv, job) pairs. Override for vectorized impl."""
        return [self.score(cv, job) for cv, job in zip(cvs, jobs)]
