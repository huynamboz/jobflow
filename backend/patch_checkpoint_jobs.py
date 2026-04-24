"""
Patch checkpoint jobs.json with experience_min/max/role_category from dataset jobs.json.
Run this instead of full GNN retrain when only reranker features need updating.

Usage:
    cd backend
    python patch_checkpoint_jobs.py
    python patch_checkpoint_jobs.py --dataset data/processed/b89 --checkpoint checkpoints/latest
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main(dataset_dir: Path, checkpoint_dir: Path) -> None:
    dataset_jobs_path = dataset_dir / "jobs.json"
    checkpoint_jobs_path = checkpoint_dir / "jobs.json"

    with open(dataset_jobs_path, encoding="utf-8") as f:
        dataset_jobs = json.load(f)

    with open(checkpoint_jobs_path, encoding="utf-8") as f:
        ckpt_jobs = json.load(f)

    # Build lookup: job_id → {experience_min, experience_max, role_category}
    dataset_map: dict[int, dict] = {
        j["job_id"]: {
            "experience_min": float(j.get("experience_min") or 0),
            "experience_max": float(j["experience_max"]) if j.get("experience_max") else None,
            "role_category":  j.get("role_category") or "",
        }
        for j in dataset_jobs
    }

    # Backup
    backup_path = checkpoint_jobs_path.with_suffix(".json.bak")
    shutil.copy2(checkpoint_jobs_path, backup_path)
    print(f"Backup saved to {backup_path}")

    patched = 0
    for job in ckpt_jobs:
        jid = job["job_id"]
        if jid in dataset_map:
            d = dataset_map[jid]
            job["experience_min"]  = d["experience_min"]
            job["experience_max"]  = d["experience_max"]
            job["role_category"]   = d["role_category"]
            if d["experience_min"] > 0 or d["role_category"]:
                patched += 1

    with open(checkpoint_jobs_path, "w", encoding="utf-8") as f:
        json.dump(ckpt_jobs, f, ensure_ascii=False, separators=(",", ":"))

    total = len(ckpt_jobs)
    matched = sum(1 for j in ckpt_jobs if j["job_id"] in dataset_map)
    has_exp = sum(1 for j in ckpt_jobs if j.get("experience_min", 0) > 0)
    has_role = sum(1 for j in ckpt_jobs if j.get("role_category", "") not in ("", "other"))
    print(f"Total checkpoint jobs : {total}")
    print(f"Matched in dataset    : {matched}")
    print(f"Has experience_min > 0: {has_exp} ({has_exp*100//max(total,1)}%)")
    print(f"Has role_category     : {has_role} ({has_role*100//max(total,1)}%)")
    print(f"Done. Retrain reranker to apply changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",    default="data/processed/b89",  help="Dataset dir with jobs.json")
    parser.add_argument("--checkpoint", default="checkpoints/latest",   help="Checkpoint dir to patch")
    args = parser.parse_args()
    main(Path(args.dataset), Path(args.checkpoint))
