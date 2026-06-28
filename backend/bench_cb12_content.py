"""Benchmark several models on CareerBuilder12 in a CONTENT + collaborative setup,
reusing the ``bench_resume_jd.py`` pipeline.

Why this file exists
--------------------
The earlier CB12 run was BIPARTITE with NO node features (random Xavier) — so
HeteroGraphSAGE had nothing to lean on and lost to LightGCN. CB12 jobs DO have
rich text (Title + Description in ``Dataset/careerbuilder-12/jobs_filtered.tsv``).
This benchmark converts CB12 into the same CVData/JobData CONTENT schema that
``bench_resume_jd.py`` uses, then runs the SAME models through the SAME harness:

  Methods (rows):  Random, Rule-Based (skill overlap), BM25, SBERT (cosine),
                   MLP, HeteroGraphSAGE (Ours)
  Metrics (cols):  Recall@{5,10,20}, NDCG@{5,10,20}, MRR
  Protocol:        per-user full-ranking over the job pool, train-seen jobs
                   excluded — identical to the resume-JD harness, so the two
                   benchmarks are directly comparable.

CB12 is WARM-START (every held-out test job also appears in some user's train
applications, by construction of the k-core + leave-one-out split), so the GNN
decoder eval produces real (non-zero) numbers — unlike the cold-item resume-JD
case where test JDs are unseen.

Content schema built from CB12:
  * Job TEXT   = f"{Title}. {Description[:2000]}"  (from jobs_filtered.tsv)
  * Job skills = regex-extracted from that text   (reused skill engine)
  * Job seniority = parsed from the Title          (reused parser)
  * User TEXT  = concatenation of the Titles of the jobs the user applied to in
                 TRAIN (a pseudo-resume — the only user-side content CB12 offers)
  * User skills = regex-extracted from that pseudo-resume text

Positives are implicit-feedback applications (label == 1); there are no labelled
negatives. The per-user ranking eval ranks ALL jobs and checks whether the
held-out applied (test) job lands in the top-k.

LightGCN is NOT run here — it is a separate ID-only CF baseline already
benchmarked on CB12; cite its number from the prior bipartite run. This file
focuses on Random / Rule-Based / BM25 / SBERT / Ours through one content harness.

Usage (from backend/):
    # fast end-to-end smoke (small subsample, ~3000 users)
    python bench_cb12_content.py --smoke
    # full run
    python bench_cb12_content.py --subsample-users 50000 --k-core 10 \
        --seed 42 --embedding english --max-epochs 300

Writes results JSON to results/cb12_content/benchmark.json and prints a table.

IMPORTANT — what the GNN actually consumes
------------------------------------------
``bench_resume_jd.run_gnn`` builds the hetero graph via ``GraphBuilder`` (which
DOES encode the content text into ``data["cv"/"job"].x``) and then trains with
``Trainer.train_generic``. ``train_generic`` REPLACES every node type's ``.x``
with a fresh learnable ``nn.Embedding`` table (Xavier init) and learns it by BPR
— so the GNN's *node features* are learned ID embeddings over the warm-start
apply graph, NOT the frozen SBERT content vectors (the content text only fixes
the embedding-table DIMENSION). This is the SAME behaviour as the resume-JD
benchmark, kept identical here for apples-to-apples comparability. The content
text is what lets the *non-GNN* baselines (BM25 / SBERT / MLP) score at all; the
GNN's edge is the collaborative apply graph plus warm-start. We reuse
``B.run_gnn`` verbatim rather than fork the trainer.
"""

from __future__ import annotations

import argparse
import csv
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

# Pre-warm heavy libs BEFORE anything else (mirrors bench_resume_jd.py).
import sklearn.metrics.pairwise  # noqa: F401,E402  pre-warm
import torch_geometric  # noqa: F401,E402  pre-load

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

# Reuse the resume-JD machinery wholesale — do NOT duplicate model/eval logic.
import bench_resume_jd as B  # noqa: E402

