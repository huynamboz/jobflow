"""Smoke test for CareerBuilder12 pipeline in the ml_benchmark sandbox.

Quick sanity check (~5-10 min on CPU/GPU):
    - Loads CB12 (downloads if missing via Kaggle CLI)
    - Subsamples to 5000 users + k-core=5 for speed
    - Trains 5 epochs with HeteroGraphSAGE (Trainer.train_generic reuse)
    - Prints metrics (NDCG@20, Recall@20, HR@20, MRR)
    - Exits 0 if no exception, no NaN

Usage:
    cd backend
    python scripts/smoke_test_careerbuilder.py
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import sklearn.metrics.pairwise  # pre-warm BEFORE django.setup to avoid deadlock  # noqa: F401
import torch_geometric  # pre-load BEFORE django.setup to avoid PyG 2.7.0 circular import bug  # noqa: F401

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np

from ml_benchmark.data.careerbuilder_loader import load_careerbuilder_12
from ml_benchmark.training.trainer import TrainConfig, Trainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("smoke_test_careerbuilder")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_BACKEND_DIR.parent / "Dataset" / "careerbuilder-12",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--k-core", type=int, default=5)
    parser.add_argument("--subsample-users", type=int, default=5000,
                        help="Subsample N users for smoke speed")
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=_BACKEND_DIR / "checkpoints_benchmark",
    )
    args = parser.parse_args()

    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    logger.info(
        "Loading CareerBuilder12 (cache=%s, k=%d, subsample=%d) ...",
        args.cache_dir, args.k_core, args.subsample_users,
    )
    dataset = load_careerbuilder_12(
        cache_dir=args.cache_dir,
        subsample_users=args.subsample_users,
        subsample_seed=args.seed,
        k_core=args.k_core,
        hidden_channels=args.hidden,
        include_hetero=False,
        seed=args.seed,
    )
    sp = dataset.split
    logger.info(
        "Dataset ready: %d users, %d jobs, train=%d val=%d test=%d",
        sp.num_users, sp.num_jobs,
        len(sp.train_pairs), len(sp.val_pairs), len(sp.test_pairs),
    )

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
        train_pairs=sp.train_pairs,
        val_pairs=sp.val_pairs,
        test_pairs=sp.test_pairs,
        src_type="user",
        dst_type="job",
        num_src=sp.num_users,
        num_dst=sp.num_jobs,
        eval_at_k=(20,),
    )

    elapsed = time.time() - t_start
    test_metrics = result.test_metrics or {}
    has_nan = any(
        v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
        for v in test_metrics.values()
    )

    print("\n" + "=" * 60)
    print("✓ Smoke test CareerBuilder completed")
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
