"""JobFlow loader for ml_benchmark sandbox (Phase 4b — own data benchmark).

Loads the curated JobFlow labeled dataset (cv-job pairs with overall=0/1 labels)
and converts to the same (HeteroData + train/val/test pairs) format as the
MovieLens and CareerBuilder loaders. This makes it possible to train both
HeteroGraphSAGE and LightGCN on JobFlow with the same Phase 2/3/4 pipeline,
giving an apples-to-apples comparison.

Default config: bipartite (cv ↔ applied ↔ job). Hetero variant with the full
schema (cv + job + skill + seniority) is the responsibility of the original
production training code in run_train_save.py, not this loader.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import HeteroData

logger = logging.getLogger(__name__)


@dataclass
class JobflowSplit:
    train_pairs: list[tuple[int, int]]    # (cv_idx, job_idx) — dense reindexed
    val_pairs: list[tuple[int, int]]
    test_pairs: list[tuple[int, int]]
    num_users: int                         # number of CVs after filter
    num_jobs: int                          # number of jobs after filter


@dataclass
class JobflowDataset:
    data: HeteroData
    split: JobflowSplit
    cv_idx_to_dense: dict[int, int]
    job_idx_to_dense: dict[int, int]


def _load_labels_positives(data_dir: Path) -> list[tuple[int, int]]:
    """Read labels.json, return positive (cv_idx, job_idx) pairs only."""
    with open(data_dir / "labels.json", encoding="utf-8") as f:
        labels = json.load(f)
    positives = [(int(l["cv_idx"]), int(l["job_idx"])) for l in labels if l.get("label") == 1]
    logger.info("  total labels=%d  positives=%d  negatives=%d",
                len(labels), len(positives), len(labels) - len(positives))
    return positives


def _leave_one_out_split(
    positives_by_cv: dict[int, list[int]],
    min_positives_per_cv: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], list[int]]:
    """JobFlow has no timestamp → use insertion order (stable).
    Returns (train, val, test, kept_cvs_in_dense_order).
    """
    kept_cvs = sorted([cv for cv, ps in positives_by_cv.items() if len(ps) >= min_positives_per_cv])
    train, val, test = [], [], []
    for cv in kept_cvs:
        items = positives_by_cv[cv]
        if len(items) < 3:
            train.extend((cv, j) for j in items)
            continue
        test.append((cv, items[-1]))
        val.append((cv, items[-2]))
        train.extend((cv, j) for j in items[:-2])
    return train, val, test, kept_cvs


def load_jobflow(
    data_dir: Path | str = "data/processed/b89",
    *,
    min_positives_per_cv: int = 3,
    hidden_channels: int = 64,
    seed: int = 42,
) -> JobflowDataset:
    """Bipartite JobFlow loader compatible with Trainer.train_generic.

    Filters labels.json for positives, drops CVs with < min_positives_per_cv,
    does leave-one-out split per CV (insertion order as a stand-in for timestamp).
    """
    data_dir = Path(data_dir)
    if not (data_dir / "labels.json").exists():
        raise RuntimeError(f"labels.json not found in {data_dir}")

    logger.info("Loading JobFlow positives from %s ...", data_dir)
    positives = _load_labels_positives(data_dir)

    # Group by cv, dedupe (a (cv, job) pair can appear multiple times in labels.json)
    seen_pairs: set[tuple[int, int]] = set()
    positives_by_cv: dict[int, list[int]] = {}
    dupes = 0
    for cv, job in positives:
        key = (cv, job)
        if key in seen_pairs:
            dupes += 1
            continue
        seen_pairs.add(key)
        positives_by_cv.setdefault(cv, []).append(job)
    logger.info("  CVs with at least one positive: %d (dropped %d duplicate (cv, job) pairs)",
                len(positives_by_cv), dupes)

    # Split
    train, val, test, kept_cv_ids = _leave_one_out_split(positives_by_cv, min_positives_per_cv)
    logger.info("  after filter (min_positives_per_cv=%d): %d CVs", min_positives_per_cv, len(kept_cv_ids))
    logger.info("  train=%d val=%d test=%d", len(train), len(val), len(test))

    # Build dense indices (CV)
    cv_idx_to_dense = {cv: i for i, cv in enumerate(kept_cv_ids)}
    # Build dense indices (Job) — only jobs that appear in any kept pair
    kept_jobs = sorted({j for u, j in (train + val + test)})
    job_idx_to_dense = {j: i for i, j in enumerate(kept_jobs)}
    num_users = len(kept_cv_ids)
    num_jobs = len(kept_jobs)
    logger.info("  final: %d users × %d jobs", num_users, num_jobs)

    # Re-index all pairs into dense space
    train = [(cv_idx_to_dense[u], job_idx_to_dense[j]) for u, j in train]
    val = [(cv_idx_to_dense[u], job_idx_to_dense[j]) for u, j in val]
    test = [(cv_idx_to_dense[u], job_idx_to_dense[j]) for u, j in test]

    # Build HeteroData (bipartite): use node types "user" and "job" to match
    # Trainer.train_generic / LightGCN training conventions used in Phase 2/3/4.
    data = HeteroData()
    user_x = torch.empty(num_users, hidden_channels)
    job_x = torch.empty(num_jobs, hidden_channels)
    nn.init.xavier_uniform_(user_x)
    nn.init.xavier_uniform_(job_x)
    data["user"].x = user_x
    data["job"].x = job_x
    data["user"].num_nodes = num_users
    data["job"].num_nodes = num_jobs

    if not train:
        raise RuntimeError("Empty train set after split (try lower min_positives_per_cv)")
    train_arr = np.asarray(train, dtype=np.int64).T
    data["user", "applied", "job"].edge_index = torch.from_numpy(train_arr).long()

    # Defensive invariants
    train_set = set(train)
    assert not any(p in train_set for p in val), "val leaks into train"
    assert not any(p in train_set for p in test), "test leaks into train"
    assert data["user", "applied", "job"].edge_index.shape[1] == len(train)

    split = JobflowSplit(
        train_pairs=train,
        val_pairs=val,
        test_pairs=test,
        num_users=num_users,
        num_jobs=num_jobs,
    )
    return JobflowDataset(
        data=data,
        split=split,
        cv_idx_to_dense=cv_idx_to_dense,
        job_idx_to_dense=job_idx_to_dense,
    )
