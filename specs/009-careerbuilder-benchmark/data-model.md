# Phase 1 — Data Model: CB12 Schema Mapping

**Date**: 2026-05-21

Mapping từ CareerBuilder12 raw TSV → HeteroData (PyG) cho training.

---

## E1. Raw CB12 schema

### `users.tsv` (~35 MB, ~1.6M rows)

Cột (tab-separated, header row đầu):
```
UserID, WindowID, Split, City, State, Country, ZipCode, DegreeType,
Major, GraduationDate, WorkHistoryCount, TotalYearsExperience, CurrentlyEmployed,
ManagedOthers, ManagedHowMany
```

Cần cho Phase 3: chỉ `UserID` (cho bipartite). Cột khác defer cho US2 nếu cần user feature.

### `jobs.tsv` (~3.4 GB, ~380K rows)

Cột:
```
JobID, WindowID, Title, Description, Requirements, City, State, Country,
Zip5, StartDate, EndDate
```

Cần cho Phase 3:
- Tier 1 (US1 bipartite): `JobID` only
- Tier 2 (US2 hetero): `JobID`, `Title` (seniority parse), `Description` (skill extract), `City`, `State`

**Lưu ý**: file 3.4GB → dùng `pandas.read_csv(usecols=[...], chunksize=100000, ...)` để tránh OOM.

### `apps.tsv` (~75 MB, ~1.6M rows)

Cột:
```
UserID, WindowID, Split, ApplicationDate, JobID
```

Mọi cột đều cần. Đây là source-of-truth cho positive interaction.

Volume note: CB12 sparse — ~1.6M app / (~1.6M user × ~380K job) → density ~0.0003%.

---

## E2. Preprocessing pipeline

```text
1. Download apps.tsv + users.tsv + jobs.tsv từ Kaggle (cache, 1 lần)
       │
       ▼
2. Subsample 50K user (seed=42)
       │  → filter apps_df: chỉ giữ apps có UserID ∈ subsampled set
       ▼
3. K-core=10 iterative
       │  → drop user/job có < 10 apps cho đến converge
       ▼
4. Build dense idx mapping: UserID → user_idx (0..N), JobID → job_idx (0..M)
       ▼
5. Sort apps per user theo ApplicationDate ascending
       ▼
6. Leave-one-out split:
       - Last app → test
       - Second-last → val
       - Rest → train
       ▼
7. Build HeteroData (bipartite cho US1, +genre node cho US2)
```

Ước tính volume sau pipeline (rough estimate dựa trên density):
- Sau subsample 50K user: ~50K apps (rough — density-dependent)
- Sau k-core=10: 10-30K user × 5-20K job × ~50-200K positive
- Train: ~70% positives
- Val: ~10K (1/user)
- Test: ~10K (1/user)

→ Phải validate SC-011 sau khi chạy thực tế. Nếu volume < ngưỡng, fall back tăng subsample.

---

## E3. HeteroData schema (bipartite — US1 MVP)

```python
data = HeteroData()
data["user"].x = xavier_init(num_users, hidden_channels)   # Trainable nn.Embedding (Phase 2 lesson R10)
data["job"].x = xavier_init(num_jobs, hidden_channels)
data["user"].num_nodes = num_users
data["job"].num_nodes = num_jobs

# Chỉ TRAIN edges (tránh leak)
data["user", "applied", "job"].edge_index = torch.tensor([
    [user_idx_0, user_idx_1, ...],
    [job_idx_0, job_idx_1, ...],
])
```

**Khác MovieLens**: dùng edge type `"applied"` thay vì `"rated"` (semantic đúng).

---

## E4. HeteroData schema (hetero — US2 stretch)

Defer chi tiết schema cho khi implement. Tentative:

```python
data["skill"].x = xavier_init(num_skills, hidden_channels)
data["seniority"].x = xavier_init(num_seniority_levels, hidden_channels)
data["job", "requires_skill", "skill"].edge_index = ...
data["job", "requires_seniority", "seniority"].edge_index = ...
# Optional: user-side skill nếu có user_history.tsv processing
```

---

## E5. Split storage

```python
@dataclass
class CareerbuilderSplit:
    train_pairs: list[tuple[int, int]]    # (user_idx, job_idx)
    val_pairs: list[tuple[int, int]]      # 1 per user
    test_pairs: list[tuple[int, int]]     # 1 per user
    num_users: int
    num_jobs: int
    num_skills: int = 0
    num_seniority: int = 0
```

Y hệt `MovielensSplit` chỉ đổi tên field `num_movies` → `num_jobs`, `num_genres` → `num_skills`.

---

## E6. ID mapping

```python
@dataclass
class CareerbuilderDataset:
    data: HeteroData
    split: CareerbuilderSplit
    user_id_to_idx: dict[str, int]   # CB12 UserID is string, không phải int
    job_id_to_idx: dict[str, int]
    skill_to_idx: dict[str, int] = field(default_factory=dict)
    idx_to_user_id: list[str]
    idx_to_job_id: list[str]
```

**Khác MovieLens**: UserID và JobID trong CB12 là **string** (vd "12345" string), trong khi MovieLens là int. Mapping cần handle str → int idx.

---

## E7. Invariant rules

| Rule | Check |
|---|---|
| R-INV-1: Mỗi user còn lại có ≥ k apps (k=10) | `min(Counter(user_idx).values()) >= 10` |
| R-INV-2: Mỗi user 1 val + 1 test pair | enforce trong split logic |
| R-INV-3: val_pair[u].time < test_pair[u].time | enforce trong sort |
| R-INV-4: train_pair[u].time ≤ val_pair[u].time | enforce trong split logic |
| R-INV-5: Train edges == len(train_pairs) | shape check |
| R-INV-6: Val/test pairs KHÔNG trong train edges | set intersection |
| R-INV-7: idx bounds | bound check |
| R-INV-8 (SC-011): Sau k-core, ≥ 10K user × ≥ 5K job × ≥ 50K positive | log + assert |

---

## E8. Output result schema

`backend/results/careerbuilder/seed42.json` — y hệt MovieLens schema, đổi tên:

```json
{
  "feature": "009-careerbuilder-benchmark",
  "dataset": "CareerBuilder12",
  "variant": "bipartite",
  "preprocessing": {
    "subsample_users": 50000,
    "subsample_seed": 42,
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
    "num_users": ...,
    "num_jobs": ...,
    "num_train_pairs": ...,
    "num_val_pairs": ...,
    "num_test_pairs": ...
  },
  "training": {
    "best_epoch": ...,
    "epochs_run": ...,
    "wall_time_seconds": ...,
    "device": "cuda"
  },
  "test_metrics": {
    "ndcg@20": ...,
    "recall@20": ...,
    "hr@20": ...,
    "mrr": ...
  },
  "versions": {
    "python": "3.11.X",
    "torch": "2.4.1+cu121",
    "torch_geometric": "2.7.0"
  }
}
```
