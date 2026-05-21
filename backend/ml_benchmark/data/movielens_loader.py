"""MovieLens-1M loader for ml_benchmark sandbox (feature 008).

Pipeline:
    1. Download `ml-1m.zip` from GroupLens (idempotent, cached)
    2. Parse `ratings.dat` (UserID::MovieID::Rating::Timestamp), filter rating >= 4
    3. K-core filtering (iterative): drop users and movies with < k interactions
    4. Leave-one-out split per user by timestamp
    5. Build HeteroData (bipartite by default, hetero with `genre` node if requested)

Output: `MovielensDataset` containing `HeteroData`, splits, and id mappings.

The HeteroData uses node types `"user"` and `"movie"` (not `"cv"`/`"job"`).
Trainer should use `Trainer.train_generic()` with `src_type="user"`, `dst_type="movie"`.

Reference: LightGCN paper (He et al., SIGIR 2020), §4.1 for preprocessing convention.
"""

from __future__ import annotations

import logging
import time
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import HeteroData

logger = logging.getLogger(__name__)

MOVIELENS_1M_URL = "https://files.grouplens.org/datasets/movielens/ml-1m.zip"
EXPECTED_FILESIZE_MIN = 5_500_000   # ~5.5 MB
EXPECTED_FILESIZE_MAX = 6_500_000   # ~6.5 MB
REQUIRED_FILES = ("ratings.dat", "movies.dat", "users.dat")


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass
class MovielensSplit:
    train_pairs: list[tuple[int, int]]   # (user_idx, movie_idx)
    val_pairs: list[tuple[int, int]]
    test_pairs: list[tuple[int, int]]
    num_users: int
    num_movies: int
    num_genres: int = 0