from ml_benchmark.data.careerbuilder_loader import (  # noqa: E402
    _parse_seniority_from_title,
    load_careerbuilder_12,
)
from ml_benchmark.graph.schema import (  # noqa: E402
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
logger = logging.getLogger("bench_cb12_content")

DATASET_NAME = "CareerBuilder12 (content + collaborative)"
# Repo-root Dataset/ (the loader's default), not backend/Dataset/.
CACHE_DIR = _BACKEND_DIR.parent / "Dataset" / "careerbuilder-12"
JOBS_FILTERED = CACHE_DIR / "jobs_filtered.tsv"

KS = B.KS                       # (5, 10, 20)
METRIC_COLS = B.METRIC_COLS     # recall@k.. ndcg@k.. mrr
DEFAULT_SKILL_CAT = SkillCategory.TECHNICAL

DESC_MAX_CHARS = 2000           # truncate job Description before embedding
USER_TEXT_MAX_TITLES = 40       # cap pseudo-resume length (history can be long)

_SENIORITY_NAME_TO_ENUM = {
    "intern": SeniorityLevel.INTERN,
    "junior": SeniorityLevel.JUNIOR,
    "mid": SeniorityLevel.MID,
    "senior": SeniorityLevel.SENIOR,
    "lead": SeniorityLevel.LEAD,
    "manager": SeniorityLevel.MANAGER,
}


# ---------------------------------------------------------------------------
# Parse jobs_filtered.tsv -> {JobID(int): (title, description)}
# ---------------------------------------------------------------------------


def load_job_text_map(
    jobs_path: Path, keep_job_ids: set[int]
) -> dict[int, tuple[str, str]]:
    """Parse the 3-column TSV (JobID, Title, Description) for jobs in ``keep_job_ids``.

    The Description field contains embedded ``\\r\\n`` and ``<BR>`` HTML but the
    file has no quote characters, so we parse with ``quoting=QUOTE_NONE`` (mirrors
    how ``careerbuilder_loader`` reads this very file in chunks). Stray bad lines
    are warned + skipped. Returns ``{job_id: (title, description)}``; jobs not in
    ``keep_job_ids`` are dropped.
    """
    if not jobs_path.exists():
        raise FileNotFoundError(
            f"jobs_filtered.tsv not found at {jobs_path}. "
            "Build it first (loader's hetero pre-filter writes kept jobs only)."
        )

    out: dict[int, tuple[str, str]] = {}
    t0 = time.time()
    n_rows = 0
    reader = pd.read_csv(
        jobs_path,
        sep="\t",
        encoding="ISO-8859-1",
        usecols=["JobID", "Title", "Description"],
        on_bad_lines="warn",
        quoting=csv.QUOTE_NONE,
        dtype={"JobID": "Int64"},
        low_memory=False,
        chunksize=50_000,
    )
    for chunk in reader:
        chunk = chunk.dropna(subset=["JobID"])
        # Filter to the jobs that survived k-core (much smaller than the file).
        chunk = chunk[chunk["JobID"].isin(keep_job_ids)]
        for jid, title, desc in zip(
            chunk["JobID"].tolist(),
            chunk["Title"].tolist(),
            chunk["Description"].tolist(),
        ):
            jid = int(jid)
            title = str(title) if pd.notna(title) else ""
            desc = str(desc) if pd.notna(desc) else ""
            out[jid] = (title, desc)
            n_rows += 1
    logger.info(
        "jobs_filtered.tsv: matched %d / %d kept jobs with text in %.1fs",
        len(out), len(keep_job_ids), time.time() - t0,
    )
    return out


# ---------------------------------------------------------------------------
# CB12 -> CVData / JobData / LabeledPair (the content schema)
# ---------------------------------------------------------------------------


def build_schema_objects(
    ds,
    job_text_map: dict[int, tuple[str, str]],
    alias_to_canonical: dict[str, str],
    compiled_patterns: list,
):
    """Convert the CB12 dataset (index space) into CONTENT-schema objects.

    cv_id == user_idx and job_id == job_idx so the LabeledPairs align 1:1 with the
    split's (user_idx, job_idx) tuples. Returns (cvs, jobs, pairs, skill_catalog,
    stats).
    """
    split = ds.split
    num_users = split.num_users
    num_jobs = split.num_jobs
    idx_to_job_id = ds.idx_to_job_id  # job_idx -> real CB12 JobID

    # --- Job text + skills + seniority, per job index ------------------------
    job_title_by_idx: list[str] = [""] * num_jobs
    job_text_by_idx: list[str] = [""] * num_jobs
    job_skills_by_idx: list[tuple[str, ...]] = [()] * num_jobs
    job_sen_by_idx: list[SeniorityLevel] = [SeniorityLevel.MID] * num_jobs

    n_jobs_with_text = 0
    for jidx in range(num_jobs):
        real_jid = idx_to_job_id[jidx]
        title, desc = job_text_map.get(real_jid, ("", ""))
        if title or desc:
            n_jobs_with_text += 1
        job_title_by_idx[jidx] = title
        text = f"{title}. {desc[:DESC_MAX_CHARS]}".strip()
        job_text_by_idx[jidx] = text
        sk = sorted(
            B._extract_skills_from_text(text, alias_to_canonical, compiled_patterns)
        )
        job_skills_by_idx[jidx] = tuple(sk)
        sen_name = _parse_seniority_from_title(title)
        job_sen_by_idx[jidx] = _SENIORITY_NAME_TO_ENUM.get(sen_name, SeniorityLevel.MID)

    jobs: list[JobData] = []
    for jidx in range(num_jobs):
        sk = job_skills_by_idx[jidx]
        jobs.append(
            JobData(
                job_id=jidx,
                seniority=job_sen_by_idx[jidx],
                skills=sk,
                skill_importances=tuple(3 for _ in sk),
                salary_min=0,
                salary_max=0,
                text=job_text_by_idx[jidx],
                experience_min=0.0,
                experience_max=None,
                role_category="",
            )
        )

    # --- User pseudo-resume = Titles of jobs they applied to in TRAIN --------
    train_jobs_by_user: dict[int, list[int]] = {}
    for u, j in split.train_pairs:
        train_jobs_by_user.setdefault(u, []).append(j)

    cvs: list[CVData] = []
    for uidx in range(num_users):
        applied = train_jobs_by_user.get(uidx, [])
        titles = [job_title_by_idx[j] for j in applied if job_title_by_idx[j]]
        # Cap length so the pseudo-resume stays embeddable.
        user_text = ". ".join(titles[:USER_TEXT_MAX_TITLES]).strip()
        sk = sorted(
            B._extract_skills_from_text(user_text, alias_to_canonical, compiled_patterns)
        )
        cvs.append(
            CVData(
                cv_id=uidx,
                seniority=SeniorityLevel.MID,
                experience_years=0.0,
                education=EducationLevel.BACHELOR,
                skills=tuple(sk),
                skill_proficiencies=tuple(3 for _ in sk),
                text=user_text,
            )
        )

    # --- LabeledPairs from the split (all positives, implicit feedback) ------
    pairs: list[LabeledPair] = []
    for u, j in split.train_pairs:
        pairs.append(LabeledPair(cv_id=u, job_id=j, label=1, split="train"))
    for u, j in split.val_pairs:
        pairs.append(LabeledPair(cv_id=u, job_id=j, label=1, split="val"))
    for u, j in split.test_pairs:
        pairs.append(LabeledPair(cv_id=u, job_id=j, label=1, split="test"))

    # --- Skill catalog = union of all extracted skills -> default category ---
    all_skills: set[str] = set()
    for c in cvs:
        all_skills.update(c.skills)
    for j in jobs:
        all_skills.update(j.skills)
    skill_catalog: dict[str, SkillCategory] = {
        s: DEFAULT_SKILL_CAT for s in sorted(all_skills)
    }

    stats = {
        "num_users": num_users,
        "num_jobs": num_jobs,
        "num_jobs_with_text": n_jobs_with_text,
        "num_users_with_text": sum(1 for c in cvs if c.text),
        "num_train_pairs": len(split.train_pairs),
        "num_val_pairs": len(split.val_pairs),
        "num_test_pairs": len(split.test_pairs),
        "num_pairs": len(pairs),
        "num_skills": len(skill_catalog),
    }
    return cvs, jobs, pairs, skill_catalog, stats


# ---------------------------------------------------------------------------
# GNN: reuse B.run_gnn, but feed CB12's REAL val split.
# ---------------------------------------------------------------------------
#
# B.run_gnn re-carves ~10% of the TRAIN positives as validation (CB12 already has
# a leave-one-out val split). To use the dataset's real val pairs as the GNN's
# early-stopping signal — and avoid pulling test-adjacent train positives out of
# the graph — we relabel CB12's "val" pairs in-place to split="train" so they
# become graph edges, then let B.run_gnn carve its own 10% val from that combined
# train. (Folding val INTO train is harmless: in leave-one-out, val is just the
# 2nd-most-recent application; including it as a message-passing edge only helps.)
#
# Rationale for NOT forking B.run_gnn: its train/test idx-mapping, GraphBuilder
# call, TrainConfig, and metric normalization are exactly what we want and what
# keeps this comparable to the resume-JD numbers. The only CB12-specific concern
# (an explicit val split) is satisfied by feeding those pairs as train edges.


def run_gnn_cb12(cvs, jobs, pairs, skill_catalog, embed, **kw) -> dict[str, float]:
    """Thin wrapper: fold CB12 val pairs into train, then defer to B.run_gnn.

    B.run_gnn keys off ``p.split`` ("train"/"test") and carves its own val from
    train. CB12's standalone val positives are remapped to "train" so they (a)
    become graph apply-edges and (b) feed B.run_gnn's internal val carve. Test
    pairs are passed through untouched.
    """
    remapped: list[LabeledPair] = []
    for p in pairs:
        split = "train" if p.split == "val" else p.split
        remapped.append(
            LabeledPair(cv_id=p.cv_id, job_id=p.job_id, label=p.label, split=split)
        )
    # B.run_gnn signature:
    #   run_gnn(cvs, jobs, pairs, skill_catalog, embed, *, seed, max_epochs,
    #           patience, hidden, num_layers, lr, weight_decay) -> metrics dict
    return B.run_gnn(cvs, jobs, remapped, skill_catalog, embed, **kw)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subsample-users", type=int, default=50_000)
    parser.add_argument("--k-core", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--embedding", type=str, default="english",
        help="Embedding provider name (default 'english'; 'multilingual' is a "
             "placeholder that falls back to 'english').",
    )
    parser.add_argument("--max-epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--mlp-epochs", type=int, default=50)
    parser.add_argument(
        "--smoke", action="store_true",
        help="Small subsample (~3000 users) for a fast end-to-end test.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=_BACKEND_DIR / "results" / "cb12_content" / "benchmark.json",
    )
    args = parser.parse_args()

    subsample_users = 3_000 if args.smoke else args.subsample_users

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    t_start = time.time()

    # 1. Embedding provider (with fallback to 'english').
    embed = B.make_embedding_provider(args.embedding)

    # 2. Skill extraction engine (shared alias index + compiled patterns).
    alias_to_canonical, compiled_patterns = B._build_skill_engine()

    # 3. Load CB12 (index space + apply pairs as leave-one-out splits).
    logger.info(
        "Loading CB12 (subsample_users=%d, k_core=%d, seed=%d) ...",
        subsample_users, args.k_core, args.seed,
    )
    ds = load_careerbuilder_12(
        cache_dir=CACHE_DIR,
        subsample_users=subsample_users,
        k_core=args.k_core,
        seed=args.seed,
        include_hetero=False,   # we build content via the CVData/JobData schema
    )

    # 4. Parse job text for the jobs that survived k-core.
    keep_job_ids = set(ds.idx_to_job_id)
    job_text_map = load_job_text_map(JOBS_FILTERED, keep_job_ids)

    # 5. Build content-schema objects (cv_id=user_idx, job_id=job_idx).
    cvs, jobs, pairs, skill_catalog, stats = build_schema_objects(
        ds, job_text_map, alias_to_canonical, compiled_patterns
    )
    logger.info("Dataset stats: %s", stats)

    # 5b. Precompute embeddings ONCE for ALL users + jobs (batched). Shared by the
    #     SBERT-cosine and MLP scorers so neither re-encodes per (cv, job) pair.
    cv_emb, job_emb = B.build_embedding_cache(embed, cvs, jobs, batch_size=256)

    # For BM25/MLP fit, restrict to entities seen in TRAIN positives.
    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    train_cv_ids = {p.cv_id for p in train_pos}
    train_job_ids = {p.job_id for p in train_pos}
    train_cvs = [c for c in cvs if c.cv_id in train_cv_ids]
    train_jobs = [j for j in jobs if j.job_id in train_job_ids]

    results: dict[str, dict[str, float]] = {}

    # 6. Baselines — all share the SAME cvs/jobs/pairs through B.run_baseline.
    #    NOTE: B.run_baseline groups by split ("train" excluded per-user, "test"
    #    held out). CB12 "val" pairs are not used by the baselines (val=[] inside
    #    run_baseline) — consistent with the GNN folding val into train.
    logger.info("Eval: Random")
    results["Random"] = B.run_baseline(B.RandomScorer(seed=args.seed), cvs, jobs, pairs)

    logger.info("Eval: Rule-Based (skill overlap)")
    results["Rule-Based (skill overlap)"] = B.run_baseline(
        B.SkillOverlapScorer(), cvs, jobs, pairs
    )

    logger.info("Eval: BM25")
    bm25 = B.BM25Scorer().fit(train_cvs if train_cvs else cvs)
    results["BM25"] = B.run_baseline(bm25, cvs, jobs, pairs)

    logger.info("Eval: SBERT (cosine)")
    results["SBERT (cosine)"] = B.run_baseline(
        B.CachedCosineScorer(cv_emb, job_emb), cvs, jobs, pairs
    )

    logger.info("Eval: MLP")
    mlp = B.MLPScorer(
        cv_emb, job_emb, dim=int(embed.dim), seed=args.seed, epochs=args.mlp_epochs
    )
    # CB12 is implicit feedback: only positives exist. MLPScorer.fit samples no
    # negatives itself, so it trains as a 1-class regressor toward 1.0 — weak but
    # included for parity with the resume-JD table (which has labelled negatives).
    train_pairs_all = [p for p in pairs if p.split == "train"]
    mlp.fit(
        train_cvs if train_cvs else cvs,
        train_jobs if train_jobs else jobs,
        train_pairs_all,
    )
    results["MLP"] = B.run_baseline(mlp, cvs, jobs, pairs)

    # 7. GNN (Ours) — warm-start collaborative graph + content-dim node features.
    logger.info("Eval: HeteroGraphSAGE (Ours)")
    results["HeteroGraphSAGE (Ours)"] = run_gnn_cb12(
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

    # 8. Print + persist.
    B.print_table(results)

    output = {
        "dataset": DATASET_NAME,
        "task": "per-user full-ranking (warm-start, implicit apply feedback)",
        "smoke": args.smoke,
        "embedding_requested": args.embedding,
        "embedding_dim": int(embed.dim),
        "ks": list(KS),
        "metrics": METRIC_COLS,
        "stats": stats,
        "config": {
            "subsample_users": subsample_users,
            "k_core": args.k_core,
            "seed": args.seed,
            "max_epochs": args.max_epochs,
            "patience": args.patience,
            "hidden": args.hidden,
            "num_layers": args.num_layers,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "mlp_epochs": args.mlp_epochs,
            "desc_max_chars": DESC_MAX_CHARS,
            "user_text_max_titles": USER_TEXT_MAX_TITLES,
        },
        "results": results,
        "wall_time_seconds": round(elapsed, 2),
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
            "numpy": np.__version__,
        },
        "note": (
            "LightGCN not run here (ID-only CF baseline; cite from prior CB12 "
            "bipartite run). GNN node features are learned ID embeddings over the "
            "warm-start apply graph (train_generic replaces .x with learnable "
            "tables); content text powers BM25/SBERT/MLP and fixes the GNN "
            "embedding-table dimension."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Wrote results to %s (%.1fs)", args.output, elapsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
