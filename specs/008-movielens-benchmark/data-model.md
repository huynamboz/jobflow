# Phase 1 — Data Model: MovieLens Schema Mapping

**Date**: 2026-05-21
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

Tài liệu này định nghĩa mapping từ MovieLens-1M raw files → HeteroData (PyTorch Geometric) cho training, kèm invariant rules.

---

## E1. Raw MovieLens-1M files

MovieLens-1M có format pipe-delimited (`::`), encoding ISO-8859-1.

### `ratings.dat`

Format: `UserID::MovieID::Rating::Timestamp`

| Field | Type | Note |
|---|---|---|
| UserID | int | 1..6040 |
| MovieID | int | 1..3952 (không liên tục) |
| Rating | int | 1..5 |
| Timestamp | int | Unix epoch |

Volume: ~1,000,209 rows.

### `movies.dat`

Format: `MovieID::Title::Genres`

| Field | Type | Note |
|---|---|---|
| MovieID | int | matches ratings.dat |
| Title | str | "Toy Story (1995)" |
| Genres | str | Pipe-separated, vd "Animation\|Children's\|Comedy" |

Volume: ~3,883 rows. **Title không dùng trong Phase 2** (không có text embedding); Genres CHỈ dùng nếu US2 hetero variant được làm.

### `users.dat`

Format: `UserID::Gender::Age::Occupation::Zip-code`

**Không dùng trong Phase 2** (out of scope per spec: không khai thác user metadata).

---

## E2. Preprocessing pipeline

```text
ratings.dat
    │
    ▼
[1] filter rating >= 4              # FR-003 — positive interaction only
    │  → drop ~58% rows (chỉ rating 4-5 giữ lại)
    ▼
[2] k-core filtering k=10 (iterative)  # FR-005 — chuẩn LightGCN
    │  → user và movie nào còn < 10 inter → drop hết
    │  → lặp đến converge
    ▼
[3] map UserID → user_idx, MovieID → movie_idx   # 0-indexed cho PyG
    │  → store mapping bidirectional cho debug
    ▼
[4] sort theo timestamp per user       # FR-005 — chuẩn bị LOO split
    ▼
[5] split:                              # FR-005 — leave-one-out per user
    │   - last interaction → test
    │   - second-last → val
    │   - rest → train
    ▼
[6] build HeteroData                    # convert sang format PyG
```

Ước tính volume sau pipeline (theo LightGCN paper Table 1, dataset "MovieLens-1M"):
- Users: ~5,949 (từ 6,040)
- Movies: ~3,127 (từ 3,883, sau lọc rating + k-core)
- Total positive interactions: ~571,531 (từ ~1M original ratings)
- Train: ~561,633 (= total − 2×num_users)
- Val: ~5,949 (1 per user)
- Test: ~5,949 (1 per user)

Số thực tế khi implement có thể chệch ±5% — chấp nhận được.

---

## E3. HeteroData schema (bipartite — US1 MVP)

```python
data = HeteroData()

# Node features — learnable embedding placeholder
data["user"].x = xavier_init(num_users, hidden_channels)   # frozen tensor
data["movie"].x = xavier_init(num_movies, hidden_channels) # frozen tensor

# Number of nodes
data["user"].num_nodes = num_users
data["movie"].num_nodes = num_movies

# Edges — chỉ TRAIN interactions, KHÔNG put val/test vào graph (tránh leak)
data["user", "rated", "movie"].edge_index = torch.tensor([
    [user_idx_0, user_idx_1, ...],     # row 0: source user indices
    [movie_idx_0, movie_idx_1, ...],   # row 1: dest movie indices
])
# Shape: (2, num_train_pairs)
```

**Khác với JobFlow schema**: không có `match`/`no_match` edges (vì BPR sampling thay vì supervised pair classification — đã là pattern MovieLens benchmark chuẩn).

---

## E4. HeteroData schema (hetero — US2 stretch)

Thêm node `genre` + edge `has_genre`:

```python
data["genre"].x = xavier_init(num_genres, hidden_channels)   # ~18 genres
data["genre"].num_nodes = num_genres

# Movie ↔ Genre edge (multi-label: 1 movie có nhiều genre)
data["movie", "has_genre", "genre"].edge_index = torch.tensor([
    [movie_idx_0, movie_idx_0, movie_idx_1, ...],   # row 0: movie
    [genre_idx_a, genre_idx_b, genre_idx_a, ...],   # row 1: genre
])
```

