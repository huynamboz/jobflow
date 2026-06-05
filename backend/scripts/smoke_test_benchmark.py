"""
Smoke test for the ml_benchmark sandbox.

Loads a small JobFlow dataset, runs a short training, prints final metrics.
Imports exclusively from ml_benchmark.* — proves the sandbox is self-contained
and the duplicate succeeded.

Default dataset: data/processed/b89 (smallest stable JobFlow export available
at smoke-test design time — confirm with `ls backend/data/processed/`).

Does NOT save a checkpoint — checkpoint persistence lives in the stripped
inference/ module. Smoke test only validates training + evaluation loop.

Usage (from repo root):
    cd backend
    python scripts/smoke_test_benchmark.py
    python scripts/smoke_test_benchmark.py --epochs 5 --dataset data/processed/b89
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Script lives in backend/scripts/; ensure backend/ is on sys.path so
# `import config` (Django settings) and `import ml_benchmark` resolve.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import sklearn.metrics.pairwise  # pre-warm to avoid sentence_transformers deadlock  # noqa: F401

from ml_benchmark.embedding import get_provider
from ml_benchmark.graph.builder import GraphBuilder
from ml_benchmark.graph.schema import (
    CVData,
    DatasetSplit,
    EducationLevel,
    JobData,
    LabeledPair,
    SeniorityLevel,
    SkillCategory,
)
from ml_benchmark.training.trainer import TrainConfig, Trainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("smoke_test_benchmark")


def load_dataset(data_dir: Path):
    def jload(name):
        with open(data_dir / name, encoding="utf-8") as f:
            return json.load(f)

    raw_cvs = jload("cvs.json")
    raw_jobs = jload("jobs.json")
    raw_labels = jload("labels.json")
    raw_skills = jload("skills.json")

    skill_catalog = {s["name"]: SkillCategory(s["category"]) for s in raw_skills}
    job_idx_to_db_id = {j["idx"]: j["job_id"] for j in raw_jobs}
    cv_idx_to_db_id = {c["idx"]: c["cv_id"] for c in raw_cvs}

    cvs = [
        CVData(
            cv_id=c["cv_id"],
            seniority=SeniorityLevel(c["seniority"]),
            experience_years=float(c["experience_years"]),
            education=EducationLevel(c["education"]),
            skills=tuple(c["skills"]),
            skill_proficiencies=tuple(c["skill_proficiencies"]),
            text=c["text"] or "",
        )
        for c in raw_cvs
    ]
    jobs = [
        JobData(
            job_id=j["job_id"],
            seniority=SeniorityLevel(j["seniority"]),
            skills=tuple(j["skills"]),
            skill_importances=tuple(j["skill_importances"]),
            salary_min=int(j["salary_min"] or 0),
            salary_max=int(j["salary_max"] or 0),
            experience_min=float(j.get("experience_min") or 0),
            experience_max=float(j["experience_max"]) if j.get("experience_max") else None,
            role_category=j.get("role_category") or "",
            text=j["text"] or "",
        )
        for j in raw_jobs
    ]

    split_map: dict[str, list[LabeledPair]] = {}
    for lbl in raw_labels:
        split = lbl.get("split", "train")
        split_map.setdefault(split, []).append(
            LabeledPair(
                cv_id=cv_idx_to_db_id[lbl["cv_idx"]],
                job_id=job_idx_to_db_id[lbl["job_idx"]],
                label=lbl["label"],
                split=split,
            )
        )
    dataset = DatasetSplit(
        train=split_map.get("train", []),
        val=split_map.get("val", []),
        test=split_map.get("test", []),
    )
    return cvs, jobs, dataset, skill_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/processed/b89"),
        help="Path to JobFlow dataset dir containing cvs.json, jobs.json, labels.json, skills.json",
    )
    parser.add_argument("--epochs", type=int, default=5, help="Training epochs for smoke test")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=Path("checkpoints_benchmark"),
        help="Sandbox checkpoint dir (NOT production checkpoints/). Created if missing.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.dataset.is_dir():
        logger.error("Dataset dir not found: %s", args.dataset)
        return 1

    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Sandbox checkpoint dir: %s (no checkpoint will be saved by smoke test)", args.checkpoint_dir)

    t_start = time.time()

    logger.info("Loading dataset from %s ...", args.dataset)
    cvs, jobs, dataset, skill_catalog = load_dataset(args.dataset)
    logger.info(
        "Loaded %d CVs, %d Jobs, %d/%d/%d train/val/test pairs",
        len(cvs), len(jobs),
        len(dataset.train), len(dataset.val), len(dataset.test),
    )

    logger.info("Building graph ...")
    provider = get_provider()
    builder = GraphBuilder(provider)
    data = builder.build(cvs, jobs, skill_catalog, dataset.train + dataset.val + dataset.test)
    logger.info(
        "Graph: %d CVs, %d Jobs, %d Skills",
        data["cv"].x.shape[0], data["job"].x.shape[0], data["skill"].x.shape[0],
    )

    logger.info("Training %d epochs ...", args.epochs)
    config = TrainConfig(
        model_type="graphsage",
        hidden_channels=128,
        num_layers=2,
        lr=1e-3,
        weight_decay=1e-5,
        epochs=args.epochs,
        patience=args.epochs,  # disable early stop for smoke test
        seed=args.seed,
    )
    trainer = Trainer(config)
    result = trainer.train(data, dataset, cvs, jobs)

    elapsed = time.time() - t_start
    print("\n" + "=" * 60)
    print("✓ Smoke test completed")
    print(f"  Wall time: {elapsed:.1f}s")
    print(f"  Best epoch: {result.best_epoch}")
    print(f"  Final train loss: {result.train_losses[-1]:.4f}")
    if result.test_metrics:
        metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in result.test_metrics.items())
        print(f"  Test metrics: {metrics_str}")
    else:
        print("  No test metrics (test split empty)")
    print(f"  Checkpoint dir: {args.checkpoint_dir} (not written by smoke test)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
