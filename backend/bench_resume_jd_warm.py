"""WARM-START person-job-fit benchmark on the local resume-JD dataset.

Same per-resume full-ranking protocol and SAME model harness as
``bench_resume_jd.py`` (which it imports as ``B`` and reuses wholesale), with
TWO deliberate changes that make the GNN's collaborative signal meaningful:

  1. **LLM-extracted features** instead of rule-based skill regex. The bundled
     ``data/resume_jd/features.json`` carries, per resume AND per job, a canonical
     lowercase ``skills`` list, a ``seniority`` bucket, a ``domain`` string and an
     ``experience_years`` int — all extracted by an LLM. We feed those straight into
     ``CVData`` / ``JobData`` so the skill graph and the per-dimension baselines see
     a clean, rich signal rather than whatever a keyword matcher scrapes from text.

  2. **WARM-START leave-one-out re-split** (the key fix). The original dataset split
     is IGNORED. Instead we build per-resume positive lists and hold out, per resume,
     1 positive → test and (if available) 1 → val, leaving the rest → train. Every
     resume therefore has train history, and because each job is positive for many
     resumes, the test jobs stay *warm* (seen during training through other resumes'
     edges). This is the collaborative-filtering regime where HeteroGraphSAGE's
     warm fit-edges + content node features can actually beat content-only / CF
     baselines — unlike the cold-item split where no test job is ever seen in train.

Models (rows):  Random, Rule-Based (skill overlap, now on LLM skills), BM25,
                SBERT (cosine), MLP, HeteroGraphSAGE (Ours)
Metrics (cols): Recall@{5,10,20}, NDCG@{5,10,20}, MRR
Protocol:       per-resume full-ranking over the job pool (same harness for GNN
                via train_generic and baselines via PerCVEvaluator).

Positive policy (``--positive``):
  good_potential (default) — "Good Fit" AND "Potential Fit" count as relevant.
  good_only                — only "Good Fit" is relevant.

Usage (from backend/):
    # fast end-to-end smoke (subsamples ~120 resumes)
    python bench_resume_jd_warm.py --smoke
    # full run
    python bench_resume_jd_warm.py --seed 42 --embedding english --max-epochs 300

Writes results JSON to results/resume_jd_warm/benchmark.json and prints a table.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import random
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Reuse the proven pipeline wholesale: embedding cache, scorers, run_gnn,
# run_baseline, print_table, KS, METRIC_COLS, etc. Importing B also pre-warms
# sklearn / torch_geometric (its module-level side effects).
import bench_resume_jd as B

import numpy as np
import torch

from ml_benchmark.baselines.bm25 import BM25Scorer
from ml_benchmark.baselines.skill_overlap import SkillOverlapScorer
from ml_benchmark.graph.schema import (
    CVData,
    EducationLevel,
    JobData,
    LabeledPair,
    SeniorityLevel,
    SkillCategory,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("bench_resume_jd_warm")

DATASET_NAME = "resume-job-description-fit (local, LLM features, warm-start)"
DATA_DIR = _BACKEND_DIR.parent / "data" / "resume_jd"
DEFAULT_SKILL_CAT = SkillCategory.TECHNICAL  # single default category for all skills

# LLM seniority string → SeniorityLevel enum member. Enum members are exactly
# INTERN / JUNIOR / MID / SENIOR / LEAD / MANAGER, so the lowercase strings in
# features.json map 1:1. Anything unknown defaults to MID.
SENIORITY_MAP: dict[str, SeniorityLevel] = {
    "intern": SeniorityLevel.INTERN,
    "junior": SeniorityLevel.JUNIOR,
    "mid": SeniorityLevel.MID,
    "senior": SeniorityLevel.SENIOR,
    "lead": SeniorityLevel.LEAD,
    "manager": SeniorityLevel.MANAGER,
}


def _map_seniority(raw) -> SeniorityLevel:
    if not raw:
        return SeniorityLevel.MID
    return SENIORITY_MAP.get(str(raw).strip().lower(), SeniorityLevel.MID)


def _exp_years(raw) -> float:
    try:
        return float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Load raw json
# ---------------------------------------------------------------------------


def _load_json(name: str):
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Expected dataset file not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_data(smoke: bool, seed: int):
    """Load the 4 json files. In smoke mode keep ~120 resumes (and all their pairs).

    Returns (resumes, jobs, pairs, features) where pairs is filtered to the kept
    resumes in smoke mode.
    """
    resumes = _load_json("resumes.json")   # {resume_id: text}
    jobs = _load_json("jobs.json")         # {job_id: text}
    pairs = _load_json("pairs.json")       # [{resume_id, job_id, label, split}]
    features = _load_json("features.json")  # {doc_id: {skills, seniority, domain, experience_years}}

    if smoke:
        rng = random.Random(seed)
        # Prefer resumes that have at least one relevant pair so eval isn't empty.
        pos_labels = {"Good Fit", "Potential Fit"}
        has_pos: dict[str, bool] = {}
        for p in pairs:
            if p["label"] in pos_labels:
                has_pos[p["resume_id"]] = True
        all_rids = list(resumes.keys())
        rng.shuffle(all_rids)
        all_rids.sort(key=lambda r: (not has_pos.get(r, False)))
        keep = set(all_rids[:120])
        resumes = {r: t for r, t in resumes.items() if r in keep}
        pairs = [p for p in pairs if p["resume_id"] in keep]
        logger.info("SMOKE: subsampled to %d resumes / %d pairs", len(keep), len(pairs))

    return resumes, jobs, pairs, features


# ---------------------------------------------------------------------------
# Build schema objects (LLM features) + WARM-START re-split
# ---------------------------------------------------------------------------


def build_schema_objects(resumes, jobs, pairs, features, *, positive: str, seed: int):
    """Build CVData/JobData/skill_catalog and the warm-start LabeledPair list.

    Returns (cvs, jobs_list, pairs_out, skill_catalog, stats).
    """
    # 1. Stable integer ids: sorted order of the string ids.
    resume_ids = sorted(resumes.keys())          # e.g. ["R0000", "R0001", ...]
    job_ids = sorted(jobs.keys())                # e.g. ["J0000", "J0001", ...]
    rid_to_cv = {rid: i for i, rid in enumerate(resume_ids)}
    jid_to_job = {jid: i for i, jid in enumerate(job_ids)}

    def _skills(doc_id) -> list[str]:
        feat = features.get(doc_id) or {}
        return [str(s).strip().lower() for s in (feat.get("skills") or []) if str(s).strip()]

    # 2a. CVData per resume (LLM features).
    cvs: list[CVData] = []
    for rid in resume_ids:
        feat = features.get(rid) or {}
        sk = tuple(_skills(rid))
        cvs.append(
            CVData(
                cv_id=rid_to_cv[rid],
                seniority=_map_seniority(feat.get("seniority")),
                experience_years=_exp_years(feat.get("experience_years")),
                education=EducationLevel.BACHELOR,        # not extracted → sensible default
                skills=sk,
                skill_proficiencies=tuple(3 for _ in sk),  # mid proficiency, no per-skill signal
                text=resumes[rid],
            )
        )

    # 2b. JobData per job (LLM features). domain → role_category, exp → experience_min.
    jobs_list: list[JobData] = []
    for jid in job_ids:
        feat = features.get(jid) or {}
        sk = tuple(_skills(jid))
        jobs_list.append(
            JobData(
                job_id=jid_to_job[jid],
                seniority=_map_seniority(feat.get("seniority")),
                skills=sk,
                skill_importances=tuple(3 for _ in sk),
                salary_min=0,
                salary_max=0,
                text=jobs[jid],
                experience_min=_exp_years(feat.get("experience_years")),
                experience_max=None,
                role_category=str(feat.get("domain") or ""),
            )
        )

    # 3. skill catalog: union of all skills across resumes + jobs → default category.
    all_skills: set[str] = set()
    for rid in resume_ids:
        all_skills.update(_skills(rid))
    for jid in job_ids:
        all_skills.update(_skills(jid))
    skill_catalog: dict[str, SkillCategory] = {s: DEFAULT_SKILL_CAT for s in sorted(all_skills)}

    # 4. WARM-START re-split — IGNORE p["split"].
    #    positive policy decides which labels count as relevant.
    if positive == "good_only":
        pos_labels = {"Good Fit"}
    else:  # "good_potential"
        pos_labels = {"Good Fit", "Potential Fit"}

    # Per-resume positive (cv_id, job_id) lists, deduped, deterministic order.
    pos_by_cv: dict[int, list[int]] = {}
    seen_pair: set[tuple[int, int]] = set()
    for p in pairs:
        if p["label"] not in pos_labels:
            continue
        rid, jid = p["resume_id"], p["job_id"]
        if rid not in rid_to_cv or jid not in jid_to_job:
            continue
        ci, ji = rid_to_cv[rid], jid_to_job[jid]
        key = (ci, ji)
        if key in seen_pair:
            continue
        seen_pair.add(key)
        pos_by_cv.setdefault(ci, []).append(ji)

    rng = random.Random(seed)
    train_pairs: list[tuple[int, int]] = []
    val_pairs: list[tuple[int, int]] = []
    test_pairs: list[tuple[int, int]] = []

    for ci, jids in pos_by_cv.items():
        jids = sorted(jids)            # determinism before shuffle
        rng.shuffle(jids)
        n = len(jids)
        if n >= 2:
            # 1 → test, the rest → train; if >=3 also carve 1 → val.
            test_pairs.append((ci, jids[0]))
            if n >= 3:
                val_pairs.append((ci, jids[1]))
                train_pairs.extend((ci, j) for j in jids[2:])
            else:
                train_pairs.extend((ci, j) for j in jids[1:])
        else:
            # <2 positives → everything to train (no held-out eval for this resume).
            train_pairs.extend((ci, j) for j in jids)

    # 5. LabeledPair list (positives only; ranker treats all other jobs as negatives).
    pairs_out: list[LabeledPair] = []
    for ci, ji in train_pairs:
        pairs_out.append(LabeledPair(cv_id=ci, job_id=ji, label=1, split="train"))
    for ci, ji in val_pairs:
        pairs_out.append(LabeledPair(cv_id=ci, job_id=ji, label=1, split="val"))
    for ci, ji in test_pairs:
        pairs_out.append(LabeledPair(cv_id=ci, job_id=ji, label=1, split="test"))

    # 4b. Warm-start verification: how many unique test jobs also appear in train?
    train_job_set = {ji for _, ji in train_pairs}
    test_job_set = {ji for _, ji in test_pairs}
    warm_test_jobs = len(test_job_set & train_job_set)
    cold_test_jobs = len(test_job_set - train_job_set)

    stats = {
        "positive_policy": positive,
        "num_resumes": len(resume_ids),
        "num_jobs": len(job_ids),
        "num_skills": len(skill_catalog),
        "num_resumes_with_positives": len(pos_by_cv),
        "num_train_pos": len(train_pairs),
        "num_val_pos": len(val_pairs),
        "num_test_pos": len(test_pairs),
        "num_test_resumes": len({ci for ci, _ in test_pairs}),
        "unique_test_jobs": len(test_job_set),
        "unique_test_jobs_seen_in_train": warm_test_jobs,   # warm-start verification
        "unique_test_jobs_cold": cold_test_jobs,
        "warm_fraction": round(warm_test_jobs / max(1, len(test_job_set)), 4),
    }
    return cvs, jobs_list, pairs_out, skill_catalog, stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--embedding", type=str, default="english",
                        help="Embedding provider name (multilingual is a placeholder "
                             "that falls back to 'english').")
    parser.add_argument("--max-epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--mlp-epochs", type=int, default=50)
    parser.add_argument("--positive", type=str, default="good_potential",
                        choices=["good_potential", "good_only"],
                        help="Which labels count as relevant positives.")
    parser.add_argument(
        "--output",
        type=Path,
        default=_BACKEND_DIR / "results" / "resume_jd_warm" / "benchmark.json",
    )
    parser.add_argument("--smoke", action="store_true",
                        help="Subsample ~120 resumes for a fast end-to-end test.")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    t_start = time.time()

    # 1. Embedding provider (reuse B's fallback logic).
    embed = B.make_embedding_provider(args.embedding)

    # 2. Load data + build schema objects with the warm-start split.
    resumes, jobs_raw, pairs_raw, features = load_data(smoke=args.smoke, seed=args.seed)
    cvs, jobs, pairs, skill_catalog, stats = build_schema_objects(
        resumes, jobs_raw, pairs_raw, features, positive=args.positive, seed=args.seed
    )
    logger.info("Dataset stats: %s", stats)
    logger.info(
        "WARM-START check: %d/%d unique test jobs ALSO appear in train (%.1f%% warm); "
        "%d cold.",
        stats["unique_test_jobs_seen_in_train"], stats["unique_test_jobs"],
        100.0 * stats["warm_fraction"], stats["unique_test_jobs_cold"],
    )

    # 3. Precompute embeddings ONCE for all cvs + jobs (shared by SBERT + MLP).
    cv_emb, job_emb = B.build_embedding_cache(embed, cvs, jobs, batch_size=256)

    # train corpora for BM25 fit / MLP fit (resumes/jobs that appear in train positives).
    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    train_cv_ids = {p.cv_id for p in train_pos}
    train_job_ids = {p.job_id for p in train_pos}
    train_cvs = [c for c in cvs if c.cv_id in train_cv_ids]
    train_jobs = [j for j in jobs if j.job_id in train_job_ids]

    results: dict[str, dict[str, float]] = {}

    # 4. Baselines (same per-CV full-ranking harness, ks = B.KS = (5, 10, 20)).
    logger.info("Eval: Random")
    results["Random"] = B.run_baseline(B.RandomScorer(seed=args.seed), cvs, jobs, pairs)

    logger.info("Eval: Rule-Based (skill overlap, LLM skills)")
    results["Rule-Based (skill overlap)"] = B.run_baseline(
        SkillOverlapScorer(), cvs, jobs, pairs
    )

    logger.info("Eval: BM25")
    bm25 = BM25Scorer().fit(train_cvs if train_cvs else cvs)
    results["BM25"] = B.run_baseline(bm25, cvs, jobs, pairs)

    logger.info("Eval: SBERT (cosine)")
    results["SBERT (cosine)"] = B.run_baseline(
        B.CachedCosineScorer(cv_emb, job_emb), cvs, jobs, pairs
    )

    logger.info("Eval: MLP")
    mlp = B.MLPScorer(cv_emb, job_emb, dim=int(embed.dim), seed=args.seed, epochs=args.mlp_epochs)
    # Fit on ALL train pairs (here positives only — warm-start split holds positives;
    # MLPScorer's BCE still trains, full-space negatives are implicit at rank time).
    train_pairs_all = [p for p in pairs if p.split == "train"]
    mlp.fit(train_cvs if train_cvs else cvs, train_jobs if train_jobs else jobs, train_pairs_all)
    results["MLP"] = B.run_baseline(mlp, cvs, jobs, pairs)

    # 5. GNN (Ours) — warm collaborative fit-edges + content node features.
    #    Signature: run_gnn(cvs, jobs, pairs, skill_catalog, embed, *, seed, max_epochs,
    #                        patience, hidden, num_layers, lr, weight_decay)
    logger.info("Eval: HeteroGraphSAGE (Ours)")
    results["HeteroGraphSAGE (Ours)"] = B.run_gnn(
        cvs, jobs, pairs, skill_catalog, embed,
        seed=args.seed,
        max_epochs=args.max_epochs,
        patience=args.patience,
        hidden=args.hidden,
        num_layers=args.num_layers,
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    elapsed = time.time() - t_start

    # 6. Print + persist.
    B.print_table(results)

    output = {
        "dataset": DATASET_NAME,
        "data_dir": str(DATA_DIR),
        "task": "per-resume full-ranking, WARM-START split, LLM-extracted features",
        "smoke": args.smoke,
        "positive_policy": args.positive,
        "embedding_requested": args.embedding,
        "embedding_dim": int(embed.dim),
        "ks": list(B.KS),
        "metrics": B.METRIC_COLS,
        "stats": stats,
        "warm_start_verification": {
            "unique_test_jobs": stats["unique_test_jobs"],
            "unique_test_jobs_seen_in_train": stats["unique_test_jobs_seen_in_train"],
            "unique_test_jobs_cold": stats["unique_test_jobs_cold"],
            "warm_fraction": stats["warm_fraction"],
        },
        "config": {
            "seed": args.seed,
            "max_epochs": args.max_epochs,
            "patience": args.patience,
            "hidden": args.hidden,
            "num_layers": args.num_layers,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "mlp_epochs": args.mlp_epochs,
        },
        "results": results,
        "wall_time_seconds": round(elapsed, 2),
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Wrote results to %s (%.1fs)", args.output, elapsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
