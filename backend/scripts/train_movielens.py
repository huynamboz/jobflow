"""Full MovieLens-1M training for ml_benchmark sandbox (feature 008).

Trains HeteroGraphSAGE on bipartite MovieLens (or hetero with --hetero), writes
metrics to a JSON file in the standardized result schema (see data-model.md §E8).

Usage:
    cd backend
    python scripts/train_movielens.py --seed 42 --output results/movielens/seed42.json
    python scripts/train_movielens.py --hetero --seed 42 --output results/movielens/seed42_hetero.json

Output file is intended to be committed as evidence for the thesis benchmark table.
"""

from __future__ import annotations

import argparse
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

import sklearn.metrics.pairwise  # pre-warm BEFORE django.setup to avoid deadlock with sentence_transformers  # noqa: F401
import torch_geometric  # pre-load BEFORE django.setup to avoid PyG 2.7.0 circular import bug  # noqa: F401

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np
import torch

from ml_benchmark.data.movielens_loader import load_movielens_1m
from ml_benchmark.training.trainer import TrainConfig, Trainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("train_movielens")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_BACKEND_DIR.parent / "Dataset" / "movielens-1m",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-epochs", type=int, default=500)
    parser.add_argument("--patience", type=int, default=50)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--k-core", type=int, default=10)
    parser.add_argument("--hetero", action="store_true", help="Use hetero variant with genre node")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to write the result JSON (vd: results/movielens/seed42.json)",
    )
    args = parser.parse_args()

    # ---------- Fix all sources of randomness ----------
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    logger.info("Loading MovieLens-1M (k_core=%d, hetero=%s, seed=%d) ...",
                args.k_core, args.hetero, args.seed)
    dataset = load_movielens_1m(
        cache_dir=args.cache_dir,
        rating_threshold=4,
        k_core=args.k_core,
        hidden_channels=args.hidden,
        include_genres=args.hetero,
        subsample_users=None,
        seed=args.seed,
    )
    sp = dataset.split

    config = TrainConfig(
        model_type="graphsage",
        hidden_channels=args.hidden,
        num_layers=args.num_layers,
        lr=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.max_epochs,
        patience=args.patience,
        seed=args.seed,
    )
    trainer = Trainer(config)
    result = trainer.train_generic(
        data=dataset.data,
        train_pairs=sp.train_pairs,
        val_pairs=sp.val_pairs,
        test_pairs=sp.test_pairs,
        src_type="user",
        dst_type="movie",
        num_src=sp.num_users,
        num_dst=sp.num_movies,
        eval_at_k=(20,),
    )

    elapsed = time.time() - t_start
    test_metrics = result.test_metrics or {}

    # NaN safety check
    has_nan = any(
        v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
        for v in test_metrics.values()
    )
    if has_nan:
        logger.error("NaN in test metrics: %s", test_metrics)
        return 1

    output = {
        "feature": "008-movielens-benchmark",
        "dataset": "MovieLens-1M",
        "variant": "hetero" if args.hetero else "bipartite",
        "preprocessing": {
            "rating_threshold": 4,
            "k_core": args.k_core,
            "split": "leave-one-out per user (timestamp)",
        },
        "model": "HeteroGraphSAGE",
        "config": {
            "hidden_channels": args.hidden,
            "num_layers": args.num_layers,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "max_epochs": args.max_epochs,
            "early_stopping_patience": args.patience,
            "seed": args.seed,
        },
        "stats": {
            "num_users": sp.num_users,
            "num_movies": sp.num_movies,
            "num_genres": sp.num_genres,
            "num_train_pairs": len(sp.train_pairs),
            "num_val_pairs": len(sp.val_pairs),
            "num_test_pairs": len(sp.test_pairs),
        },
        "training": {
            "best_epoch": result.best_epoch,
            "epochs_run": len(result.train_losses),
            "final_train_loss": float(result.train_losses[-1]) if result.train_losses else None,
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
    print(f"✓ Full training completed ({args.output.name})")
    print(f"  Wall time:    {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Best epoch:   {result.best_epoch}/{len(result.train_losses)}")
    print(f"  Test NDCG@20: {test_metrics.get('ndcg@20', 0.0):.4f}")
    print(f"  Test Recall@20: {test_metrics.get('recall@20', 0.0):.4f}")
    print(f"  Test HR@20:   {test_metrics.get('hr@20', 0.0):.4f}")
    print(f"  Test MRR:     {test_metrics.get('mrr', 0.0):.4f}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
