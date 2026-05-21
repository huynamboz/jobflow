"""LightGCN baseline training (feature 010).

Trains PyG's LightGCN on a chosen dataset (MovieLens-1M or CareerBuilder12)
with the same per-user full-ranking evaluation used by Phase 2/3, so the
metric is directly comparable with HeteroGraphSAGE.

Usage:
    cd backend
    python scripts/train_lightgcn.py --dataset movielens --seed 42 --output results/lightgcn/movielens_seed42.json
    python scripts/train_lightgcn.py --dataset careerbuilder --seed 42 --output results/lightgcn/careerbuilder_seed42.json
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
import platform
import random
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import sklearn.metrics.pairwise  # noqa: F401
import torch_geometric  # noqa: F401

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np
import torch

from ml_benchmark.baselines.lightgcn import LightGCNScorer
from ml_benchmark.evaluation.metrics import hit_rate_at_k, mrr, ndcg_at_k, recall_at_k

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("train_lightgcn")


def _get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_dataset(dataset: str, args):
    """Returns (num_users, num_items, train_pairs, val_pairs, test_pairs, ds_label, preprocess_meta)."""
    if dataset == "movielens":
        from ml_benchmark.data.movielens_loader import load_movielens_1m
        ds = load_movielens_1m(
            cache_dir=_BACKEND_DIR.parent / "Dataset" / "movielens-1m",
            rating_threshold=4,
            k_core=args.k_core if args.k_core is not None else 10,
            hidden_channels=args.hidden,
            include_genres=False,
            subsample_users=args.subsample_users if args.subsample_users != 0 else None,
            seed=args.seed,
        )
        return (
            ds.split.num_users, ds.split.num_movies,
            ds.split.train_pairs, ds.split.val_pairs, ds.split.test_pairs,
            "MovieLens-1M",
            {
                "rating_threshold": 4,
                "k_core": args.k_core if args.k_core is not None else 10,
                "split": "leave-one-out per user (timestamp)",
            },
        )
    elif dataset == "careerbuilder":
        from ml_benchmark.data.careerbuilder_loader import load_careerbuilder_12
        ds = load_careerbuilder_12(
            cache_dir=_BACKEND_DIR.parent / "Dataset" / "careerbuilder-12",
            subsample_users=args.subsample_users if args.subsample_users != 0 else 50_000,
            subsample_seed=args.seed,
            k_core=args.k_core if args.k_core is not None else 10,
            hidden_channels=args.hidden,
            include_hetero=False,
            seed=args.seed,
        )
        return (
            ds.split.num_users, ds.split.num_jobs,
            ds.split.train_pairs, ds.split.val_pairs, ds.split.test_pairs,
            "CareerBuilder12",
            {
                "subsample_users": args.subsample_users if args.subsample_users != 0 else 50_000,
                "subsample_seed": args.seed,
                "k_core": args.k_core if args.k_core is not None else 10,
                "split": "leave-one-out per user (timestamp)",
            },
        )
    else:
        raise ValueError(f"Unknown dataset: {dataset!r}")


def evaluate_lightgcn(
    scorer: LightGCNScorer,
    edge_index: torch.Tensor,
    eval_pairs: list[tuple[int, int]],
    train_pos_by_src: dict[int, set[int]],
    num_users: int,
    num_items: int,
    eval_at_k: tuple[int, ...],
    device: torch.device,
    chunk_size: int = 1024,
) -> dict[str, float]:
    """Per-user full ranking eval using dot product, mirrors trainer._evaluate_full_ranking."""
    if not eval_pairs:
        return {}

    eval_by_src: dict[int, list[int]] = {}
    for s, d in eval_pairs:
        eval_by_src.setdefault(s, []).append(d)

    eval_users = sorted(eval_by_src.keys())
    n_eval = len(eval_users)
    if n_eval == 0:
        return {}

    with torch.no_grad():
        z_user, z_item = scorer.get_user_item_embeddings(edge_index)

    max_k = max(eval_at_k)
    accum: dict[str, float] = {f"recall@{k}": 0.0 for k in eval_at_k}
    accum.update({f"ndcg@{k}": 0.0 for k in eval_at_k})
    accum.update({f"hr@{k}": 0.0 for k in eval_at_k})
    accum["mrr"] = 0.0

    for start in range(0, n_eval, chunk_size):
        end = min(start + chunk_size, n_eval)
        chunk = end - start
        chunk_users = eval_users[start:end]
        u_idx = torch.tensor(chunk_users, dtype=torch.long, device=device)
        scores = z_user[u_idx] @ z_item.T  # [chunk, num_items]  ← dot product chuẩn LightGCN

        # Mask train-seen + eval positives
        train_mask = torch.zeros(chunk, num_items, dtype=torch.bool, device=device)
        eval_pos = torch.zeros(chunk, num_items, dtype=torch.bool, device=device)
        for i, u in enumerate(chunk_users):
            seen = train_pos_by_src.get(u, set())
            if seen:
                train_mask[i, list(seen)] = True
            eval_pos[i, eval_by_src[u]] = True

        scores = scores.masked_fill(train_mask, float("-inf"))

        # Sort + compute metrics on GPU
        sorted_idx = scores.argsort(dim=-1, descending=True)
        is_pos_full = eval_pos.gather(1, sorted_idx)
        is_pos_topk = is_pos_full[:, :max_k].float()
        n_pos_per_user = eval_pos.sum(dim=-1).clamp(min=1).float()

        # NDCG discounts
        log2_idx = torch.log2(torch.arange(2, max_k + 2, dtype=torch.float32, device=device))
        discount_topk = 1.0 / log2_idx[:max_k]

        for k in eval_at_k:
            hits_at_k = is_pos_topk[:, :k]
            recall_per_user = hits_at_k.sum(dim=-1) / n_pos_per_user
            accum[f"recall@{k}"] += recall_per_user.sum().item()

            dcg = (hits_at_k * discount_topk[:k]).sum(dim=-1)
            n_ideal_per_user = eval_pos.sum(dim=-1).clamp(max=k)
            positions = torch.arange(k, device=device).unsqueeze(0)
            ideal_mask = positions < n_ideal_per_user.unsqueeze(1)
            idcg = (ideal_mask.float() * discount_topk[:k]).sum(dim=-1).clamp(min=1e-10)
            accum[f"ndcg@{k}"] += (dcg / idcg).sum().item()

            hr_per_user = (hits_at_k.sum(dim=-1) > 0).float()
            accum[f"hr@{k}"] += hr_per_user.sum().item()

        first_pos = is_pos_full.float().argmax(dim=-1)
        has_any = is_pos_full.any(dim=-1).float()
        accum["mrr"] += (has_any / (first_pos.float() + 1.0)).sum().item()

    for key in accum:
        accum[key] /= n_eval
    return accum


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=["movielens", "careerbuilder"], required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-epochs", type=int, default=500)
    p.add_argument("--patience", type=int, default=50)
    p.add_argument("--hidden", type=int, default=64)
    p.add_argument("--num-layers", type=int, default=3)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=0.0,
                   help="Adam weight_decay; paper relies on lambda_reg instead, defaults to 0")
    p.add_argument("--lambda-reg", type=float, default=1e-4,
                   help="L2 reg inside recommendation_loss (paper §3.3)")
    p.add_argument("--subsample-users", type=int, default=0,
                   help="Override default subsample (0 = use loader default)")
    p.add_argument("--k-core", type=int, default=None,
                   help="Override default k-core (None = use loader default)")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    # Reproducibility
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    device = _get_device()
    logger.info("Device: %s", device)

    t_start = time.time()
    logger.info("Loading %s dataset ...", args.dataset)
    num_users, num_items, train_pairs, val_pairs, test_pairs, ds_label, preprocess_meta = load_dataset(args.dataset, args)
    logger.info("Loaded: %d users, %d items, train=%d val=%d test=%d",
                num_users, num_items, len(train_pairs), len(val_pairs), len(test_pairs))

    # Build per-user train-seen set for eval mask
    train_pos_by_src: dict[int, set[int]] = {}
    for u, i in train_pairs:
        train_pos_by_src.setdefault(u, set()).add(i)

    # Build LightGCN model
    scorer = LightGCNScorer(
        num_users=num_users, num_items=num_items,
        embedding_dim=args.hidden, num_layers=args.num_layers,
    ).to(device)
    optimizer = torch.optim.Adam(scorer.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # Build shifted bipartite edge_index (train edges only)
    train_arr = np.asarray(train_pairs, dtype=np.int64)
    src_t = torch.from_numpy(train_arr[:, 0]).long().to(device)
    pos_t = scorer.shift_items(torch.from_numpy(train_arr[:, 1]).long().to(device))
    edge_index = torch.stack([src_t, pos_t])  # [2, num_train]
    n_train = len(train_pairs)

    best_val = -float("inf")
    best_state = None
    best_epoch = 0
    patience_counter = 0
    train_losses = []

    for epoch in range(args.max_epochs):
        scorer.train()
        # BPR: 1 random negative item per positive (shifted into item space)
        neg_t = torch.randint(num_users, num_users + num_items, (n_train,), device=device)

        pos_rank = scorer.score_edges(edge_index, src_t, pos_t)
        neg_rank = scorer.score_edges(edge_index, src_t, neg_t)
        node_id = torch.cat([src_t, pos_t, neg_t])
        loss = scorer.recommendation_loss(pos_rank, neg_rank, node_id=node_id, lambda_reg=args.lambda_reg)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        train_losses.append(loss.item())

        # Eval
        scorer.eval()
        val_metrics = evaluate_lightgcn(
            scorer, edge_index, val_pairs, train_pos_by_src,
            num_users, num_items, eval_at_k=(20,), device=device,
        )
        val_signal = val_metrics.get("ndcg@20", 0.0)
        logger.info(
            "Epoch %d — loss=%.4f val_ndcg@20=%.4f val_recall@20=%.4f val_hr@20=%.4f",
            epoch, loss.item(), val_signal,
            val_metrics.get("recall@20", 0.0), val_metrics.get("hr@20", 0.0),
        )

        if val_signal > best_val:
            best_val = val_signal
            best_state = copy.deepcopy(scorer.state_dict())
            best_epoch = epoch
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info("Early stopping at epoch %d (patience=%d)", epoch, args.patience)
                break

    if best_state is not None:
        scorer.load_state_dict(best_state)
    scorer.eval()
    test_metrics = evaluate_lightgcn(
        scorer, edge_index, test_pairs, train_pos_by_src,
        num_users, num_items, eval_at_k=(20,), device=device,
    )

    elapsed = time.time() - t_start
    has_nan = any(
        v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
        for v in test_metrics.values()
    )
    if has_nan:
        logger.error("NaN in test metrics: %s", test_metrics)
        return 1

    output = {
        "feature": "010-lightgcn-baseline",
        "dataset": ds_label,
        "variant": "bipartite",
        "preprocessing": preprocess_meta,
        "model": "LightGCN",
        "config": {
            "embedding_dim": args.hidden,
            "num_layers": args.num_layers,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "lambda_reg": args.lambda_reg,
            "max_epochs": args.max_epochs,
            "early_stopping_patience": args.patience,
            "seed": args.seed,
        },
        "stats": {
            "num_users": num_users,
            "num_items": num_items,
            "num_train_pairs": len(train_pairs),
            "num_val_pairs": len(val_pairs),
            "num_test_pairs": len(test_pairs),
        },
        "training": {
            "best_epoch": best_epoch,
            "epochs_run": len(train_losses),
            "final_train_loss": float(train_losses[-1]) if train_losses else None,
            "wall_time_seconds": round(elapsed, 2),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        },
        "test_metrics": {k: float(v) for k, v in test_metrics.items()},
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
            "numpy": np.__version__,
        },
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Result written to %s", args.output)

    print("\n" + "=" * 60)
    print(f"✓ LightGCN training completed ({args.output.name})")
    print(f"  Dataset:      {ds_label}")
    print(f"  Wall time:    {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Best epoch:   {best_epoch}/{len(train_losses)}")
    print(f"  Test NDCG@20: {test_metrics.get('ndcg@20', 0.0):.4f}")
    print(f"  Test Recall@20: {test_metrics.get('recall@20', 0.0):.4f}")
    print(f"  Test HR@20:   {test_metrics.get('hr@20', 0.0):.4f}")
    print(f"  Test MRR:     {test_metrics.get('mrr', 0.0):.4f}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
