"""Two-stage reranker: Stage 1 fast retrieve → Stage 2 MLP rerank.

Uses a small PyTorch MLP trained on feature vectors — no external deps needed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from ml_service.graph.schema import CVData, JobData
from ml_service.reranker.features import FeatureExtractor

logger = logging.getLogger(__name__)


class _RerankerMLP(nn.Module):
    """Small MLP: features → match probability."""

    def __init__(self, input_dim: int, hidden: int = 32) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class Reranker:
    """MLP-based reranker for Stage 2 ranking.

    Train on (CV, Job, label) pairs using feature vectors.
    At inference, score candidates retrieved by Stage 1.
    """

    def __init__(self, feature_extractor: FeatureExtractor) -> None:
        self._fe = feature_extractor
        self._model: _RerankerMLP | None = None
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    def train(
        self,
        cvs: list[CVData],
        jobs: list[JobData],
        cv_indices: list[int],
        job_indices: list[int],
        labels: list[int],
        *,
        epochs: int = 50,
        lr: float = 1e-3,
        gnn_scores: list[float] | None = None,
        stage1_scores: list[float] | None = None,
    ) -> dict[str, float]:
        """Train MLP reranker on labeled pairs."""
        logger.info("Extracting features for %d pairs...", len(labels))
        X = self._fe.extract_batch(cvs, jobs, cv_indices, job_indices, gnn_scores=gnn_scores, stage1_scores=stage1_scores)
        y = np.array(labels, dtype=np.float32)

        if len(y) == 0 or len(np.unique(y)) < 2:
            logger.warning("Not enough data to train reranker")
            return {}

        X_t = torch.from_numpy(X)
        y_t = torch.from_numpy(y)

        input_dim = X.shape[1]
        self._model = _RerankerMLP(input_dim)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)
        loss_fn = nn.BCEWithLogitsLoss()

        self._model.train()
        for epoch in range(epochs):
            logits = self._model(X_t)
            loss = loss_fn(logits, y_t)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        self._trained = True

        # Compute accuracy
        self._model.eval()
        with torch.no_grad():
            probs = torch.sigmoid(self._model(X_t)).numpy()
            preds = (probs >= 0.5).astype(int)
            accuracy = float((preds == y).mean())

        logger.info("Reranker trained: accuracy=%.3f, loss=%.4f, samples=%d",
                    accuracy, loss.item(), len(y))
        return {"accuracy": accuracy, "loss": loss.item(), "samples": len(y)}

    def score(self, cv: CVData, job: JobData, *, gnn_score: float = 0.0) -> float:
        """Score a single (CV, Job) pair. Returns probability of match.

        Args:
            gnn_score: GNN decode score for this pair (0-1). Default 0.0.
        """
        if not self._trained or self._model is None:
            return 0.5
        X = torch.from_numpy(self._fe.extract(cv, job, gnn_score=gnn_score).reshape(1, -1))
        self._model.eval()
        with torch.no_grad():
            prob = torch.sigmoid(self._model(X)).item()
        return prob

    def score_batch(
        self,
        cvs: list[CVData],
        jobs: list[JobData],
        cv_indices: list[int],
        job_indices: list[int],
        gnn_scores: list[float] | None = None,
    ) -> np.ndarray:
        """Score multiple pairs. Returns array of match probabilities.

        Args:
            gnn_scores: Optional list of GNN decode scores (one per pair).
                       If None, defaults to 0.0 for each pair.
        """
        if not self._trained or self._model is None:
            return np.full(len(cv_indices), 0.5)
        X = self._fe.extract_batch(cvs, jobs, cv_indices, job_indices, gnn_scores=gnn_scores)
        if len(X) == 0:
            return np.array([])
        X_t = torch.from_numpy(X)
        self._model.eval()
        with torch.no_grad():
            probs = torch.sigmoid(self._model(X_t)).numpy()
        return probs

    def feature_importance(self) -> dict[str, float]:
        """Approximate feature importance from first layer weights."""
        if not self._trained or self._model is None:
            return {}
        first_layer = self._model.net[0]
        weights = first_layer.weight.data.abs().mean(dim=0).numpy()
        return {
            name: float(w)
            for name, w in zip(FeatureExtractor.FEATURE_NAMES, weights)
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        if self._model is not None:
            torch.save(self._model.state_dict(), path / "reranker.pt")
        with open(path / "reranker_meta.json", "w") as f:
            json.dump({"trained": self._trained, "input_dim": len(FeatureExtractor.FEATURE_NAMES)}, f)
        logger.info("Reranker saved to %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        model_path = path / "reranker.pt"
        meta_path = path / "reranker_meta.json"
        if model_path.exists() and meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            input_dim = meta.get("input_dim", len(FeatureExtractor.FEATURE_NAMES))
            self._model = _RerankerMLP(input_dim)
            self._model.load_state_dict(torch.load(model_path, weights_only=True))
            self._model.eval()
            self._trained = True
            logger.info("Reranker loaded from %s", path)
        else:
            logger.warning("No reranker model found at %s", path)
