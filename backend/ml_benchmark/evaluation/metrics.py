from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score


def recall_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Recall@K: fraction of positives ranked in the top-k positions."""
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    n_positive = int(y_true.sum())
    if n_positive == 0:
        return 0.0
    top_k_indices = np.argsort(y_scores)[::-1][:k]
    hits = int(y_true[top_k_indices].sum())
    return hits / n_positive


def mrr(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    """Mean Reciprocal Rank: 1/rank of the first relevant item."""
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    ranked_indices = np.argsort(y_scores)[::-1]
    for rank, idx in enumerate(ranked_indices, start=1):
        if y_true[idx] == 1:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Normalized Discounted Cumulative Gain at K."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_scores = np.asarray(y_scores)

    # Clamp k to actual number of items
    n = len(y_true)
    k = min(k, n)

    # DCG
    top_k_indices = np.argsort(y_scores)[::-1][:k]
    gains = y_true[top_k_indices]
    discounts = np.log2(np.arange(2, k + 2, dtype=np.float64))
    dcg = float(np.sum(gains / discounts))

    # Ideal DCG
    ideal_gains = np.sort(y_true)[::-1][:k]
    idcg = float(np.sum(ideal_gains / discounts))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def auc_roc(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    """Area Under the ROC Curve. Returns 0.0 if only one class present."""
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    if len(np.unique(y_true)) < 2:
        return 0.0
    return float(roc_auc_score(y_true, y_scores))


def precision_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Precision@K: fraction of top-k items that are positive."""
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    k = min(k, len(y_true))
    if k == 0:
        return 0.0
    top_k_indices = np.argsort(y_scores)[::-1][:k]
    hits = int(y_true[top_k_indices].sum())
    return hits / k


def hit_rate_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Hit Rate@K: 1.0 if at least one positive in top-k, else 0.0."""
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    k = min(k, len(y_true))
    if k == 0:
        return 0.0
    top_k_indices = np.argsort(y_scores)[::-1][:k]
    return 1.0 if y_true[top_k_indices].sum() > 0 else 0.0


def compute_all_metrics(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    """Compute all ranking metrics at once."""
    results: dict[str, float] = {}
    for k in ks:
        results[f"recall@{k}"] = recall_at_k(y_true, y_scores, k)
        results[f"precision@{k}"] = precision_at_k(y_true, y_scores, k)
        results[f"ndcg@{k}"] = ndcg_at_k(y_true, y_scores, k)
        results[f"hit_rate@{k}"] = hit_rate_at_k(y_true, y_scores, k)
    results["mrr"] = mrr(y_true, y_scores)
    results["auc_roc"] = auc_roc(y_true, y_scores)
    return results
