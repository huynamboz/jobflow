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
    """Small MLP: features → class logits (binary or 3-class ordinal)."""

    def __init__(self, input_dim: int, hidden: int = 32, num_classes: int = 1) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.net(x)
        return out if self.num_classes > 1 else out.squeeze(-1)


class Reranker:
    """MLP-based reranker for Stage 2 ranking.

    Train on (CV, Job, label) pairs using feature vectors.
    At inference, score candidates retrieved by Stage 1.
    """

    def __init__(self, feature_extractor: FeatureExtractor, ordinal: bool = True) -> None:
        self._fe = feature_extractor
        self._model: _RerankerMLP | None = None
        self._trained = False
        self._ordinal = ordinal  # True = 3-class (0/1/2), False = binary

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
        """Train MLP reranker on labeled pairs.

        Labels for ordinal mode: 0=not suitable, 1=suitable, 2=very suitable.
        Labels for binary mode: 0=negative, 1=positive.
        """
        logger.info("Extracting features for %d pairs...", len(labels))
        X = self._fe.extract_batch(cvs, jobs, cv_indices, job_indices, gnn_scores=gnn_scores, stage1_scores=stage1_scores)
        y = np.array(labels, dtype=np.int64 if self._ordinal else np.float32)

        if len(y) == 0 or len(np.unique(y)) < 2:
            logger.warning("Not enough data to train reranker")
            return {}

        X_t = torch.from_numpy(X.astype(np.float32))
        input_dim = X.shape[1]

        if self._ordinal:
            num_classes = 3
            y_t = torch.from_numpy(y)  # long tensor for CrossEntropyLoss
            self._model = _RerankerMLP(input_dim, num_classes=num_classes)
            loss_fn = nn.CrossEntropyLoss()
        else:
            self._model = _RerankerMLP(input_dim, num_classes=1)
            y_t = torch.from_numpy(y.astype(np.float32))
            loss_fn = nn.BCEWithLogitsLoss()

        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)

        self._model.train()
        for _ in range(epochs):
            logits = self._model(X_t)
            loss = loss_fn(logits, y_t)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        self._trained = True

        # Compute accuracy
        self._model.eval()
        with torch.no_grad():
            if self._ordinal:
                preds = self._model(X_t).argmax(dim=1).numpy()
            else:
                preds = (torch.sigmoid(self._model(X_t)).numpy() >= 0.5).astype(int)
            accuracy = float((preds == y).mean())

        logger.info(
            "Reranker trained (%s): accuracy=%.3f, loss=%.4f, samples=%d",
            "ordinal" if self._ordinal else "binary",
            accuracy, loss.item(), len(y),
        )
        return {"accuracy": accuracy, "loss": loss.item(), "samples": len(y)}

    def score(self, cv: CVData, job: JobData, *, gnn_score: float = 0.0) -> float:
        """Score a single (CV, Job) pair. Returns ranking score in [0, 1].

        Ordinal mode: expected class value (0*p0 + 1*p1 + 2*p2) / 2.
        Binary mode: sigmoid probability.
        """
        if not self._trained or self._model is None:
            return 0.5
        X = torch.from_numpy(self._fe.extract(cv, job, gnn_score=gnn_score).reshape(1, -1))
        self._model.eval()
        with torch.no_grad():
            logits = self._model(X)
            return self._logits_to_score(logits)

    def _logits_to_score(self, logits: torch.Tensor) -> float:
        """Convert model output logits to a single ranking score [0, 1]."""
        if self._ordinal:
            # Expected match quality: (0*p0 + 1*p1 + 2*p2) / 2 → [0, 1]
            probs = torch.softmax(logits, dim=-1)
            weights = torch.tensor([0.0, 1.0, 2.0])
            expected = (probs * weights).sum(dim=-1)
            return float(expected.squeeze() / 2.0)
        else:
            return float(torch.sigmoid(logits).squeeze())

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
        X_t = torch.from_numpy(X.astype(np.float32))
        self._model.eval()
        with torch.no_grad():
            logits = self._model(X_t)
            if self._ordinal:
                probs = torch.softmax(logits, dim=-1)
                weights = torch.tensor([0.0, 1.0, 2.0])
                scores = (probs * weights).sum(dim=-1) / 2.0
            else:
                scores = torch.sigmoid(logits)
        return scores.numpy()

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
            json.dump({
                "trained": self._trained,
                "input_dim": len(FeatureExtractor.FEATURE_NAMES),
                "ordinal": self._ordinal,
                "num_classes": 3 if self._ordinal else 1,
            }, f)
        logger.info("Reranker saved to %s", path)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        model_path = path / "reranker.pt"
        meta_path = path / "reranker_meta.json"
        if model_path.exists() and meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            input_dim = meta.get("input_dim", len(FeatureExtractor.FEATURE_NAMES))
            self._ordinal = meta.get("ordinal", False)
            num_classes = meta.get("num_classes", 3 if self._ordinal else 1)
            self._model = _RerankerMLP(input_dim, num_classes=num_classes)
            self._model.load_state_dict(torch.load(model_path, weights_only=True))
            self._model.eval()
            self._trained = True
            logger.info("Reranker loaded from %s (ordinal=%s)", path, self._ordinal)
        else:
            logger.warning("No reranker model found at %s", path)
