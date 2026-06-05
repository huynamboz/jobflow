from __future__ import annotations

import math
import re

from ml_benchmark.baselines.base import Scorer
from ml_benchmark.graph.schema import CVData, JobData


def _tokenize(text: str) -> list[str]:
    """Lowercase and split on non-alphanumeric characters."""
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Scorer(Scorer):
    """Okapi BM25 scorer — JD text as query, CV text as document.

    Call ``fit(cvs)`` before scoring to compute IDF statistics.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._idf: dict[str, float] = {}
        self._avgdl: float = 0.0
        self._fitted = False

    def fit(self, cvs: list[CVData]) -> BM25Scorer:
        """Compute IDF from the CV corpus."""
        n = len(cvs)
        if n == 0:
            self._fitted = True
            return self

        doc_freq: dict[str, int] = {}
        total_len = 0
        for cv in cvs:
            tokens = _tokenize(cv.text)
            total_len += len(tokens)
            unique = set(tokens)
            for term in unique:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        self._avgdl = total_len / n
        # IDF with smoothing: log((N - df + 0.5) / (df + 0.5) + 1)
        self._idf = {}
        for term, df in doc_freq.items():
            self._idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

        self._fitted = True
        return self

    def score(self, cv: CVData, job: JobData) -> float:
        """BM25 score: CV text is the document, JD text is the query."""
        if not self._fitted:
            raise RuntimeError("BM25Scorer.fit() must be called before scoring.")

        doc_tokens = _tokenize(cv.text)
        query_tokens = _tokenize(job.text)
        dl = len(doc_tokens)

        # Term frequency in document
        tf: dict[str, int] = {}
        for t in doc_tokens:
            tf[t] = tf.get(t, 0) + 1

        total = 0.0
        for q in query_tokens:
            if q not in self._idf:
                continue
            freq = tf.get(q, 0)
            idf = self._idf[q]
            numerator = freq * (self._k1 + 1)
            denominator = freq + self._k1 * (1 - self._b + self._b * dl / max(self._avgdl, 1e-9))
            total += idf * numerator / denominator

        return total
