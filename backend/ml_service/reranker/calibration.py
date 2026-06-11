"""Score calibration via Platt scaling (logistic regression).

Maps raw scores to calibrated probabilities so that:
- score 0.7 ≈ 70% probability of being a good match
- threshold becomes meaningful
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class PlattCalibrator:
    """Platt scaling: fit sigmoid to map raw scores → calibrated probabilities."""

    def __init__(self) -> None:
        self._a: float = 1.0  # sigmoid slope
        self._b: float = 0.0  # sigmoid offset
        self._fitted = False
        self.trained_with: str = ""  # sha256(reranker.pt)[:16] at fit time (025)

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> None:
        """Fit Platt scaling parameters on validation data.

        scores: raw model scores (e.g., stage1 hybrid scores)
        labels: binary labels (0/1)
        """
        scores = np.asarray(scores, dtype=np.float64)
        labels = np.asarray(labels, dtype=np.float64)

        if len(scores) < 10 or len(np.unique(labels)) < 2:
            logger.warning("Not enough data for calibration (%d samples)", len(scores))
            return

        # Platt scaling = unregularized 1-D logistic regression (Platt 1999).
        # 025: the previous hand-rolled GD (lr=0.01, 1000 iters) did NOT
        # converge — it compressed the whole score range into P∈[0.37,0.54].
        # sklearn LBFGS is the canonical implementation (what
        # CalibratedClassifierCV(method="sigmoid") uses); C=1e6 ≈ no penalty.
        from sklearn.linear_model import LogisticRegression

        lr_model = LogisticRegression(solver="lbfgs", C=1e6, max_iter=1000)
        lr_model.fit(scores.reshape(-1, 1), labels)
        a = float(lr_model.coef_[0][0])
        b = float(lr_model.intercept_[0])

        if a <= 0:
            # The ranking signal anti-predicts labels — calibrating it would
            # invert the displayed order vs rank order. Refuse loudly.
            logger.error(
                "Platt fit produced non-positive slope a=%.4f — ranking signal "
                "anti-predicts labels; calibration REFUSED (fitted stays False).", a)
            return

        self._a = a
        self._b = b
        self._fitted = True

        calibrated = self.transform(scores)
        pred = (calibrated >= 0.5).astype(int)
        accuracy = float((pred == labels).mean())
        span = float(calibrated.max() - calibrated.min())
        logger.info("Platt calibration fitted: a=%.3f, b=%.3f, accuracy=%.3f, span=%.3f",
                    self._a, self._b, accuracy, span)
        self._log_reliability(scores, labels)

    def _log_reliability(self, scores: np.ndarray, labels: np.ndarray) -> None:
        """025: per-decile reliability — mean predicted P vs observed match
        rate. Contract gate: |predicted − observed| ≤ 0.15 per populated decile."""
        preds = self.transform(scores)
        edges = np.quantile(scores, np.linspace(0, 1, 11))
        logger.info("Calibration reliability (val):  decile | n | mean P̂ | observed")
        worst = 0.0
        for i in range(10):
            lo, hi = edges[i], edges[i + 1]
            m = (scores >= lo) & (scores <= hi if i == 9 else scores < hi)
            if m.sum() < 5:
                continue
            gap = abs(float(preds[m].mean()) - float(labels[m].mean()))
            worst = max(worst, gap)
            logger.info("  [%.3f, %.3f] | %4d | %.3f | %.3f%s",
                        lo, hi, int(m.sum()), float(preds[m].mean()),
                        float(labels[m].mean()), "  ⚠ gap>0.15" if gap > 0.15 else "")
        logger.info("Reliability worst-decile gap: %.3f (gate ≤ 0.15)", worst)

    def transform(self, scores: np.ndarray) -> np.ndarray:
        """Apply calibration to raw scores → calibrated probabilities."""
        if not self._fitted:
            return scores
        z = self._a * np.asarray(scores, dtype=np.float64) + self._b
        return 1.0 / (1.0 + np.exp(-z))

    def transform_single(self, score: float) -> float:
        """Calibrate a single score."""
        if not self._fitted:
            return score
        z = self._a * score + self._b
        return float(1.0 / (1.0 + np.exp(-z)))

    def save(self, path: Path | str, *, trained_with: str = "") -> None:
        """025: trained_with = sha256(reranker.pt)[:16] — couples this artifact
        to the reranker whose score distribution it was fitted on (the engine
        warns at boot on mismatch, mirroring the A14 weight guard)."""
        path = Path(path)
        with open(path / "calibration.json", "w") as f:
            json.dump({"a": self._a, "b": self._b, "fitted": self._fitted,
                       "trained_with": trained_with or self.trained_with}, f)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        cal_path = path / "calibration.json"
        if cal_path.exists():
            with open(cal_path) as f:
                data = json.load(f)
            self._a = data["a"]
            self._b = data["b"]
            self._fitted = data["fitted"]
            self.trained_with = data.get("trained_with", "")
            logger.info("Calibration loaded: a=%.3f, b=%.3f", self._a, self._b)
