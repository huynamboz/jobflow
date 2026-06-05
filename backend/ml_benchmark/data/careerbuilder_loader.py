"""CareerBuilder12 loader for ml_benchmark sandbox (feature 009).

Source: Kaggle dataset `jsrshivam/job-recommendation-case-study`.

Pipeline:
    1. Download CB12 via `kaggle datasets download` (idempotent, cached)
    2. Parse `apps.tsv` and `users.tsv` (jobs.tsv NOT required for bipartite —
       JobIDs derived from apps.tsv)
    3. Subsample 50K random users (seed=42) — full 390K too large for GPU budget
    4. K-core=10 iterative filter
    5. Leave-one-out split per user by ApplicationDate
    6. Build HeteroData (bipartite by default; hetero stretch with skill/seniority
       requires jobs.tsv full sync — TODO US2)

Output: `CareerbuilderDataset`.

Reuses Phase 2 (MovieLens) infrastructure pattern. Trainer.train_generic() is
called with src_type="user", dst_type="job".
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.data import HeteroData

logger = logging.getLogger(__name__)

KAGGLE_DATASET_ID = "jsrshivam/job-recommendation-case-study"
REQUIRED_FILES = ("apps.tsv", "users.tsv")    # jobs.tsv (3.4GB) only needed for hetero
REQUIRED_FILES_HETERO = ("apps.tsv", "users.tsv", "jobs.tsv")

# Seniority levels for hetero variant (mirrors ml_benchmark.graph.schema.SeniorityLevel
# but kept local to avoid JobFlow-specific enum dependency).
SENIORITY_LEVELS = ["intern", "junior", "mid", "senior", "lead", "manager"]
SENIORITY_DEFAULT = "mid"
_SENIORITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("intern",  re.compile(r"\b(intern|internship|trainee)\b", re.IGNORECASE)),
    ("manager", re.compile(r"\b(manager|director|vp|head of|chief)\b", re.IGNORECASE)),
    ("lead",    re.compile(r"\b(lead|principal|staff|architect)\b", re.IGNORECASE)),
    ("senior",  re.compile(r"\b(senior|sr\.|sr )\b", re.IGNORECASE)),
    ("junior",  re.compile(r"\b(junior|jr\.|jr |entry[- ]level|entry-level)\b", re.IGNORECASE)),
]


def _parse_seniority_from_title(title: str) -> str:
    """Return one of SENIORITY_LEVELS based on title regex; default 'mid'."""
    if not title:
        return SENIORITY_DEFAULT
    for level, pat in _SENIORITY_PATTERNS:
        if pat.search(title):
            return level
    return SENIORITY_DEFAULT


def _build_skill_keyword_index(skill_alias_path: Path) -> tuple[dict[str, str], list[str]]:
    """Load skill-alias.json → (alias_lower -> canonical_skill, canonical_list).

    Each alias is matched as a whole-word regex against job description text.
    Longer aliases are checked first to avoid 'java' matching inside 'javascript'.
    """
    with open(skill_alias_path, encoding="utf-8") as f:
        raw = json.load(f)
    alias_to_canonical: dict[str, str] = {}
    for canonical, info in raw["skills"].items():
        for alias in info.get("aliases", []) + [canonical]:
            alias_to_canonical[alias.lower()] = canonical
    canonicals = sorted(set(alias_to_canonical.values()))
    return alias_to_canonical, canonicals


def _extract_skills_from_text(text: str, alias_to_canonical: dict[str, str], compiled_patterns: list[tuple[re.Pattern, str]]) -> set[str]:
    """Whole-word regex match every alias in text → set of canonical skills."""
    if not text:
        return set()
    text_lower = text.lower()
    found: set[str] = set()
    for pat, canonical in compiled_patterns:
        if pat.search(text_lower):
            found.add(canonical)
    return found


def _compile_skill_patterns(alias_to_canonical: dict[str, str]) -> list[tuple[re.Pattern, str]]:
    """Compile one regex per alias, sort by length desc (longest first).

    We use word boundaries (\b) to avoid 'java' matching 'javascript'.
    """
    # Sort aliases longest first so 'react native' matches before 'react' would
    pairs = sorted(alias_to_canonical.items(), key=lambda x: -len(x[0]))
    compiled = []
    for alias, canonical in pairs:
        # Escape special chars; allow word boundary; case insensitive
        pat_str = r"\b" + re.escape(alias.lower()) + r"\b"
        try:
            compiled.append((re.compile(pat_str), canonical))
        except re.error:
            continue   # skip malformed
    return compiled


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass
class CareerbuilderSplit:
    train_pairs: list[tuple[int, int]]    # (user_idx, job_idx)
    val_pairs: list[tuple[int, int]]
    test_pairs: list[tuple[int, int]]
    num_users: int
    num_jobs: int
    num_skills: int = 0
    num_seniority: int = 0


@dataclass
class CareerbuilderDataset:
    data: HeteroData
    split: CareerbuilderSplit
    user_id_to_idx: dict[int, int]
    job_id_to_idx: dict[int, int]
    skill_to_idx: dict[str, int] = field(default_factory=dict)
    idx_to_user_id: list[int] = field(default_factory=list)
    idx_to_job_id: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_careerbuilder_12(cache_dir: Path | str = "Dataset/careerbuilder-12") -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if all((cache_dir / f).exists() for f in REQUIRED_FILES):
        logger.info("Using cached CareerBuilder12 at %s", cache_dir)
        return cache_dir

    if shutil.which("kaggle") is None:
        raise RuntimeError(
            "kaggle CLI not found; install with `pip install kaggle` and configure ~/.kaggle/kaggle.json"
        )

    logger.info("Downloading CareerBuilder12 from Kaggle (%s) ...", KAGGLE_DATASET_ID)
    proc = subprocess.run(
        ["kaggle", "datasets", "download", "-d", KAGGLE_DATASET_ID, "--unzip", "-p", str(cache_dir)],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Kaggle download failed: {proc.stderr}")

    for f in REQUIRED_FILES:
        if not (cache_dir / f).exists():
            raise RuntimeError(f"Download OK but missing required file: {cache_dir / f}")
    logger.info("CareerBuilder12 ready at %s", cache_dir)
    return cache_dir


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_apps(apps_path: Path) -> pd.DataFrame:
    # Schema: UserID, WindowID, Split, ApplicationDate, JobID
    df = pd.read_csv(
        apps_path,
        sep="\t",
        encoding="ISO-8859-1",
        usecols=["UserID", "JobID", "ApplicationDate"],
        on_bad_lines="warn",
        low_memory=False,
    )
    # Convert types defensively
    df["UserID"] = pd.to_numeric(df["UserID"], errors="coerce")
    df["JobID"] = pd.to_numeric(df["JobID"], errors="coerce")
    df["ApplicationDate"] = pd.to_datetime(df["ApplicationDate"], errors="coerce")
    df = df.dropna(subset=["UserID", "JobID", "ApplicationDate"])
    df["UserID"] = df["UserID"].astype(np.int64)
    df["JobID"] = df["JobID"].astype(np.int64)
    return df


def _parse_user_ids(users_path: Path) -> np.ndarray:
    # Only need UserID column to subsample
    df = pd.read_csv(
        users_path,
        sep="\t",
        encoding="ISO-8859-1",
        usecols=["UserID"],
        on_bad_lines="warn",
        low_memory=False,
    )
    df["UserID"] = pd.to_numeric(df["UserID"], errors="coerce").dropna().astype(np.int64)
    return df["UserID"].unique()


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def _k_core_filter(
    interactions: list[tuple[int, int, pd.Timestamp]],
    k: int,
) -> list[tuple[int, int, pd.Timestamp]]:
    # Iterative bipartite k-core; identical Phase 2 R5.
    iteration = 0
    while True:
        iteration += 1
        user_deg: Counter = Counter()
        job_deg: Counter = Counter()
        for u, j, _ in interactions:
            user_deg[u] += 1
            job_deg[j] += 1
        new = [(u, j, ts) for u, j, ts in interactions
               if user_deg[u] >= k and job_deg[j] >= k]
        logger.info("  k-core iter %d: %d → %d interactions", iteration, len(interactions), len(new))
        if len(new) == len(interactions):
            return new
        interactions = new


def _leave_one_out_split(
    interactions: list[tuple[int, int, pd.Timestamp]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    by_user: dict[int, list[tuple[int, pd.Timestamp]]] = {}
    for u, j, ts in interactions:
        by_user.setdefault(u, []).append((j, ts))

    train, val, test = [], [], []
    for u, items in by_user.items():
        items.sort(key=lambda x: x[1])
        if len(items) < 3:
            train.extend((u, j) for j, _ in items)
            continue
        test.append((u, items[-1][0]))
        val.append((u, items[-2][0]))
        train.extend((u, j) for j, _ in items[:-2])
    return train, val, test


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def load_careerbuilder_12(
    cache_dir: Path | str = "Dataset/careerbuilder-12",
    *,
    subsample_users: Optional[int] = 50_000,
    subsample_seed: int = 42,
    min_user_apps: int = 5,
    k_core: int = 10,
    hidden_channels: int = 64,
    include_hetero: bool = False,
    seed: int = 42,
) -> CareerbuilderDataset:
    """Load CB12 dataset.

    Important: CB12 is much sparser than MovieLens (p50=2 apps/user).
    Strategy: pre-filter users with >= `min_user_apps` (default 5), then
    randomly subsample `subsample_users` of them, then apply k-core=`k_core`.
    Without min_user_apps filter, random 50K of 321K users mostly land on
    inactive users (p50=2) and k-core collapses to empty.
    """
    cache = download_careerbuilder_12(cache_dir)

    if include_hetero:
        jobs_path = cache / "jobs.tsv"
        jobs_filtered_path = cache / "jobs_filtered.tsv"
        if not jobs_path.exists() and not jobs_filtered_path.exists():
            raise RuntimeError(
                f"hetero variant requires jobs.tsv (3.4GB) or jobs_filtered.tsv (pre-filtered to kept jobs) in {cache}"
            )

    logger.info("Parsing apps.tsv ...")
    apps_df = _parse_apps(cache / "apps.tsv")
    logger.info("  loaded %d apps from %d users × %d jobs",
                len(apps_df), apps_df["UserID"].nunique(), apps_df["JobID"].nunique())

    # Pre-filter users with >= min_user_apps (paper-standard practice for sparse data)
    user_app_count = apps_df.groupby("UserID").size()
    active_users = user_app_count[user_app_count >= min_user_apps].index
    logger.info("  active users (>= %d apps): %d / %d",
                min_user_apps, len(active_users), apps_df["UserID"].nunique())

    if subsample_users is not None and len(active_users) > subsample_users:
        rng = np.random.default_rng(subsample_seed)
        sampled = rng.choice(active_users.values, size=subsample_users, replace=False)
        sampled_set = set(int(u) for u in sampled)
        logger.info("  subsampled to %d active users (seed=%d)", subsample_users, subsample_seed)
    else:
        sampled_set = set(int(u) for u in active_users)
        logger.info("  using all %d active users", len(sampled_set))

    apps_df = apps_df[apps_df["UserID"].isin(sampled_set)]
    logger.info("  filtered to subsampled active users: %d apps", len(apps_df))

    # Convert to list of (user, job, ts) tuples
    interactions = list(zip(
        apps_df["UserID"].tolist(),
        apps_df["JobID"].tolist(),
        apps_df["ApplicationDate"].tolist(),
    ))
    del apps_df  # free memory

    logger.info("Applying k-core filter (k=%d) ...", k_core)
    filtered = _k_core_filter(interactions, k_core)
    if not filtered:
        raise RuntimeError(f"k-core={k_core} produced empty interaction set (try lower k or larger subsample)")

    # Build dense idx mapping
    all_users = sorted({u for u, _, _ in filtered})
    all_jobs = sorted({j for _, j, _ in filtered})
    user_id_to_idx = {uid: i for i, uid in enumerate(all_users)}
    job_id_to_idx = {jid: i for i, jid in enumerate(all_jobs)}
    num_users = len(all_users)
    num_jobs = len(all_jobs)
    logger.info("  after k-core: %d users, %d jobs, %d interactions",
                num_users, num_jobs, len(filtered))

    # Convert to indexed
    indexed = [
        (user_id_to_idx[u], job_id_to_idx[j], ts)
        for u, j, ts in filtered
    ]

    logger.info("Building leave-one-out split per user ...")
    train, val, test = _leave_one_out_split(indexed)
    logger.info("  train=%d val=%d test=%d", len(train), len(val), len(test))

    # ---------------------------- Build HeteroData ----------------------------
    data = HeteroData()
    user_x = torch.empty(num_users, hidden_channels)
    job_x = torch.empty(num_jobs, hidden_channels)
    nn.init.xavier_uniform_(user_x)
    nn.init.xavier_uniform_(job_x)
    data["user"].x = user_x
    data["job"].x = job_x
    data["user"].num_nodes = num_users
    data["job"].num_nodes = num_jobs

    # Edges: only train pairs (avoid leak)
    train_arr = np.asarray(train, dtype=np.int64).T
    if train_arr.size == 0:
        raise RuntimeError("Empty train set after split")
    data["user", "applied", "job"].edge_index = torch.from_numpy(train_arr).long()

    # ---------------------------- Hetero variant: skill + seniority nodes ----------------------------
    skill_to_idx: dict[str, int] = {}
    num_skills = 0
    num_seniority = 0
    if include_hetero:
        logger.info("Hetero variant: parsing jobs.tsv for skill + seniority extraction ...")
        kept_job_ids = set(all_jobs)
        skill_alias_path = Path(__file__).parent / "skill-alias.json"
        alias_to_canonical, canonicals = _build_skill_keyword_index(skill_alias_path)
        compiled_patterns = _compile_skill_patterns(alias_to_canonical)
        logger.info("  loaded %d canonical skills, %d alias patterns",
                    len(canonicals), len(compiled_patterns))

        # Stream parse jobs.tsv (or pre-filtered jobs_filtered.tsv) for kept jobs only
        jobs_file = cache / "jobs_filtered.tsv" if (cache / "jobs_filtered.tsv").exists() else cache / "jobs.tsv"
        logger.info("  reading job metadata from %s", jobs_file.name)
        job_skills: dict[int, set[str]] = {}
        job_seniority: dict[int, str] = {}
        chunks = pd.read_csv(
            jobs_file,
            sep="\t",
            encoding="ISO-8859-1",
            usecols=["JobID", "Title", "Description"],
            on_bad_lines="warn",
            low_memory=False,
            chunksize=50_000,
            dtype={"JobID": "Int64"},
        )
        n_processed = 0
        for chunk in chunks:
            chunk = chunk.dropna(subset=["JobID"])
            chunk = chunk[chunk["JobID"].isin(kept_job_ids)]
            for _, row in chunk.iterrows():
                jid = int(row["JobID"])
                title = str(row.get("Title", "")) if pd.notna(row.get("Title")) else ""
                desc = str(row.get("Description", "")) if pd.notna(row.get("Description")) else ""
                blob = f"{title} {desc}"
                skills = _extract_skills_from_text(blob, alias_to_canonical, compiled_patterns)
                if skills:
                    job_skills[jid] = skills
                job_seniority[jid] = _parse_seniority_from_title(title)
                n_processed += 1
        logger.info("  parsed %d jobs from jobs.tsv (%d w/ extracted skill)", n_processed, len(job_skills))

        # Build skill node space (only canonicals that actually appear)
        used_skills = sorted({s for ss in job_skills.values() for s in ss})
        skill_to_idx = {s: i for i, s in enumerate(used_skills)}
        num_skills = len(used_skills)
        num_seniority = len(SENIORITY_LEVELS)
        logger.info("  hetero nodes: %d skill × %d seniority", num_skills, num_seniority)

        # Skill + Seniority node features (xavier init)
        if num_skills > 0:
            skill_x = torch.empty(num_skills, hidden_channels)
            nn.init.xavier_uniform_(skill_x)
            data["skill"].x = skill_x
            data["skill"].num_nodes = num_skills
        sen_x = torch.empty(num_seniority, hidden_channels)
        nn.init.xavier_uniform_(sen_x)
        data["seniority"].x = sen_x
        data["seniority"].num_nodes = num_seniority

        # job -> skill edges
        if num_skills > 0:
            js_pairs: list[tuple[int, int]] = []
            for jid_raw, skills in job_skills.items():
                if jid_raw not in job_id_to_idx:
                    continue
                jidx = job_id_to_idx[jid_raw]
                for s in skills:
                    js_pairs.append((jidx, skill_to_idx[s]))
            if js_pairs:
                js_arr = np.asarray(js_pairs, dtype=np.int64).T
                data["job", "requires_skill", "skill"].edge_index = torch.from_numpy(js_arr).long()
                logger.info("  job→skill edges: %d", len(js_pairs))

        # job -> seniority edges (1 per job)
        sen_to_idx = {lvl: i for i, lvl in enumerate(SENIORITY_LEVELS)}
        jsen_pairs: list[tuple[int, int]] = []
        for jid_raw, lvl in job_seniority.items():
            if jid_raw not in job_id_to_idx:
                continue
            jsen_pairs.append((job_id_to_idx[jid_raw], sen_to_idx[lvl]))
        if jsen_pairs:
            jsen_arr = np.asarray(jsen_pairs, dtype=np.int64).T
            data["job", "requires_seniority", "seniority"].edge_index = torch.from_numpy(jsen_arr).long()
            logger.info("  job→seniority edges: %d", len(jsen_pairs))

    # ---------------------------- Invariants (defensive asserts) ----------------------------
    user_total = Counter(u for u, _ in train) + Counter(u for u, _ in val) + Counter(u for u, _ in test)
    if user_total:
        min_inter = min(user_total.values())
        assert min_inter >= k_core, f"R-INV-1 violated: user has only {min_inter} inter, expected >= {k_core}"
    assert data["user", "applied", "job"].edge_index.shape[1] == len(train), "R-INV-5 violated"
    train_set = set(train)
    assert not any(p in train_set for p in val), "R-INV-6 violated (val leaks into train)"
    assert not any(p in train_set for p in test), "R-INV-6 violated (test leaks into train)"
    assert all(0 <= u < num_users and 0 <= j < num_jobs for u, j in train), "R-INV-7 violated"

    split = CareerbuilderSplit(
        train_pairs=train,
        val_pairs=val,
        test_pairs=test,
        num_users=num_users,
        num_jobs=num_jobs,
        num_skills=num_skills,
        num_seniority=num_seniority,
    )
    return CareerbuilderDataset(
        data=data,
        split=split,
        user_id_to_idx=user_id_to_idx,
        job_id_to_idx=job_id_to_idx,
        skill_to_idx=skill_to_idx,
        idx_to_user_id=all_users,
        idx_to_job_id=all_jobs,
    )
