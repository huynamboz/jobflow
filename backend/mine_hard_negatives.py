"""Mine hard-negative CV–Job pairs from the current checkpoint.

Hard negatives: pairs where Stage-1 score is HIGH (model is "confused")
but skill overlap is LOW (they are factually different), and NOT already labeled.

These are sent to LLM labeling — expected ~80-90% will be negative,
teaching the model to distinguish near-miss cases.

Output: JSONL file, one candidate per line:
  {"cv_id": <CV.id>, "job_id": <JDExtractionRecord.id>,
   "stage1_score": float, "gnn_score": float, "skill_overlap": float}

Usage:
    cd backend
    python mine_hard_negatives.py
    python mine_hard_negatives.py --n 1500 --threshold 0.48 --max-overlap 0.30
    python mine_hard_negatives.py --checkpoint checkpoints/latest --out data/hard_neg_candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("mine_hard_neg")


def _jaccard(a: tuple | list, b: tuple | list) -> float:
    s1, s2 = set(a), set(b)
    if not s1 and not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def load_existing_pairs(data_dir: Path) -> set[tuple[int, int]]:
    """Return set of (cv_id, job_id) already labeled — from dataset files + DB."""
    existing: set[tuple[int, int]] = set()

    # --- From b89 dataset files ---
    lbl_path = data_dir / "labels.json"
    cvs_path = data_dir / "cvs.json"
    jobs_path = data_dir / "jobs.json"
    if lbl_path.exists() and cvs_path.exists() and jobs_path.exists():
        with open(cvs_path, encoding="utf-8") as f:
            raw_cvs = json.load(f)
        with open(jobs_path, encoding="utf-8") as f:
            raw_jobs = json.load(f)
        with open(lbl_path, encoding="utf-8") as f:
            labels = json.load(f)
        cv_idx_to_id = {c["idx"]: c["cv_id"] for c in raw_cvs}
        job_idx_to_id = {j["idx"]: j["job_id"] for j in raw_jobs}
        for lbl in labels:
            cv_id = cv_idx_to_id.get(lbl["cv_idx"])
            job_id = job_idx_to_id.get(lbl["job_idx"])
            if cv_id and job_id:
                existing.add((cv_id, job_id))
        logger.info("Dataset: %d existing labeled pairs", len(existing))

    # --- From DB PairQueue (covers batches not yet in labels.json) ---
    from apps.labeling.models import PairQueue
    db_pairs = set(PairQueue.objects.values_list("cv__cv_id", "job__job_id"))
    before = len(existing)
    existing |= db_pairs
    logger.info("DB PairQueue: %d pairs (added %d new)", len(db_pairs), len(existing) - before)

    return existing


def mine(
    checkpoint_dir: Path,
    data_dir: Path,
    threshold: float,
    max_overlap: float,
    n: int,
    out_path: Path,
    max_per_cv: int,
    seed: int,
) -> None:
    random.seed(seed)

    from ml_service.config import get_settings
    from ml_service.data.skill_normalization import SkillNormalizer
    from ml_service.embedding import get_provider
    from ml_service.inference import InferenceEngine

    ml_cfg = get_settings()
    normalizer = SkillNormalizer(ml_cfg.skill_alias_path)
    provider = get_provider()

    logger.info("Loading engine from %s ...", checkpoint_dir)
    engine = InferenceEngine.from_checkpoint(checkpoint_dir, normalizer, provider)

    cvs = engine.cv_pool
    jobs = engine.job_pool
    logger.info("Engine: %d CVs, %d jobs", len(cvs), len(jobs))

    existing = load_existing_pairs(data_dir)
    logger.info("Pairs to skip (already labeled): %d", len(existing))

    candidates: list[dict] = []

    for cv_i, cv in enumerate(cvs):
        if (cv_i + 1) % 50 == 0:
            logger.info("  Scoring CV %d/%d — candidates so far: %d", cv_i + 1, len(cvs), len(candidates))

        cv_text_vec = provider.encode([cv.text])[0]
        cv_gnn_emb = engine._get_cv_gnn_embedding(cv)

        cv_candidates: list[dict] = []
        for job_i, job in enumerate(jobs):
            # Skip already labeled pairs
            if (cv.cv_id, job.job_id) in existing:
                continue

            # Fast filter: skip if skill overlap is too high (not a hard negative)
            overlap = _jaccard(cv.skills, job.skills)
            if overlap >= max_overlap:
                continue

            # Skip obvious negatives (seniority too far apart, likely easy negatives)
            if abs(int(cv.seniority) - int(job.seniority)) >= 3:
                continue

            stage1 = engine._score_pair_fast(cv, job, job_i, cv_text_vec, cv_gnn_emb)
            if stage1 < threshold:
                continue

            gnn = engine._gnn_score_fast(cv, job, job_i, cv_text_vec, cv_gnn_emb)
            cv_candidates.append({
                "cv_id": cv.cv_id,
                "job_id": job.job_id,
                "stage1_score": round(float(stage1), 4),
                "gnn_score": round(float(gnn), 4),
                "skill_overlap": round(float(overlap), 4),
            })

        # Sort by stage1_score desc, keep top max_per_cv per CV for diversity
        cv_candidates.sort(key=lambda x: -x["stage1_score"])
        candidates.extend(cv_candidates[:max_per_cv])

    logger.info("Raw candidates: %d", len(candidates))

    # Shuffle + sample n
    random.shuffle(candidates)
    final = candidates[:n]

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for c in final:
            f.write(json.dumps(c) + "\n")

    avg_s1 = sum(c["stage1_score"] for c in final) / max(len(final), 1)
    avg_ov = sum(c["skill_overlap"] for c in final) / max(len(final), 1)
    logger.info(
        "Wrote %d hard-negative candidates → %s  (avg_stage1=%.3f, avg_overlap=%.3f)",
        len(final), out_path, avg_s1, avg_ov,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mine hard-negative CV–Job pairs")
    parser.add_argument("--checkpoint",   default="checkpoints/latest",              help="Checkpoint dir")
    parser.add_argument("--data",         default="data/processed/b89",              help="Dataset dir (for existing pair lookup)")
    parser.add_argument("--threshold",    type=float, default=0.50,                  help="Min Stage-1 score to qualify as hard negative")
    parser.add_argument("--max-overlap",  type=float, default=0.35,                  help="Max skill Jaccard overlap (higher = too easy)")
    parser.add_argument("--n",            type=int,   default=2000,                  help="Max candidates to output")
    parser.add_argument("--max-per-cv",   type=int,   default=10,                    help="Max candidates per CV (for diversity)")
    parser.add_argument("--out",          default="data/hard_neg_candidates.jsonl",  help="Output JSONL path")
    parser.add_argument("--seed",         type=int,   default=42)
    args = parser.parse_args()

    mine(
        checkpoint_dir=Path(args.checkpoint),
        data_dir=Path(args.data),
        threshold=args.threshold,
        max_overlap=args.max_overlap,
        n=args.n,
        out_path=Path(args.out),
        max_per_cv=args.max_per_cv,
        seed=args.seed,
    )
