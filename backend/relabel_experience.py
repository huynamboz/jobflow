"""
Programmatic relabeling for experience mismatch pairs.

Labelers were lenient — marking 'suitable' even when CV experience is significantly
below job requirement. This creates noisy training signal for experience_fit.

Rules (applied once, before training — NOT at inference):
  - experience_fit = 0   if cv_exp < job_exp_min * EXP_FIT_THRESHOLD
  - overall      = 0   if cv_exp < job_exp_min * OVERALL_THRESHOLD

Usage:
    python relabel_experience.py --data data/processed/b89
    python relabel_experience.py --data data/processed/b89 --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

EXP_FIT_THRESHOLD = 0.70   # cv_exp < 70% of job_exp_min → experience_fit = 0
OVERALL_THRESHOLD = 0.65   # cv_exp < 65% of job_exp_min → overall = 0 (not fit)


def main(data_dir: Path, dry_run: bool = False) -> None:
    labels_path = data_dir / "labels.json"
    cvs_path    = data_dir / "cvs.json"
    jobs_path   = data_dir / "jobs.json"

    with open(labels_path, encoding="utf-8") as f:
        labels = json.load(f)
    with open(cvs_path, encoding="utf-8") as f:
        cvs = json.load(f)
    with open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    cv_map  = {c["idx"]: c for c in cvs}
    job_map = {j["idx"]: j for j in jobs}

    exp_fit_fixed = 0
    overall_fixed = 0

    for lbl in labels:
        cv  = cv_map.get(lbl["cv_idx"])
        job = job_map.get(lbl["job_idx"])
        if not cv or not job:
            continue

        cv_exp  = float(cv.get("experience_years") or 0)
        job_exp = float(job.get("experience_min")  or 0)

        if job_exp <= 0:
            continue

        ratio = cv_exp / job_exp

        if ratio < EXP_FIT_THRESHOLD and lbl.get("experience_fit", -1) > 0:
            if not dry_run:
                lbl["experience_fit"] = 0
            exp_fit_fixed += 1

        if ratio < OVERALL_THRESHOLD and lbl.get("overall", lbl.get("label", 0)) >= 1:
            if not dry_run:
                lbl["overall"] = 0
                lbl["label"]   = 0
            overall_fixed += 1

    print(f"experience_fit relabeled → 0 : {exp_fit_fixed}")
    print(f"overall relabeled → 0        : {overall_fixed}")

    if dry_run:
        print("Dry run — no files written.")
        return

    backup = labels_path.with_suffix(".json.bak")
    shutil.copy2(labels_path, backup)
    print(f"Backup: {backup}")

    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved: {labels_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",    default="data/processed/b89", help="Dataset dir with labels.json")
    parser.add_argument("--dry-run", action="store_true",           help="Show stats without modifying files")
    args = parser.parse_args()
    main(Path(args.data), dry_run=args.dry_run)
