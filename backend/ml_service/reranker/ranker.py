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


_DIM_NAMES = ["skill_fit", "experience_fit", "seniority_fit", "domain_fit"]


class _RerankerMLP(nn.Module):
    """Shared-trunk MLP with one main head (overall) + 4 auxiliary heads (dimensions).

    Auxiliary heads are only used during training (multi-task loss).
    At inference only the main head is used.
    """

    def __init__(self, input_dim: int, hidden: int = 64, num_classes: int = 1) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.trunk = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
        )
        self.main_head = nn.Linear(hidden, num_classes)
        # Auxiliary heads — one per dimension (3-class each)
        self.aux_heads = nn.ModuleList([nn.Linear(hidden, 3) for _ in _DIM_NAMES])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.trunk(x)
        out = self.main_head(z)
        return out if self.num_classes > 1 else out.squeeze(-1)

    def forward_all(self, x: torch.Tensor) -> tuple[torch.Tensor, list[torch.Tensor]]:
        """Return main logits + list of auxiliary logits (for training)."""
        z = self.trunk(x)
        main = self.main_head(z)
        aux = [head(z) for head in self.aux_heads]
        return main, aux


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
        dim_labels: list[dict] | None = None,
        aux_weight: float = 0.3,
    ) -> dict[str, float]:
        """Train MLP reranker with optional multi-task auxiliary heads.

        Labels for ordinal mode: 0=not suitable, 1=suitable, 2=very suitable.
        dim_labels: list of dicts with keys skill_fit/experience_fit/seniority_fit/domain_fit (0/1/2).
                    Pairs with missing dim label (-1) are masked out of that auxiliary loss.
        aux_weight: weight for auxiliary losses relative to main loss.
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
            y_t = torch.from_numpy(y)
            self._model = _RerankerMLP(input_dim, num_classes=num_classes)
            counts = np.bincount(y.astype(int), minlength=3).clip(1)
            weights = torch.tensor(len(y) / (3.0 * counts), dtype=torch.float32)
            main_loss_fn = nn.CrossEntropyLoss(weight=weights)
            logger.info("Class weights: %s", weights.tolist())
        else:
            self._model = _RerankerMLP(input_dim, num_classes=1)
            y_t = torch.from_numpy(y.astype(np.float32))
            main_loss_fn = nn.BCEWithLogitsLoss()

        # Build auxiliary label tensors (mask=-1 means missing → excluded from loss)
        use_multitask = self._ordinal and dim_labels is not None
        aux_tensors: list[torch.Tensor] = []
        if use_multitask:
            for dim in _DIM_NAMES:
                arr = np.array([d.get(dim, -1) for d in dim_labels], dtype=np.int64)
                aux_tensors.append(torch.from_numpy(arr))
            logger.info("Multi-task: auxiliary heads for %s (aux_weight=%.2f)", _DIM_NAMES, aux_weight)

        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)

        self._model.train()
        for _ in range(epochs):
            main_logits, aux_logits = self._model.forward_all(X_t)
            loss = main_loss_fn(main_logits, y_t)

            if use_multitask:
                for aux_l, y_aux in zip(aux_logits, aux_tensors):
                    mask = y_aux >= 0
                    if mask.sum() > 0:
                        # Each dim has its own inverse-freq weight
                        dim_counts = torch.bincount(y_aux[mask], minlength=3).float().clamp(min=1)
                        dim_w = mask.sum().float() / (3.0 * dim_counts)
                        aux_loss_fn = nn.CrossEntropyLoss(weight=dim_w)
                        loss = loss + aux_weight * aux_loss_fn(aux_l[mask], y_aux[mask])

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        self._trained = True

        # Compute accuracy on main head
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

    def score_batch_with_dims(
        self,
        cvs: list[CVData],
        jobs: list[JobData],
        cv_indices: list[int],
        job_indices: list[int],
        gnn_scores: list[float] | None = None,
    ) -> tuple[np.ndarray, list[dict[str, str]]]:
        """Score pairs and return (overall_scores, dim_levels).

        dim_levels: list of dicts with keys skill_fit/experience_fit/seniority_fit/domain_fit
                    each value is a numeric fit score in [0, 1] (ordinal expectation
                    of the 3-class aux head: softmax · [0,1,2] / 2).
        """
        if not self._trained or self._model is None:
            n = len(cv_indices)
            return np.full(n, 0.5), [{} for _ in range(n)]

        X = self._fe.extract_batch(cvs, jobs, cv_indices, job_indices, gnn_scores=gnn_scores)
        if len(X) == 0:
            return np.array([]), []

        X_t = torch.from_numpy(X.astype(np.float32))
        self._model.eval()
        with torch.no_grad():
            main_logits, aux_logits = self._model.forward_all(X_t)
            if self._ordinal:
                probs = torch.softmax(main_logits, dim=-1)
                weights = torch.tensor([0.0, 1.0, 2.0])
                scores = (probs * weights).sum(dim=-1) / 2.0
            else:
                scores = torch.sigmoid(main_logits)

            # Per-dimension numeric fit in [0,1] — ordinal expectation of each
            # 3-class aux head (softmax · [0,1,2] / 2), same scheme as the overall
            # ordinal score. Smooth number instead of a good/ok/weak bucket.
            dim_w = torch.tensor([0.0, 1.0, 2.0])
            aux_scores = [(torch.softmax(logits, dim=-1) * dim_w).sum(dim=-1) / 2.0 for logits in aux_logits]
            dim_levels: list[dict[str, float]] = []
            for i in range(len(cv_indices)):
                dim_levels.append({
                    dim: round(float(aux_scores[d][i]), 3)
                    for d, dim in enumerate(_DIM_NAMES)
                })

        return scores.numpy(), dim_levels

    def feature_importance(self) -> dict[str, float]:
        """Approximate feature importance from first layer weights."""
        if not self._trained or self._model is None:
            return {}
        first_layer = self._model.trunk[0]
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
        # 023/3.6 (A14): stamp the hybrid weights present at TRAIN time — the
        # stage1_score feature was computed with them. If serving weights ever
        # differ, the reranker sees a distribution it never learned; the engine
        # warns loudly on load.
        trained_with = None
        meta_path = path / "metadata.json"
        if meta_path.exists():
            try:
                trained_with = json.loads(meta_path.read_text()).get("hybrid_weights")
            except Exception:  # noqa: BLE001
                pass
        with open(path / "reranker_meta.json", "w") as f:
            json.dump({
                "trained": self._trained,
                "input_dim": len(FeatureExtractor.FEATURE_NAMES),
                "ordinal": self._ordinal,
                "num_classes": 3 if self._ordinal else 1,
                "trained_with_weights": trained_with,
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
            try:
                self._model.load_state_dict(torch.load(model_path, weights_only=True))
                self._model.eval()
                self._trained = True
                logger.info("Reranker loaded from %s (ordinal=%s)", path, self._ordinal)
            except RuntimeError as e:
                # Architecture changed (e.g. old net.* keys vs new trunk/heads) — start fresh
                logger.warning("Reranker checkpoint incompatible, will retrain: %s", e)
                self._model = None
                self._trained = False
        else:
            logger.warning("No reranker model found at %s", path)