@dataclass
class MovielensDataset:
    data: HeteroData
    split: MovielensSplit
    user_id_to_idx: dict[int, int]
    movie_id_to_idx: dict[int, int]
    genre_to_idx: dict[str, int] = field(default_factory=dict)
    idx_to_user_id: list[int] = field(default_factory=list)
    idx_to_movie_id: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    downloaded = block_num * block_size
    if total_size <= 0:
        return
    pct = min(100, int(100 * downloaded / total_size))
    # Print every 10%
    if pct % 10 == 0 and block_num * block_size % (total_size // 10 + 1) < block_size:
        logger.info("  download progress: %d%% (%d / %d bytes)", pct, downloaded, total_size)


def download_movielens_1m(cache_dir: Path | str = "Dataset/movielens-1m") -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "ml-1m.zip"
    extracted_dir = cache_dir / "ml-1m"

    if extracted_dir.is_dir() and all((extracted_dir / f).exists() for f in REQUIRED_FILES):
        logger.info("Using cached MovieLens-1M at %s", extracted_dir)
        return extracted_dir

    if not zip_path.exists() or not (EXPECTED_FILESIZE_MIN <= zip_path.stat().st_size <= EXPECTED_FILESIZE_MAX):
        logger.info("Downloading MovieLens-1M from %s ...", MOVIELENS_1M_URL)
        for attempt in range(3):
            try:
                urllib.request.urlretrieve(MOVIELENS_1M_URL, zip_path, _progress_hook)
                size = zip_path.stat().st_size
                if EXPECTED_FILESIZE_MIN <= size <= EXPECTED_FILESIZE_MAX:
                    logger.info("Downloaded ml-1m.zip (%d bytes)", size)
                    break
                else:
                    logger.warning("Download size out of range: %d", size)
                    zip_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Download attempt %d failed: %s", attempt + 1, e)
                zip_path.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Failed to download MovieLens-1M after 3 attempts")

    logger.info("Extracting ml-1m.zip ...")
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupt zip; bad file: {bad}")
        zf.extractall(cache_dir)

    for f in REQUIRED_FILES:
        if not (extracted_dir / f).exists():
            raise RuntimeError(f"Extraction OK but missing required file: {extracted_dir / f}")
    logger.info("MovieLens-1M ready at %s", extracted_dir)
    return extracted_dir


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_ratings(ratings_path: Path) -> list[tuple[int, int, int, int]]:
    # Format: UserID::MovieID::Rating::Timestamp
    out = []
    with open(ratings_path, encoding="ISO-8859-1") as f:
        for line in f:
            parts = line.strip().split("::")
            if len(parts) != 4:
                continue
            uid, mid, rating, ts = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            out.append((uid, mid, rating, ts))
    return out


def _parse_movies(movies_path: Path) -> dict[int, list[str]]:
    # Format: MovieID::Title::Genres   (Genres is pipe-separated)
    out: dict[int, list[str]] = {}
    with open(movies_path, encoding="ISO-8859-1") as f:
        for line in f:
            parts = line.strip().split("::")
            if len(parts) != 3:
                continue
            mid = int(parts[0])
            genres = [g.strip() for g in parts[2].split("|") if g.strip()]
            out[mid] = genres
    return out


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def _k_core_filter(
    interactions: list[tuple[int, int, int]],   # (user, movie, timestamp)
    k: int,
) -> list[tuple[int, int, int]]:
    # Iterative bipartite k-core: drop user/movie with degree < k, until converged.
    iteration = 0
    while True:
        iteration += 1
        user_deg: Counter = Counter()
        movie_deg: Counter = Counter()
        for u, m, _ in interactions:
            user_deg[u] += 1
            movie_deg[m] += 1
        new = [(u, m, ts) for u, m, ts in interactions
               if user_deg[u] >= k and movie_deg[m] >= k]
        logger.info("  k-core iter %d: %d → %d interactions", iteration, len(interactions), len(new))
        if len(new) == len(interactions):
            return new
        interactions = new


def _leave_one_out_split(
    interactions: list[tuple[int, int, int]],   # (user_idx, movie_idx, timestamp)
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    by_user: dict[int, list[tuple[int, int]]] = {}   # user_idx -> [(movie_idx, ts)]
    for u, m, ts in interactions:
        by_user.setdefault(u, []).append((m, ts))

    train, val, test = [], [], []
    for u, items in by_user.items():
        items.sort(key=lambda x: x[1])   # ascending by timestamp
        if len(items) < 3:
            # Defensive: if k-core didn't catch (shouldn't happen with k>=3)
            train.extend((u, m) for m, _ in items)
            continue
        test.append((u, items[-1][0]))
        val.append((u, items[-2][0]))
        train.extend((u, m) for m, _ in items[:-2])
    return train, val, test


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def load_movielens_1m(
    cache_dir: Path | str = "Dataset/movielens-1m",
    *,
    rating_threshold: int = 4,
    k_core: int = 10,
    hidden_channels: int = 64,
    include_genres: bool = False,
    subsample_users: Optional[int] = None,
    seed: int = 42,
) -> MovielensDataset:
    extracted = download_movielens_1m(cache_dir)

    logger.info("Parsing ratings.dat ...")
    raw = _parse_ratings(extracted / "ratings.dat")
    logger.info("  loaded %d raw ratings", len(raw))

    # Filter rating >= threshold
    positives = [(u, m, ts) for u, m, r, ts in raw if r >= rating_threshold]
    logger.info("  after rating>=%d filter: %d positives", rating_threshold, len(positives))

    # Optional subsample users (smoke test mode)
    if subsample_users is not None:
        rng = np.random.RandomState(seed)
        all_users = sorted({u for u, _, _ in positives})
        if len(all_users) > subsample_users:
            keep = set(rng.choice(all_users, size=subsample_users, replace=False).tolist())
            positives = [(u, m, ts) for u, m, ts in positives if u in keep]
            logger.info("  subsampled to %d users: %d positives", subsample_users, len(positives))

    # K-core filtering
    logger.info("Applying k-core filter (k=%d) ...", k_core)
    filtered = _k_core_filter(positives, k_core)
    if not filtered:
        raise RuntimeError(f"k-core={k_core} produced empty interaction set")

    # Build dense idx mappings
    all_users = sorted({u for u, _, _ in filtered})
    all_movies = sorted({m for _, m, _ in filtered})
    user_id_to_idx = {uid: i for i, uid in enumerate(all_users)}
    movie_id_to_idx = {mid: i for i, mid in enumerate(all_movies)}
    num_users = len(all_users)
    num_movies = len(all_movies)
    logger.info("  after k-core: %d users, %d movies, %d interactions",
                num_users, num_movies, len(filtered))

    # Convert to (user_idx, movie_idx, ts)
    interactions = [(user_id_to_idx[u], movie_id_to_idx[m], ts) for u, m, ts in filtered]

    # Leave-one-out split
    logger.info("Building leave-one-out split per user ...")
    train, val, test = _leave_one_out_split(interactions)
    logger.info("  train=%d val=%d test=%d", len(train), len(val), len(test))

    # ---------------------------- Build HeteroData ----------------------------
    data = HeteroData()

    # Learnable embedding init via xavier (frozen tensor — gets re-projected by GNN)
    user_x = torch.empty(num_users, hidden_channels)
    movie_x = torch.empty(num_movies, hidden_channels)
    nn.init.xavier_uniform_(user_x)
    nn.init.xavier_uniform_(movie_x)
    data["user"].x = user_x
    data["movie"].x = movie_x
    data["user"].num_nodes = num_users
    data["movie"].num_nodes = num_movies

    # Edges: ONLY train pairs (to avoid leaking val/test signal into the graph)
    train_arr = np.asarray(train, dtype=np.int64).T   # shape (2, N_train)
    if train_arr.size == 0:
        raise RuntimeError("Empty train set after split")
    data["user", "rated", "movie"].edge_index = torch.from_numpy(train_arr).long()

    # Optional: genre hetero (US2 stretch)
    genre_to_idx: dict[str, int] = {}
    if include_genres:
        movies_map = _parse_movies(extracted / "movies.dat")
        all_genres = sorted({g for mid in all_movies for g in movies_map.get(mid, [])})
        genre_to_idx = {g: i for i, g in enumerate(all_genres)}
        num_genres = len(all_genres)
        logger.info("  hetero variant: %d genres", num_genres)

        genre_x = torch.empty(num_genres, hidden_channels)
        nn.init.xavier_uniform_(genre_x)
        data["genre"].x = genre_x
        data["genre"].num_nodes = num_genres

        mg_pairs = []
        for mid, gs in movies_map.items():
            m_idx = movie_id_to_idx.get(mid)
            if m_idx is None:
                continue
            for g in gs:
                if g in genre_to_idx:
                    mg_pairs.append((m_idx, genre_to_idx[g]))
        if mg_pairs:
            mg_arr = np.asarray(mg_pairs, dtype=np.int64).T
            data["movie", "has_genre", "genre"].edge_index = torch.from_numpy(mg_arr).long()
    else:
        num_genres = 0

    # ---------------------------- Invariants (defensive asserts) ----------------------------
    # R-INV-1: every user >= k_core interactions
    user_total = Counter(u for u, _, _ in interactions)
    if user_total:
        min_inter = min(user_total.values())
        assert min_inter >= k_core, f"R-INV-1 violated: user has only {min_inter} inter, expected >= {k_core}"
    # R-INV-2,3,4 enforced by split logic
    # R-INV-5: train edge count matches
    assert data["user", "rated", "movie"].edge_index.shape[1] == len(train), "R-INV-5 violated"
    # R-INV-6: val/test pairs not in train edges
    train_set = set(train)
    assert not any(p in train_set for p in val), "R-INV-6 violated (val leaks into train)"
    assert not any(p in train_set for p in test), "R-INV-6 violated (test leaks into train)"
    # R-INV-7: bounds check
    assert all(0 <= u < num_users and 0 <= m < num_movies for u, m in train), "R-INV-7 violated"

    split = MovielensSplit(
        train_pairs=train,
        val_pairs=val,
        test_pairs=test,
        num_users=num_users,
        num_movies=num_movies,
        num_genres=num_genres,
    )
    return MovielensDataset(
        data=data,
        split=split,
        user_id_to_idx=user_id_to_idx,
        movie_id_to_idx=movie_id_to_idx,
        genre_to_idx=genre_to_idx,
        idx_to_user_id=all_users,
        idx_to_movie_id=all_movies,
    )
