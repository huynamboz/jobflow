"""
Generate synthetic experience-mismatch negative pairs.

Pairs where cv.experience_years << job.experience_min are clearly "not fit"
due to experience — no human labeler needed, the gap is unambiguous.

These pairs have:
  overall = 0       (not fit)
  experience_fit = 0 (not fit on experience)
  skill_fit = computed from Jaccard (may still be good)
  seniority_fit / domain_fit = -1 (masked — not asserted)

Usage:
    python generate_exp_negatives.py --data data/processed/b89_full
    python generate_exp_negatives.py --data data/processed/b89_full --max-pairs 2000 --dry-run
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

EXP_GAP_THRESHOLD = 0.65   # cv_exp < 65% of job_exp_min → clear mismatch
MIN_JOB_EXP      = 3.0     # only target jobs that actually require ≥3 years
MAX_PAIRS        = 2000
SEED             = 42


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _skill_fit(jaccard: float) -> int:
    if jaccard >= 0.25:
        return 2   # good
    if jaccard >= 0.08:
        return 1   # ok
    return 0       # weak


def main(data_dir: Path, max_pairs: int, dry_run: bool) -> None:
    with open(data_dir / "cvs.json",    encoding="utf-8") as f:
        cvs = json.load(f)
    with open(data_dir / "jobs.json",   encoding="utf-8") as f:
        jobs = json.load(f)
    with open(data_dir / "labels.json", encoding="utf-8") as f:
        labels = json.load(f)

    # Existing pairs → skip duplicates
    existing = {(l["cv_idx"], l["job_idx"]) for l in labels}

    # CV skill sets (lowercase names)
    cv_skills: dict[int, set[str]] = {
        c["idx"]: set(c.get("skills", [])) for c in cvs
    }

    # Target CVs: experience_years < MIN_JOB_EXP * EXP_GAP_THRESHOLD
    target_cvs = [
        c for c in cvs
        if (c.get("experience_years") or 0) < MIN_JOB_EXP * EXP_GAP_THRESHOLD
    ]

    # Target jobs: experience_min >= MIN_JOB_EXP
    target_jobs = [
        j for j in jobs
        if (j.get("experience_min") or 0) >= MIN_JOB_EXP
    ]

    print(f"Target CVs  (exp < {MIN_JOB_EXP * EXP_GAP_THRESHOLD:.1f} yrs): {len(target_cvs)}")
    print(f"Target jobs (exp_min >= {MIN_JOB_EXP:.0f} yrs)         : {len(target_jobs)}")

    # Generate candidates
    rng = random.Random(SEED)
    candidates = []
    for cv in target_cvs:
        cv_exp = float(cv.get("experience_years") or 0)
        cv_sk  = cv_skills[cv["idx"]]
        for job in target_jobs:
            job_exp = float(job.get("experience_min") or 0)
            if job_exp <= 0:
                continue
            ratio = cv_exp / job_exp
            if ratio >= EXP_GAP_THRESHOLD:
                continue   # gap not big enough
            if (cv["idx"], job["idx"]) in existing:
                continue   # already in dataset
            job_sk  = set(job.get("skills", []))
            jaccard = _jaccard(cv_sk, job_sk)
            candidates.append((cv["idx"], job["idx"], cv_exp, job_exp, jaccard))

    rng.shuffle(candidates)
    selected = candidates[:max_pairs]
    print(f"Candidates found : {len(candidates):,}")
    print(f"Selected         : {len(selected):,} (cap={max_pairs})")

    if not selected:
        print("Nothing to add.")
        return

    # Build new label records
    new_labels = []
    for cv_idx, job_idx, cv_exp, job_exp, jaccard in selected:
        r = rng.random()
        split = "train" if r < 0.70 else ("val" if r < 0.85 else "test")
        new_labels.append({
            "cv_idx":         cv_idx,
            "job_idx":        job_idx,
            "label":          0,
            "overall":        0,
            "skill_fit":      _skill_fit(jaccard),
            "experience_fit": 0,
            "seniority_fit":  -1,   # not asserted
            "domain_fit":     -1,   # not asserted
            "split":          split,
            "synthetic":      True,
        })

    split_count = {s: sum(1 for l in new_labels if l["split"] == s) for s in ["train", "val", "test"]}
    print(f"New labels split : {split_count}")

    # Stats on skill_fit of synthetic pairs
    from collections import Counter
    sf = Counter(l["skill_fit"] for l in new_labels)
    print(f"skill_fit dist   : weak={sf[0]}, ok={sf[1]}, good={sf[2]}")

    if dry_run:
        print("Dry run — no files written.")
        return

    backup = (data_dir / "labels.json").with_suffix(".json.bak2")
    shutil.copy2(data_dir / "labels.json", backup)
    print(f"Backup: {backup}")

    merged = labels + new_labels
    with open(data_dir / "labels.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))

    total = len(merged)
    neg   = sum(1 for l in merged if l.get("overall", l.get("label", 0)) == 0)
    print(f"Dataset after : {total:,} labels, {neg:,} negative ({neg*100//total}%)")
    print(f"Done → {data_dir}/labels.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",      default="data/processed/b89_full")
    parser.add_argument("--max-pairs", default=MAX_PAIRS, type=int)
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()
    main(Path(args.data), args.max_pairs, args.dry_run)
