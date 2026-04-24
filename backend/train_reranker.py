"""
Train Stage 2 reranker + Platt calibration on existing labeled pairs.

Usage:
    cd backend
    python train_reranker.py
    python train_reranker.py --data data/processed/b89 --checkpoint checkpoints/latest
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from ml_service.data.skill_normalization import SkillNormalizer
from ml_service.embedding import get_provider
from ml_service.inference import InferenceEngine

_BACKEND_DIR = Path(__file__).parent
DEFAULT_SKILL_ALIAS = _BACKEND_DIR / "ml_service" / "data" / "skill-alias.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("train_reranker")


def load_labels(data_dir: Path):
    with open(data_dir / "labels.json", encoding="utf-8") as f:
        raw = json.load(f)

    with open(data_dir / "cvs.json", encoding="utf-8") as f:
        raw_cvs = json.load(f)
    with open(data_dir / "jobs.json", encoding="utf-8") as f:
        raw_jobs = json.load(f)

    cv_idx_to_db_id = {c["idx"]: c["cv_id"] for c in raw_cvs}
    job_idx_to_db_id = {j["idx"]: j["job_id"] for j in raw_jobs}

    train, val = [], []
    for lbl in raw:
        cv_db_id = cv_idx_to_db_id.get(lbl["cv_idx"])
        job_db_id = job_idx_to_db_id.get(lbl["job_idx"])
        if cv_db_id is None or job_db_id is None:
            continue
        record = {
            "cv_id": cv_db_id,
            "job_id": job_db_id,
            "label": lbl.get("overall", lbl["label"]),
            "skill_fit":      lbl.get("skill_fit", -1),
            "experience_fit": lbl.get("experience_fit", -1),
            "seniority_fit":  lbl.get("seniority_fit", -1),
            "domain_fit":     lbl.get("domain_fit", -1),
        }
        if lbl.get("split") == "val":
            val.append(record)
        elif lbl.get("split") == "train":
            train.append(record)

    logger.info("Labels: %d train, %d val", len(train), len(val))
    return train, val


def build_index_pairs(records, cv_id_to_idx, job_id_to_idx):
    cv_indices, job_indices, labels, dim_labels = [], [], [], []
    skipped = 0
    for r in records:
        ci = cv_id_to_idx.get(r["cv_id"])
        ji = job_id_to_idx.get(r["job_id"])
        if ci is None or ji is None:
            skipped += 1
            continue
        cv_indices.append(ci)
        job_indices.append(ji)
        labels.append(r["label"])
        dim_labels.append({
            "skill_fit":      r.get("skill_fit", -1),
            "experience_fit": r.get("experience_fit", -1),
            "seniority_fit":  r.get("seniority_fit", -1),
            "domain_fit":     r.get("domain_fit", -1),
        })
    if skipped:
        logger.warning("Skipped %d pairs (CV/Job not in engine pool)", skipped)
    return cv_indices, job_indices, labels, dim_labels


def main(data_dir: Path, checkpoint_dir: Path, *, epochs: int = 150, aux_weight: float = 0.3, skill_alias: Path | None = None) -> None:
    logger.info("Loading engine from %s ...", checkpoint_dir)
    normalizer = SkillNormalizer(str(skill_alias or DEFAULT_SKILL_ALIAS))
    provider = get_provider()
    engine = InferenceEngine.from_checkpoint(checkpoint_dir, normalizer, provider)

    cv_id_to_idx  = {cv.cv_id:   i for i, cv  in enumerate(engine.cv_pool)}
    job_id_to_idx = {job.job_id: i for i, job in enumerate(engine.job_pool)}
    logger.info("Engine: %d CVs, %d jobs", len(cv_id_to_idx), len(job_id_to_idx))

    train_records, val_records = load_labels(data_dir)

    train_cv, train_job, train_lbl, train_dim = build_index_pairs(train_records, cv_id_to_idx, job_id_to_idx)
    val_cv,   val_job,   val_lbl,   _         = build_index_pairs(val_records,   cv_id_to_idx, job_id_to_idx)

    logger.info("Usable pairs — train: %d, val: %d", len(train_lbl), len(val_lbl))
    pos = sum(train_lbl)
    logger.info("Train pos/neg: %d / %d", pos, len(train_lbl) - pos)

    cvs = engine.cv_pool
    jobs = engine.job_pool

    # --- Pre-compute GNN + Stage1 scores (cache per CV to avoid redundant encodes) ---
    def compute_scores(cv_indices, job_indices):
        cv_text_cache: dict[int, np.ndarray] = {}
        cv_gnn_cache: dict[int, object] = {}
        gnn_scores, stage1_scores = [], []
        for ci, ji in zip(cv_indices, job_indices):
            if ci not in cv_text_cache:
                cv_text_cache[ci] = provider.encode([cvs[ci].text])[0]
                cv_gnn_cache[ci] = engine._get_cv_gnn_embedding(cvs[ci])
            gnn_s = engine._gnn_score_fast(cvs[ci], jobs[ji], ji, cv_text_cache[ci], cv_gnn_cache[ci])
            s1_s  = engine._score_pair_fast(cvs[ci], jobs[ji], ji, cv_text_cache[ci], cv_gnn_cache[ci])
            gnn_scores.append(gnn_s)
            stage1_scores.append(s1_s)
        return gnn_scores, stage1_scores

    logger.info("Pre-computing GNN + Stage1 scores for %d train pairs ...", len(train_lbl))
    train_gnn, train_s1 = compute_scores(train_cv, train_job)

    # --- Train reranker ---
    # Force ordinal mode regardless of what was loaded from checkpoint
    engine.reranker._ordinal = True
    engine.reranker._model = None
    engine.reranker._trained = False

    logger.info("Training reranker (ordinal + multi-task, epochs=%d, aux_weight=%.2f) ...", epochs, aux_weight)
    metrics = engine.train_reranker(train_cv, train_job, train_lbl, gnn_scores=train_gnn, stage1_scores=train_s1, dim_labels=train_dim, epochs=epochs, aux_weight=aux_weight)
    logger.info("Reranker metrics: %s", {k: round(v, 4) for k, v in metrics.items()})

    # --- Calibrate on val set ---
    if val_lbl:
        logger.info("Pre-computing Stage1 scores for %d val pairs ...", len(val_lbl))
        _, val_s1 = compute_scores(val_cv, val_job)
        # Platt calibrator expects binary labels (0/1); convert from ordinal (0/1/2)
        val_lbl_binary = [1 if l >= 1 else 0 for l in val_lbl]
        engine.calibrate(val_s1, val_lbl_binary)
        logger.info("Calibration fitted on %d val pairs", len(val_lbl))

    # --- Save to checkpoint ---
    engine.reranker.save(checkpoint_dir)
    logger.info("Saved reranker to %s", checkpoint_dir)

    # Also save to week10 versioned checkpoint if it exists
    versioned = checkpoint_dir.parent / "week10-b89-auc0790"
    if versioned.exists():
        engine.reranker.save(versioned)
        from ml_service.reranker.calibration import PlattCalibrator
        engine._calibrator.save(versioned)
        logger.info("Also saved to %s", versioned)

    logger.info("Done. Reranker + calibration saved.")
    if metrics:
        logger.info("Final reranker accuracy: %.4f", metrics.get("accuracy", 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",       default="data/processed/b89",  help="Dataset dir with labels.json")
    parser.add_argument("--checkpoint", default="checkpoints/latest",   help="Checkpoint dir to save into")
    parser.add_argument("--epochs",      default=150, type=int,   help="Training epochs (default: 150)")
    parser.add_argument("--aux-weight",  default=0.3, type=float, help="Multi-task auxiliary loss weight (default: 0.3)")
    parser.add_argument("--skill-alias", default=None,             help="Path to skill-alias.json (default: auto-detect)")
    args = parser.parse_args()
    main(
        Path(args.data), Path(args.checkpoint),
        epochs=args.epochs, aux_weight=args.aux_weight,
        skill_alias=Path(args.skill_alias) if args.skill_alias else None,
    )
