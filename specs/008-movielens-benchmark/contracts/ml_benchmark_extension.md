# Contract — `ml_benchmark` Extension Surface (Phase 2)

**Date**: 2026-05-21
**Spec**: [../spec.md](../spec.md)

Tài liệu này định nghĩa public surface MỚI mà Phase 2 (MovieLens) thêm vào package `ml_benchmark`. Surface cũ (từ 007) giữ nguyên 100% backward-compat — xem [007 contract](../../007-duplicate-ml-benchmark/contracts/import_surface.md).

---

## 1. New loader

```python
from ml_benchmark.data.movielens_loader import (
    MovielensDataset,            # dataclass — output container
    MovielensSplit,              # dataclass — train/val/test pairs
    load_movielens_1m,           # main entry point
    download_movielens_1m,       # idempotent download
)
```

**`load_movielens_1m(...)` signature**:

```python
def load_movielens_1m(
    cache_dir: Path | str = "Dataset/movielens-1m",
    *,
    rating_threshold: int = 4,
    k_core: int = 10,
    hidden_channels: int = 64,
    include_genres: bool = False,        # True = US2 hetero variant
    subsample_users: int | None = None,  # debug — only keep N random users
    seed: int = 42,
) -> MovielensDataset: ...
```

- Auto-downloads dataset nếu chưa cache.
- Áp filtering + split + build HeteroData.
- `include_genres=True` → schema hetero (thêm node `genre` + edge `has_genre`).
- `subsample_users` → dùng cho smoke test, prod set None.

**`MovielensDataset` fields**:

```python
@dataclass
class MovielensDataset:
    data: HeteroData                          # PyG graph
    split: MovielensSplit                     # train/val/test pairs
    user_id_to_idx: dict[int, int]
    movie_id_to_idx: dict[int, int]
    genre_to_idx: dict[str, int]              # empty nếu bipartite
    idx_to_user_id: list[int]
    idx_to_movie_id: list[int]
```

---

## 2. Decoder generic alias (additive)

Trong `ml_benchmark/models/gnn.py`:

```python
class MLPDecoder(nn.Module):
    # Method cũ giữ nguyên:
    def decode(self, z_cv: Tensor, z_job: Tensor) -> Tensor: ...

    # KHÔNG sửa MLPDecoder. Thay vào đó, generic decode hiện ở class wrapper:

class HeteroGraphSAGE(nn.Module):
    # Method cũ:
    def decode(self, z_dict, cv_indices, job_indices) -> Tensor: ...

    # MỚI — generic alias:
    def decode_generic(
        self,
        z_dict: dict[str, Tensor],
        src_indices: Tensor,
        dst_indices: Tensor,
        src_type: str,
        dst_type: str,
    ) -> Tensor:
        return self.decoder(z_dict[src_type][src_indices], z_dict[dst_type][dst_indices])
```

**Backward-compat guarantee**: `decode(z, cv, job)` cũ chạy y nguyên. JobFlow code và 007 smoke test KHÔNG cần đổi gì.

---

## 3. Trainer.train_generic (additive)

Trong `ml_benchmark/training/trainer.py`:

```python
class Trainer:
    # Method cũ giữ nguyên — JobFlow vẫn gọi:
    def train(self, data, dataset, cvs, jobs) -> TrainResult: ...

    # MỚI:
    def train_generic(
        self,
        data: HeteroData,
        train_pairs: list[tuple[int, int]],
        val_pairs: list[tuple[int, int]],
        test_pairs: list[tuple[int, int]],
        *,
        src_type: str = "user",
        dst_type: str = "movie",
        num_src: int,
        num_dst: int,
        eval_at_k: list[int] = (20,),         # @20 cho LightGCN compat
    ) -> TrainResult: ...
```

**Pattern**: tương tự `train()`, nhưng:
- Không cần `cvs/jobs` lists — chỉ cần count.
- BPR sampling: negative dst random từ `[0, num_dst)`.
- Eval bằng metric @20 (default).
- Reuse `TrainResult` dataclass (đã có sẵn).

---

## 4. Forbidden imports

Vẫn giữ rule từ 007:

- `from ml_service.* import …` trong sandbox → vi phạm FR-015.
- `from ml_benchmark.api/inference/verifier/reranker` → không tồn tại (đã strip).

Thêm rule mới:

- `from torch_geometric.datasets import MovieLens` → KHÔNG dùng. Loader phải tự control schema để khớp HeteroGraphSAGE của ta. PyG built-in dataset có node feature format khác.

---

## 5. Scripts public surface

```bash
# Smoke (5 epoch, < 10 phút CPU):
python backend/scripts/smoke_test_movielens.py

# Full train (1 seed, ghi vào results/movielens/seed{N}.json):
python backend/scripts/train_movielens.py --seed 42

# Optional — multi-seed gộp summary:
python backend/scripts/benchmark_compare.py --seeds 42 123 2024 --output results/movielens/summary.json
```

Mọi script dùng env var `BENCHMARK_DATASET_DIR` (optional, default `Dataset/movielens-1m`) để override cache location.

---

## 6. Compatibility note

Phase 2 contract này được lock cho:
- Smoke test JobFlow của 007 (regression check)
- Smoke + full train của Phase 2

Phase 3 (CareerBuilder) sẽ thêm `careerbuilder_loader.py` cùng pattern; có thể refactor `train_generic` lên thành class method chung — đó là phép tiến hoá hợp lệ, không vi phạm contract này.

Phase 6 (refactor cleanup) có thể rename `cv/job` → `src/dst` toàn sandbox — sẽ là breaking change được document riêng, không thuộc Phase 2.
