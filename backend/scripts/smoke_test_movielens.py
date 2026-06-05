"""Smoke test for MovieLens-1M pipeline in the ml_benchmark sandbox.

Quick sanity check (~5–10 min on CPU, faster on GPU):
    - Loads MovieLens-1M (downloads if missing)
    - Subsamples to 1000 users + k-core=5 for speed
    - Trains 5 epochs with HeteroGraphSAGE
    - Prints metrics (NDCG@20, Recall@20, HR@20, MRR)
    - Exits 0 if no exception, no NaN

Usage:
    cd backend
    python scripts/smoke_test_movielens.py
    python scripts/smoke_test_movielens.py --epochs 5 --subsample-users 1000

Does NOT save a checkpoint. Does NOT verify metric values match LightGCN paper
— that is for full train_movielens.py with k=10 and no subsample.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import sklearn.metrics.pairwise  # pre-warm BEFORE django.setup to avoid deadlock with sentence_transformers  # noqa: F401

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import math
import numpy as np

from ml_benchmark.data.movielens_loader import load_movielens_1m
from ml_benchmark.training.trainer import TrainConfig, Trainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("smoke_test_movielens")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_BACKEND_DIR.parent / "Dataset" / "movielens-1m",
        help="Where to cache the MovieLens-1M files",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--k-core", type=int, default=5,
                        help="Lower k for smoke speed (full run uses 10)")
    parser.add_argument("--subsample-users", type=int, default=1000,
                        help="Use only N random users for smoke speed (set to 0 for all)")
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=_BACKEND_DIR / "checkpoints_benchmark",
        help="Sandbox checkpoint dir (smoke test does not save)",
    )
    args = parser.parse_args()

    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    logger.info("Loading MovieLens-1M (cache=%s, k=%d, subsample=%s) ...",
                args.cache_dir, args.k_core, args.subsample_users or "all")
    dataset = load_movielens_1m(
        cache_dir=args.cache_dir,
        rating_threshold=4,
        k_core=args.k_core,
        hidden_channels=args.hidden,
        include_genres=False,
        subsample_users=args.subsample_users if args.subsample_users > 0 else None,
        seed=args.seed,
    )
    logger.info("Dataset ready: %d users, %d movies, %d train pairs, %d val, %d test",
                dataset.split.num_users, dataset.split.num_movies,
                len(dataset.split.train_pairs), len(dataset.split.val_pairs),
                len(dataset.split.test_pairs))

    config = TrainConfig(
        model_type="graphsage",
        hidden_channels=args.hidden,
        num_layers=2,
        lr=1e-3,
        weight_decay=1e-4,
        epochs=args.epochs,
        patience=args.epochs,   # disable early stopping for smoke
        seed=args.seed,
    )
    trainer = Trainer(config)
    result = trainer.train_generic(
        data=dataset.data,
        train_pairs=dataset.split.train_pairs,
        val_pairs=dataset.split.val_pairs,
        test_pairs=dataset.split.test_pairs,
        src_type="user",
        dst_type="movie",
        num_src=dataset.split.num_users,
        num_dst=dataset.split.num_movies,
        eval_at_k=(20,),
    )

    elapsed = time.time() - t_start

    # Sanity check metrics
    test_metrics = result.test_metrics or {}
    has_nan = any(
        v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
        for v in test_metrics.values()
    )

    print("\n" + "=" * 60)
    print("✓ Smoke test MovieLens completed")
    print(f"  Wall time:   {elapsed:.1f}s")
    print(f"  Best epoch:  {result.best_epoch}")
    if result.train_losses:
        print(f"  Final loss:  {result.train_losses[-1]:.4f}")
    if test_metrics:
        line = ", ".join(f"{k}={v:.4f}" for k, v in test_metrics.items())
        print(f"  Test:        {line}")
    print(f"  NaN check:   {'FAIL' if has_nan else 'OK'}")
    print("=" * 60)
    return 1 if has_nan else 0


if __name__ == "__main__":
    sys.exit(main())
