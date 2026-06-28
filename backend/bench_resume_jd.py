"""Benchmark several models on `cnamuangtoun/resume-job-description-fit` as a
per-resume RANKING task, reusing the `ml_benchmark` package.

One comparison table over the SAME cvs / jobs / split:
  Methods (rows):  Random, Rule-Based (skill overlap), BM25, SBERT (cosine),
                   MLP, HeteroGraphSAGE (Ours)
  Metrics (cols):  Recall@{5,10,20}, NDCG@{5,10,20}, MRR
  Protocol:        per-resume full-ranking over the job pool, macro-averaged
                   over test resumes with >= 1 Good-Fit.

Positive = label == "Good Fit"; everything else is negative.

Usage (from backend/):
    # fast end-to-end smoke (subsamples ~60 resumes)
    python bench_resume_jd.py --smoke
    # full run
    python bench_resume_jd.py --seed 42 --embedding multilingual --max-epochs 300

Writes results JSON to results/resume_jd/benchmark.json and prints a table.
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

# Pre-warm heavy libs BEFORE django.setup (mirrors scripts/train_careerbuilder.py).
import sklearn.metrics.pairwise  # noqa: F401  pre-warm
import torch_geometric  # noqa: F401  pre-load

import numpy as np
import torch

from ml_benchmark.baselines.base import Scorer
from ml_benchmark.baselines.bm25 import BM25Scorer
from ml_benchmark.baselines.skill_overlap import SkillOverlapScorer
from ml_benchmark.data.careerbuilder_loader import (
    _build_skill_keyword_index,
    _compile_skill_patterns,
    _extract_skills_from_text,
)
from ml_benchmark.embedding import get_provider
from ml_benchmark.embedding.base import EmbeddingProvider
from ml_benchmark.evaluation.per_cv_evaluator import PerCVEvaluator
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
logger = logging.getLogger("bench_resume_jd")

DATASET_NAME = "cnamuangtoun/resume-job-description-fit"
KS = (5, 10, 20)
METRIC_COLS = [f"recall@{k}" for k in KS] + [f"ndcg@{k}" for k in KS] + ["mrr"]
DEFAULT_SKILL_CAT = SkillCategory.TECHNICAL  # single default category for all skills


# ---------------------------------------------------------------------------
# Embedding provider (multilingual placeholder is not implemented → english)
# ---------------------------------------------------------------------------


def make_embedding_provider(name: str) -> EmbeddingProvider:
    """Return the requested provider; fall back to 'english' if it errors.

    Note: as of this repo the 'multilingual' provider is a placeholder that
    raises NotImplementedError, so the practical fallback is 'english'
    (all-MiniLM-L6-v2, 384-dim). Both produce 384-dim vectors so node-feature
    and MLP input dims stay consistent.
    """
    try:
        provider = get_provider(name)
        # Probe so a lazy NotImplementedError surfaces here, not deep in build().
        _ = provider.encode(["probe"])
        logger.info("Embedding provider: %s (dim=%d)", name, provider.dim)
        return provider
    except Exception as exc:  # noqa: BLE001  (NotImplementedError is a subclass)
        if name == "english":
            raise
        logger.warning(
            "Embedding provider %r unavailable (%s); falling back to 'english'.",
            name, exc,
        )
        provider = get_provider("english")
        _ = provider.encode(["probe"])
        logger.info("Embedding provider: english (dim=%d)", provider.dim)
        return provider


# ---------------------------------------------------------------------------
# Embedding cache (compute ONCE, reuse for cosine + MLP)
# ---------------------------------------------------------------------------


def _encode_batched(
    embed: EmbeddingProvider, texts: list[str], batch_size: int = 256
) -> np.ndarray:
    """Encode texts in batches of `batch_size`, returning an (N, dim) float32 array."""
    if not texts:
        return np.zeros((0, int(embed.dim)), dtype=np.float32)
    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        chunks.append(np.asarray(embed.encode(batch), dtype=np.float32))
    return np.concatenate(chunks, axis=0)


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    """L2-normalize rows; zero-norm rows stay zero (cosine with them = 0)."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return mat / norms