Genre extraction:
- Split `movies.dat` cột Genres bằng `|`.
- Build genre catalog (~18 unique trong ML-1M).
- Mỗi (movie, genre) pair → 1 edge.

---

## E5. Split storage

Không lưu vào HeteroData. Trả về riêng:

```python
@dataclass
class MovielensSplit:
    train_pairs: list[tuple[int, int]]   # (user_idx, movie_idx)
    val_pairs: list[tuple[int, int]]     # 1 per user
    test_pairs: list[tuple[int, int]]    # 1 per user
    num_users: int
    num_movies: int
    num_genres: int = 0                   # 0 nếu bipartite
```

Lý do tách: trainer dùng pairs cho BPR sampling + eval, HeteroData chỉ dùng cho GNN forward (chỉ train edges).

---

## E6. ID mapping convention

| MovieLens raw | Sandbox |
|---|---|
| UserID (1..6040, có gap sau k-core) | `user_idx` (0..num_users-1, dense) |
| MovieID (1..3952, có gap) | `movie_idx` (0..num_movies-1, dense) |
| Genre string (vd "Action") | `genre_idx` (0..num_genres-1) |

Mapping được lưu vào loader output:

```python
@dataclass
class MovielensDataset:
    data: HeteroData
    split: MovielensSplit
    user_id_to_idx: dict[int, int]
    movie_id_to_idx: dict[int, int]
    genre_to_idx: dict[str, int]    # empty nếu bipartite
    idx_to_user_id: list[int]       # reverse mapping cho debug
    idx_to_movie_id: list[int]
```

---

## E7. Invariant rules

| Rule | Check |
|---|---|
| R-INV-1: Mỗi user có ≥ 10 train+val+test pairs (vì k=10) | `min(len(pairs_per_user.values())) >= 10` |
| R-INV-2: Mỗi user có đúng 1 val + 1 test pair | `all(len(val_per_user[u]) == 1 for u in users)` và tương tự test |
| R-INV-3: Val pair của user u có timestamp < test pair của u | enforce trong split logic |
| R-INV-4: Train pair của user u có timestamp ≤ val pair của u | enforce trong split logic |
| R-INV-5: Train edges trong HeteroData = đúng `len(split.train_pairs)` cạnh | check shape `data["user","rated","movie"].edge_index.shape[1]` |
| R-INV-6: Val/test pairs KHÔNG xuất hiện trong train edges của HeteroData | set intersection check |
| R-INV-7: Mọi user_idx ∈ [0, num_users), tương tự movie_idx | bound check |

Verify ở smoke test bằng `assert` statements + log.

---

## E8. Output result schema

`backend/results/movielens/seed{N}.json`:

```json
{
  "feature": "008-movielens-benchmark",
  "dataset": "MovieLens-1M",
  "preprocessing": {
    "rating_threshold": 4,
    "k_core": 10,
    "split": "leave-one-out per user (timestamp)"
  },
  "model": "HeteroGraphSAGE",
  "config": {
    "hidden_channels": 64,
    "num_layers": 2,
    "lr": 1e-3,
    "weight_decay": 1e-4,
    "max_epochs": 500,
    "early_stopping_patience": 50,
    "seed": 42
  },
  "stats": {
    "num_users": 5949,
    "num_movies": 3127,
    "num_train_pairs": 561633,
    "num_val_pairs": 5949,
    "num_test_pairs": 5949
  },
  "training": {
    "best_epoch": 187,
    "wall_time_seconds": 3654.2,
    "device": "cpu"
  },
  "test_metrics": {
    "ndcg@20": 0.1834,
    "recall@20": 0.2261,
    "hr@20": 0.5478,
    "mrr": 0.1547
  },
  "versions": {
    "python": "3.11.15",
    "torch": "2.x.y",
    "torch_geometric": "2.x.y"
  }
}
```

`backend/results/movielens/summary.json`:

```json
{
  "feature": "008-movielens-benchmark",
  "seeds": [42, 123, 2024],
  "ndcg@20": {"mean": 0.1834, "std": 0.0042, "values": [0.1834, 0.1791, 0.1876]},
  "recall@20": {"mean": 0.2261, ...},
  "hr@20": {...},
  "mrr": {...},
  "comparison_lightgcn_paper": {
    "ndcg@20_paper": 0.22,
    "recall@20_paper": 0.26,
    "in_same_order_of_magnitude": true
  }
}
```
