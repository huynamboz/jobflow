"""
Export training dataset from Django DB to JSON files.

Reads:
  - LabelingCV + CV.parsed_text   → cvs.json
  - LabelingJob + JDExtractionRecord.combined_text → jobs.json
  - HumanLabel + PairQueue.split  → labels.json
  - Skill catalog                 → skills.json
  + edge files: cv_skills.json, job_skills.json
  + metadata.json

Usage:
    cd backend
    python export_dataset.py
    python export_dataset.py --output data/processed/v2
    python export_dataset.py --min-cv-skills 2 --min-job-skills 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()


SENIORITY_MAP = {"INTERN": 0, "JUNIOR": 1, "MID": 2, "SENIOR": 3, "LEAD": 4, "MANAGER": 5}
EDUCATION_MAP = {"NONE": 0, "COLLEGE": 1, "BACHELOR": 2, "MASTER": 3, "PHD": 4}


def main(output_dir: Path, min_cv_skills: int, min_job_skills: int, batch_ids: list[int] | None = None) -> None:
    from apps.labeling.models import LabelingCV, LabelingJob, HumanLabel, PairQueue
    from apps.cvs.models import CV
    from apps.jobs.models import JDExtractionRecord
    from ml_service.data.skill_normalization import SkillNormalizer

    output_dir.mkdir(parents=True, exist_ok=True)
    normalizer = SkillNormalizer()
    skill_catalog = normalizer.skill_catalog  # canonical_name → SkillCategory

    # ── CVs ──────────────────────────────────────────────────────────────────
    print("Loading CVs...")
    labeling_cvs = list(LabelingCV.objects.all())

    # Fetch full text from CV source
    cv_texts: dict[int, str] = {}
    for cv_src in CV.objects.only("id", "parsed_text", "raw_text"):
        cv_texts[cv_src.id] = cv_src.parsed_text or cv_src.raw_text or ""

    cvs_out = []
    cv_skills_out = []
    labeling_cv_id_to_idx: dict[int, int] = {}  # LabelingCV.id → sequential index

    for lcv in labeling_cvs:
        skills = lcv.skills or []
        if len(skills) < min_cv_skills:
            continue

        idx = len(cvs_out)
        labeling_cv_id_to_idx[lcv.id] = idx

        skill_names = []
        skill_profs = []
        for s in skills:
            name = s["name"] if isinstance(s, dict) else str(s)
            prof = int(s.get("proficiency", 3)) if isinstance(s, dict) else 3
            if name in skill_catalog:
                skill_names.append(name)
                skill_profs.append(max(1, min(5, prof)))
                cv_skills_out.append({
                    "cv_idx": idx,
                    "skill": name,
                    "proficiency": max(1, min(5, prof)),
                })

        cvs_out.append({
            "idx":              idx,
            "labeling_cv_id":  lcv.id,
            "cv_id":           lcv.cv_id,
            "seniority":       SENIORITY_MAP.get(lcv.seniority, 2),
            "experience_years": float(lcv.experience_years or 0),
            "education":       EDUCATION_MAP.get(lcv.education, 2),
            "role_category":   lcv.role_category or "other",
            "skills":          skill_names,
            "skill_proficiencies": skill_profs,
            "text":            cv_texts.get(lcv.cv_id, lcv.text_summary or ""),
        })

    print(f"  {len(cvs_out)} CVs exported")

    # ── Jobs ─────────────────────────────────────────────────────────────────
    print("Loading Jobs...")
    labeling_jobs = list(LabelingJob.objects.all())

    # Fetch full combined_text from JDExtractionRecord
    jd_texts: dict[int, str] = {}
    for jd_src in JDExtractionRecord.objects.only("id", "combined_text"):
        jd_texts[jd_src.id] = jd_src.combined_text or ""

    jobs_out = []
    job_skills_out = []
    labeling_job_id_to_idx: dict[int, int] = {}  # LabelingJob.id → sequential index

    for ljob in labeling_jobs:
        skills = ljob.skills or []
        if len(skills) < min_job_skills:
            continue

        idx = len(jobs_out)
        labeling_job_id_to_idx[ljob.id] = idx

        skill_names = []
        skill_imps = []
        for s in skills:
            name = s["name"] if isinstance(s, dict) else str(s)
            imp = int(s.get("importance", 3)) if isinstance(s, dict) else 3
            if name in skill_catalog:
                skill_names.append(name)
                skill_imps.append(max(1, min(5, imp)))
                job_skills_out.append({
                    "job_idx":    idx,
                    "skill":      name,
                    "importance": max(1, min(5, imp)),
                })

        jobs_out.append({
            "idx":             idx,
            "labeling_job_id": ljob.id,
            "job_id":          ljob.job_id,
            "title":           ljob.title,
            "seniority":       SENIORITY_MAP.get(ljob.seniority, 2),
            "role_category":   ljob.role_category or "other",
            "experience_min":  float(ljob.experience_min or 0),
            "experience_max":  float(ljob.experience_max) if ljob.experience_max else None,
            "salary_min":      int(ljob.salary_min or 0),
            "salary_max":      int(ljob.salary_max or 0),
            "skills":          skill_names,
            "skill_importances": skill_imps,
            "text":            jd_texts.get(ljob.job_id, ljob.text_summary or ""),
        })

    print(f"  {len(jobs_out)} Jobs exported")

    # ── Labels ────────────────────────────────────────────────────────────────
    print("Loading Labels...")
    labels_out = []
    skipped = 0

    human_labels = HumanLabel.objects.select_related("pair__cv", "pair__job", "pair")
    if batch_ids:
        human_labels = human_labels.filter(batch_id__in=batch_ids)
        print(f"  (filtered to batch(es): {batch_ids})")

    # 021/A2: a pair can carry multiple labels across batches (re-labeling),
    # sometimes CONTRADICTORY. Keep exactly ONE per pair — the LATEST judgment
    # wins (created_at desc, id desc). Without this the graph receives both
    # match AND no_match edges for the same pair.
    latest_per_pair = {}
    num_input_labels = 0
    for hl in human_labels.order_by("pair_id", "-created_at", "-id"):
        num_input_labels += 1
        if hl.pair_id not in latest_per_pair:
            latest_per_pair[hl.pair_id] = hl
    num_dropped_duplicates = num_input_labels - len(latest_per_pair)
    print(f"  dedup: {num_input_labels} labels → {len(latest_per_pair)} pairs "
          f"({num_dropped_duplicates} duplicates dropped, latest wins)")
    human_labels = list(latest_per_pair.values())

    split_counts = {"train": 0, "val": 0, "test": 0}
    label_counts = {0: 0, 1: 0}

    for hl in human_labels:
        cv_idx  = labeling_cv_id_to_idx.get(hl.pair.cv_id)
        job_idx = labeling_job_id_to_idx.get(hl.pair.job_id)
        if cv_idx is None or job_idx is None:
            skipped += 1
            continue

        binary_label = 0 if hl.overall == 0 else 1
        split = hl.pair.split or "train"

        labels_out.append({
            "cv_idx":         cv_idx,
            "job_idx":        job_idx,
            "label":          binary_label,
            "overall":        hl.overall,
            "skill_fit":      hl.skill_fit,
            "seniority_fit":  hl.seniority_fit,
            "experience_fit": hl.experience_fit,
            "domain_fit":     hl.domain_fit,
            "split":          split,
        })

        split_counts[split] = split_counts.get(split, 0) + 1
        label_counts[binary_label] += 1

    print(f"  {len(labels_out)} labels exported ({skipped} skipped — CV/Job filtered out)")
    print(f"  positive={label_counts[1]}, negative={label_counts[0]}")
    print(f"  train={split_counts.get('train',0)}, val={split_counts.get('val',0)}, test={split_counts.get('test',0)}")

    # ── Skills ────────────────────────────────────────────────────────────────
    skills_out = [
        {"name": name, "category": int(cat)}
        for name, cat in skill_catalog.items()
    ]

    # ── Metadata ─────────────────────────────────────────────────────────────
    metadata = {
        "num_cvs":      len(cvs_out),
        "num_jobs":     len(jobs_out),
        "num_skills":   len(skills_out),
        "num_labels":   len(labels_out),
        "num_positive": label_counts[1],
        "num_negative": label_counts[0],
        "positive_rate": round(label_counts[1] / max(len(labels_out), 1), 4),
        "split": split_counts,
        "min_cv_skills":  min_cv_skills,
        "min_job_skills": min_job_skills,
        "batch_ids": batch_ids or "all",
        "dedup": "latest_per_pair",  # 021/A2
        "num_dropped_duplicates": num_dropped_duplicates,
    }

    # ── Write files ───────────────────────────────────────────────────────────
    files = {
        "cvs.json":        cvs_out,
        "jobs.json":       jobs_out,
        "skills.json":     skills_out,
        "cv_skills.json":  cv_skills_out,
        "job_skills.json": job_skills_out,
        "labels.json":     labels_out,
        "metadata.json":   metadata,
    }

    for fname, data in files.items():
        path = output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        size_kb = path.stat().st_size // 1024
        print(f"  {fname:<20} {len(data) if isinstance(data, list) else '':<8} {size_kb} KB")

    print(f"\nDone → {output_dir}/")
    print(f"  CVs: {len(cvs_out)}, Jobs: {len(jobs_out)}, Labels: {len(labels_out)}")
    print(f"  Positive rate: {metadata['positive_rate']:.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/processed/v2", help="Output directory")
    parser.add_argument("--min-cv-skills",  type=int, default=2)
    parser.add_argument("--min-job-skills", type=int, default=2)
    parser.add_argument("--batches", type=int, nargs="+", default=None,
                        help="Only include HumanLabels from these batch IDs (e.g. --batches 8 9)")
    args = parser.parse_args()

    main(Path(args.output), args.min_cv_skills, args.min_job_skills, args.batches)