def build_embedding_cache(
    embed: EmbeddingProvider,
    cvs: list[CVData],
    jobs: list[JobData],
    *,
    batch_size: int = 256,
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Precompute L2-normalized embeddings ONCE for all CVs and Jobs.

    A handful of batched ``embed.encode([...])`` calls instead of one encode per
    (cv, job) pair. Returns ``(cv_emb, job_emb)`` mapping id -> normalized vector
    so cosine similarity is a plain dot product at score time.
    """
    t0 = time.time()
    cv_mat = _l2_normalize(_encode_batched(embed, [c.text for c in cvs], batch_size))
    job_mat = _l2_normalize(_encode_batched(embed, [j.text for j in jobs], batch_size))
    cv_emb = {c.cv_id: cv_mat[i] for i, c in enumerate(cvs)}
    job_emb = {j.job_id: job_mat[i] for i, j in enumerate(jobs)}
    logger.info(
        "Embedding cache: %d CVs + %d jobs encoded (batch=%d) in %.1fs",
        len(cvs), len(jobs), batch_size, time.time() - t0,
    )
    return cv_emb, job_emb


# ---------------------------------------------------------------------------
# New scorers
# ---------------------------------------------------------------------------


class RandomScorer(Scorer):
    """Deterministic pseudo-random score in [0, 1) seeded by (seed, cv_id, job_id)."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def score(self, cv: CVData, job: JobData) -> float:
        # Stable across runs: derive a per-pair RNG from the seed + ids.
        rng = np.random.RandomState((self._seed * 1_000_003 + cv.cv_id * 1009 + job.job_id) % (2**32))
        return float(rng.random())


class CachedCosineScorer(Scorer):
    """SBERT cosine via PRECOMPUTED, L2-normalized embeddings.

    Embeddings are encoded once up-front (see ``build_embedding_cache``); cosine
    similarity is then a plain dot product of the two unit vectors — no encoding
    at score time, so the per-CV full-ranking eval is O(N²) dot products, not
    O(N²) encodes.
    """

    def __init__(self, cv_emb: dict[int, np.ndarray], job_emb: dict[int, np.ndarray]) -> None:
        self._cv_emb = cv_emb
        self._job_emb = job_emb

    def score(self, cv: CVData, job: JobData) -> float:
        return float(self._cv_emb[cv.cv_id] @ self._job_emb[job.job_id])


class MLPScorer(Scorer):
    """2-layer MLP on concat([cv_emb, job_emb]) -> 1 logit (sigmoid prob).

    Trains on Good-Fit(=1)/else(=0) pairs with BCE. Reuses the SAME precomputed
    ``cv_emb``/``job_emb`` cache as the cosine baseline for BOTH training and
    ``.score()`` (look up by id, never re-encode).
    """

    def __init__(self, cv_emb: dict[int, np.ndarray], job_emb: dict[int, np.ndarray],
                 *, dim: int, seed: int = 42,
                 epochs: int = 50, lr: float = 1e-3, hidden: int = 128) -> None:
        self._cv_emb = cv_emb
        self._job_emb = job_emb
        self._dim = int(dim)
        self._seed = seed
        self._epochs = epochs
        self._lr = lr
        self._hidden = hidden
        self._device = torch.device("cpu")  # keep it CPU-ok / small
        self._model: torch.nn.Module | None = None

    def fit(self, train_cvs: list[CVData], train_jobs: list[JobData],
            train_pairs: list[LabeledPair]) -> "MLPScorer":
        torch.manual_seed(self._seed)
        np.random.seed(self._seed)

        # Use only pairs whose embeddings are present in the shared cache.
        usable = [
            p for p in train_pairs
            if p.cv_id in self._cv_emb and p.job_id in self._job_emb
        ]

        if not usable:
            logger.warning("MLPScorer.fit: no usable training pairs; model stays untrained.")
            return self

        dim = self._dim
        X = np.stack(
            [np.concatenate([self._cv_emb[p.cv_id], self._job_emb[p.job_id]]) for p in usable]
        ).astype(np.float32)
        y = np.array([1.0 if p.label == 1 else 0.0 for p in usable], dtype=np.float32)

        Xt = torch.from_numpy(X).to(self._device)
        yt = torch.from_numpy(y).to(self._device)

        model = torch.nn.Sequential(
            torch.nn.Linear(2 * dim, self._hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(self._hidden, 1),
        ).to(self._device)
        opt = torch.optim.Adam(model.parameters(), lr=self._lr)
        loss_fn = torch.nn.BCEWithLogitsLoss()

        model.train()
        for epoch in range(self._epochs):
            opt.zero_grad()
            logits = model(Xt).squeeze(-1)
            loss = loss_fn(logits, yt)
            loss.backward()
            opt.step()
        model.eval()
        self._model = model
        logger.info("MLPScorer fitted on %d pairs (%d pos) — final BCE=%.4f",
                    len(usable), int(y.sum()), float(loss.item()))
        return self

    def score(self, cv: CVData, job: JobData) -> float:
        if self._model is None:
            return 0.0
        # Pure cache lookup — embeddings were precomputed for ALL cvs/jobs.
        x = np.concatenate([self._cv_emb[cv.cv_id], self._job_emb[job.job_id]]).astype(np.float32)
        with torch.no_grad():
            logit = self._model(torch.from_numpy(x).unsqueeze(0).to(self._device)).item()
        return float(1.0 / (1.0 + np.exp(-logit)))


# ---------------------------------------------------------------------------
# Dataset → schema objects
# ---------------------------------------------------------------------------


def _build_skill_engine() -> tuple[dict[str, str], list]:
    """Return (alias_to_canonical, compiled_patterns) from the bundled skill-alias.json.

    Falls back to ml_service's skill-alias.json if the ml_benchmark copy is absent.
    """
    candidates = [
        _BACKEND_DIR / "ml_benchmark" / "data" / "skill-alias.json",
        _BACKEND_DIR / "ml_service" / "data" / "skill-alias.json",
        _BACKEND_DIR / "ml_service" / "skill-alias.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            f"No skill-alias.json found. Looked in: {[str(c) for c in candidates]}"
        )
    logger.info("Skill alias index: %s", path)
    alias_to_canonical, _canonicals = _build_skill_keyword_index(path)
    compiled = _compile_skill_patterns(alias_to_canonical)
    return alias_to_canonical, compiled


def load_resume_jd_rows(smoke: bool, seed: int):
    """Load HF dataset and return (rows, ) where each row has resume_text/job_description_text/label/split."""
    from datasets import load_dataset

    ds = load_dataset(DATASET_NAME)
    rows = []
    for split_name in ("train", "test"):
        if split_name not in ds:
            continue
        for r in ds[split_name]:
            rows.append(
                {
                    "resume_text": r["resume_text"],
                    "job_description_text": r["job_description_text"],
                    "label": r["label"],
                    "split": split_name,
                }
            )

    if smoke:
        # Subsample by RESUME so each kept resume keeps all its pairs (ranking needs
        # multiple pairs per resume). Keep ~60 resumes, biased to ones with a Good Fit.
        rng = random.Random(seed)
        by_resume: dict[str, list[dict]] = {}
        for r in rows:
            by_resume.setdefault(r["resume_text"], []).append(r)
        resumes = list(by_resume.keys())
        rng.shuffle(resumes)
        # prefer resumes that have at least one Good Fit so eval isn't empty
        def has_good(rt: str) -> bool:
            return any(x["label"] == "Good Fit" for x in by_resume[rt])
        resumes.sort(key=lambda rt: (not has_good(rt)))
        keep = set(resumes[:60])
        rows = [r for r in rows if r["resume_text"] in keep]
        logger.info("SMOKE: subsampled to %d resumes / %d rows", len(keep), len(rows))

    return rows


def build_schema_objects(rows, alias_to_canonical, compiled_patterns):
    """Map unique resume/JD text -> ids, build CVData/JobData/LabeledPair lists.

    Returns:
        cvs, jobs, pairs, skill_catalog, stats(dict)
    """
    # Stable id assignment over BOTH splits (first-seen order).
    resume_to_id: dict[str, int] = {}
    jd_to_id: dict[str, int] = {}
    for r in rows:
        if r["resume_text"] not in resume_to_id:
            resume_to_id[r["resume_text"]] = len(resume_to_id)
        if r["job_description_text"] not in jd_to_id:
            jd_to_id[r["job_description_text"]] = len(jd_to_id)

    # --- skills per unique resume / jd ---
    cv_skills: dict[int, list[str]] = {}
    for text, cid in resume_to_id.items():
        sk = sorted(_extract_skills_from_text(text, alias_to_canonical, compiled_patterns))
        cv_skills[cid] = sk
    job_skills: dict[int, list[str]] = {}
    for text, jid in jd_to_id.items():
        sk = sorted(_extract_skills_from_text(text, alias_to_canonical, compiled_patterns))
        job_skills[jid] = sk

    # --- CVData per unique resume ---
    cvs: list[CVData] = []
    for text, cid in resume_to_id.items():
        sk = tuple(cv_skills[cid])
        cvs.append(
            CVData(
                cv_id=cid,
                seniority=SeniorityLevel.MID,         # sensible default
                experience_years=0.0,                  # sensible default
                education=EducationLevel.BACHELOR,     # sensible default
                skills=sk,
                skill_proficiencies=tuple(3 for _ in sk),  # mid proficiency
                text=text,
            )
        )
    cvs.sort(key=lambda c: c.cv_id)

    # --- JobData per unique JD ---
    jobs: list[JobData] = []
    for text, jid in jd_to_id.items():
        sk = tuple(job_skills[jid])
        jobs.append(
            JobData(
                job_id=jid,
                seniority=SeniorityLevel.MID,
                skills=sk,
                skill_importances=tuple(3 for _ in sk),
                salary_min=0,
                salary_max=0,
                text=text,
                experience_min=0.0,
                experience_max=None,
                role_category="",
            )
        )
    jobs.sort(key=lambda j: j.job_id)

    # --- skill catalog (union of all extracted skills) → default category ---
    all_skills: set[str] = set()
    for sk in cv_skills.values():
        all_skills.update(sk)
    for sk in job_skills.values():
        all_skills.update(sk)
    skill_catalog: dict[str, SkillCategory] = {s: DEFAULT_SKILL_CAT for s in sorted(all_skills)}

    # --- LabeledPairs: dedupe (cv_id, job_id); a test row makes the pair a test pair. ---
    # label = 1 iff "Good Fit". If a pair appears in both splits with conflicting
    # labels, keep label=1 if ANY occurrence is Good Fit (positive-dominant), and
    # split=test if ANY occurrence is in test (test rows define the test set).
    agg: dict[tuple[int, int], dict] = {}
    for r in rows:
        cid = resume_to_id[r["resume_text"]]
        jid = jd_to_id[r["job_description_text"]]
        key = (cid, jid)
        label = 1 if r["label"] == "Good Fit" else 0
        cur = agg.get(key)
        if cur is None:
            agg[key] = {"label": label, "split": r["split"]}
        else:
            cur["label"] = max(cur["label"], label)
            if r["split"] == "test":
                cur["split"] = "test"

    pairs: list[LabeledPair] = [
        LabeledPair(cv_id=cid, job_id=jid, label=v["label"], split=v["split"])
        for (cid, jid), v in agg.items()
    ]

    stats = {
        "num_unique_resumes": len(resume_to_id),
        "num_unique_jds": len(jd_to_id),
        "num_pairs": len(pairs),
        "num_pos_pairs": sum(1 for p in pairs if p.label == 1),
        "num_train_pairs": sum(1 for p in pairs if p.split == "train"),
        "num_test_pairs": sum(1 for p in pairs if p.split == "test"),
        "num_skills": len(skill_catalog),
    }
    return cvs, jobs, pairs, skill_catalog, stats


# ---------------------------------------------------------------------------
# GNN training (HeteroGraphSAGE) via train_generic
# ---------------------------------------------------------------------------


def run_gnn(
    cvs: list[CVData],
    jobs: list[JobData],
    pairs: list[LabeledPair],
    skill_catalog: dict[str, SkillCategory],
    embed: EmbeddingProvider,
    *,
    seed: int,
    max_epochs: int,
    patience: int,
    hidden: int,
    num_layers: int,
    lr: float,
    weight_decay: float,
) -> dict[str, float]:
    """Build hetero graph over ALL cvs/jobs (train positives as match edges only),
    train HeteroGraphSAGE via train_generic, return per-CV test metrics.

    Comparability note: train_generic's full-ranking eval excludes only TRAIN-seen
    jobs per CV (PerCVEvaluator excludes train+val). We therefore carve val from a
    small slice of train positives and DROP those carved pairs from neither — they
    are simply not used as graph edges or test, so the test job pool the GNN ranks
    over is essentially the full job catalog minus that CV's train-positive jobs,
    matching the baselines whose dataset_split.train holds the same train positives.
    """
    rng = random.Random(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)

    cv_id_to_idx = {c.cv_id: i for i, c in enumerate(cvs)}
    job_id_to_idx = {j.job_id: i for i, j in enumerate(jobs)}

    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    test_pos = [p for p in pairs if p.split == "test" and p.label == 1]

    # Carve ~10% of train positives as validation so early stopping has a signal.
    train_pos_shuffled = list(train_pos)
    rng.shuffle(train_pos_shuffled)
    n_val = max(1, int(0.10 * len(train_pos_shuffled))) if train_pos_shuffled else 0
    val_pos = train_pos_shuffled[:n_val]
    graph_train_pos = train_pos_shuffled[n_val:]

    # Graph match edges: ONLY train-split positives that remain after val carve-out.
    builder = GraphBuilder(embed)
    data = builder.build(cvs, jobs, skill_catalog, graph_train_pos)

    # train_generic expects idx-space (src_idx, dst_idx) tuples.
    def to_idx_pairs(plist: list[LabeledPair]) -> list[tuple[int, int]]:
        out = []
        for p in plist:
            ci = cv_id_to_idx.get(p.cv_id)
            ji = job_id_to_idx.get(p.job_id)
            if ci is not None and ji is not None:
                out.append((ci, ji))
        return out

    train_pairs_idx = to_idx_pairs(graph_train_pos)
    val_pairs_idx = to_idx_pairs(val_pos)
    test_pairs_idx = to_idx_pairs(test_pos)

    config = TrainConfig(
        model_type="graphsage",
        hidden_channels=hidden,
        num_layers=num_layers,
        lr=lr,
        weight_decay=weight_decay,
        epochs=max_epochs,
        patience=patience,
        seed=seed,
        use_node_features=True,  # content-aware: use SBERT/text node features (+ warm-start collaborative edges)
    )
    trainer = Trainer(config)
    result = trainer.train_generic(
        data=data,
        train_pairs=train_pairs_idx,
        val_pairs=val_pairs_idx,
        test_pairs=test_pairs_idx,
        src_type="cv",
        dst_type="job",
        num_src=len(cvs),
        num_dst=len(jobs),
        eval_at_k=KS,
    )

    tm = result.test_metrics or {}
    # train_generic emits recall@k / ndcg@k / hr@k / mrr — normalize to our columns.
    return {col: float(tm.get(col, 0.0)) for col in METRIC_COLS}


# ---------------------------------------------------------------------------
# Baseline evaluation
# ---------------------------------------------------------------------------


def run_baseline(
    scorer: Scorer,
    cvs: list[CVData],
    jobs: list[JobData],
    pairs: list[LabeledPair],
) -> dict[str, float]:
    """Per-CV full-ranking eval of a scorer over ALL jobs.

    dataset_split.train = train positives (excluded per-CV from ranking, mirroring
    the GNN's train-seen exclusion); val = []; test = test positives.
    """
    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    test_pos = [p for p in pairs if p.split == "test" and p.label == 1]
    split = DatasetSplit(train=train_pos, val=[], test=test_pos)
    evaluator = PerCVEvaluator(cvs, jobs, split, min_test_positives=1)
    res = evaluator.evaluate(scorer, ks=KS)
    return {col: float(res.avg_metrics.get(col, 0.0)) for col in METRIC_COLS}


# ---------------------------------------------------------------------------
# Table printing
# ---------------------------------------------------------------------------


def print_table(results: dict[str, dict[str, float]]) -> None:
    name_w = 26
    col_w = 12
    header = f"{'Method':<{name_w}}" + "".join(f"{c:>{col_w}}" for c in METRIC_COLS)
    width = name_w + col_w * len(METRIC_COLS)
    print("\n" + "=" * width)
    print(f"  Resume-JD Fit — per-resume full-ranking ({DATASET_NAME})")
    print("=" * width)
    print(header)
    print("-" * width)

    best: dict[str, str] = {}
    for c in METRIC_COLS:
        vals = [(name, m.get(c, 0.0)) for name, m in results.items()]
        if vals:
            best[c] = max(vals, key=lambda x: x[1])[0]

    for name, m in results.items():
        row = f"{name:<{name_w}}"
        for c in METRIC_COLS:
            v = m.get(c, 0.0)
            mark = "*" if best.get(c) == name else " "
            row += f"{v:>{col_w - 1}.4f}{mark}"
        print(row)
    print("=" * width)
    print("  * = best in column")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--embedding", type=str, default="multilingual",
                        help="Embedding provider name (falls back to 'english' if unavailable).")
    parser.add_argument("--max-epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--mlp-epochs", type=int, default=50)
    parser.add_argument(
        "--output",
        type=Path,
        default=_BACKEND_DIR / "results" / "resume_jd" / "benchmark.json",
    )
    parser.add_argument("--smoke", action="store_true",
                        help="Subsample ~60 resumes for a fast end-to-end test.")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    t_start = time.time()

    # 1. Embedding provider (with fallback).
    embed = make_embedding_provider(args.embedding)

    # 2. Skill extraction engine.
    alias_to_canonical, compiled_patterns = _build_skill_engine()

    # 3. Load dataset + build schema objects.
    rows = load_resume_jd_rows(smoke=args.smoke, seed=args.seed)
    cvs, jobs, pairs, skill_catalog, stats = build_schema_objects(
        rows, alias_to_canonical, compiled_patterns
    )
    logger.info("Dataset stats: %s", stats)

    # 3b. Precompute embeddings ONCE for ALL cvs + jobs (batched). Shared by the
    #     SBERT-cosine and MLP scorers so neither re-encodes per (cv, job) pair.
    cv_emb, job_emb = build_embedding_cache(embed, cvs, jobs, batch_size=256)

    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    train_cvs = [c for c in cvs if c.cv_id in {p.cv_id for p in train_pos}]
    train_jobs = [j for j in jobs if j.job_id in {p.job_id for p in train_pos}]

    results: dict[str, dict[str, float]] = {}

    # 4. Baselines (share the SAME cvs/jobs/split).
    logger.info("Eval: Random")
    results["Random"] = run_baseline(RandomScorer(seed=args.seed), cvs, jobs, pairs)

    logger.info("Eval: Rule-Based (skill overlap)")
    results["Rule-Based (skill overlap)"] = run_baseline(SkillOverlapScorer(), cvs, jobs, pairs)

    logger.info("Eval: BM25")
    bm25 = BM25Scorer().fit(train_cvs if train_cvs else cvs)
    results["BM25"] = run_baseline(bm25, cvs, jobs, pairs)

    logger.info("Eval: SBERT (cosine)")
    results["SBERT (cosine)"] = run_baseline(
        CachedCosineScorer(cv_emb, job_emb), cvs, jobs, pairs
    )

    logger.info("Eval: MLP")
    mlp = MLPScorer(cv_emb, job_emb, dim=int(embed.dim), seed=args.seed, epochs=args.mlp_epochs)
    # Fit on ALL train pairs (pos + neg) so BCE has both classes.
    train_pairs_all = [p for p in pairs if p.split == "train"]
    mlp.fit(train_cvs if train_cvs else cvs, train_jobs if train_jobs else jobs, train_pairs_all)
    results["MLP"] = run_baseline(mlp, cvs, jobs, pairs)

    # 5. GNN (Ours).
    logger.info("Eval: HeteroGraphSAGE (Ours)")
    results["HeteroGraphSAGE (Ours)"] = run_gnn(
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
    print_table(results)

    output = {
        "dataset": DATASET_NAME,
        "task": "per-resume full-ranking (Good Fit = positive)",
        "smoke": args.smoke,
        "embedding_requested": args.embedding,
        "embedding_dim": int(embed.dim),
        "ks": list(KS),
        "metrics": METRIC_COLS,
        "stats": stats,
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
            "torch_geometric": torch_geometric.__version__,
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
