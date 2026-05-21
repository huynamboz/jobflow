from __future__ import annotations

import numpy as np

from ml_benchmark.baselines.base import Scorer
from ml_benchmark.graph.schema import CVData, JobData


class SkillOverlapScorer(Scorer):
    """Jaccard similarity between CV skills and Job required skills."""

    def score(self, cv: CVData, job: JobData) -> float:
        cv_set = set(cv.skills)
        job_set = set(job.skills)
        union = cv_set | job_set
        if not union:
            return 0.0
        return len(cv_set & job_set) / len(union)

    @staticmethod
    def build_matrix(cvs: list[CVData], jobs: list[JobData]) -> np.ndarray:
        """Vectorized Jaccard for all CV-job pairs → ndarray[n_cvs, n_jobs].

        Runs in milliseconds via matrix multiplication instead of Python loops.
        """
        all_skills: set[str] = set()
        for cv in cvs:
            all_skills.update(cv.skills)
        for job in jobs:
            all_skills.update(job.skills)
        skill2idx = {s: i for i, s in enumerate(all_skills)}
        n = len(skill2idx)

        cv_mat = np.zeros((len(cvs), n), dtype=np.float32)
        for i, cv in enumerate(cvs):
            for s in cv.skills:
                cv_mat[i, skill2idx[s]] = 1.0

        job_mat = np.zeros((len(jobs), n), dtype=np.float32)
        for i, job in enumerate(jobs):
            for s in job.skills:
                job_mat[i, skill2idx[s]] = 1.0

        intersection = cv_mat @ job_mat.T  # [n_cvs, n_jobs]
        cv_sizes = cv_mat.sum(axis=1, keepdims=True)   # [n_cvs, 1]
        job_sizes = job_mat.sum(axis=1, keepdims=True).T  # [1, n_jobs]
        union = cv_sizes + job_sizes - intersection
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(union > 0, intersection / union, 0.0)
