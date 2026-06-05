# Contract — `careerbuilder_loader` Public API

**Date**: 2026-05-21

Phase 3 thêm 1 module mới vào `ml_benchmark/data/`. Tất cả API khác (gnn, trainer, scripts) **không thay đổi** — reuse y nguyên Phase 2.

---

## 1. New loader module

```python
from ml_benchmark.data.careerbuilder_loader import (
    CareerbuilderDataset,
    CareerbuilderSplit,
    load_careerbuilder_12,
    download_careerbuilder_12,
)
```

## 2. `load_careerbuilder_12` signature

```python
def load_careerbuilder_12(
    cache_dir: Path | str = "Dataset/careerbuilder-12",
    *,
    subsample_users: int | None = 50_000,
    subsample_seed: int = 42,
    k_core: int = 10,
    hidden_channels: int = 64,
    include_hetero: bool = False,         # US2 stretch — adds skill/seniority nodes
    seed: int = 42,
) -> CareerbuilderDataset: ...
```

- Auto-downloads từ Kaggle nếu cache rỗng (qua `kaggle datasets download`)
- Validate file presence: `apps.tsv`, `users.tsv`, `jobs.tsv` minimum
- Subsample + k-core + LOO split
- Build HeteroData (bipartite default, hetero nếu `include_hetero=True`)

## 3. `CareerbuilderDataset` fields

```python
@dataclass
class CareerbuilderDataset:
    data: HeteroData
    split: CareerbuilderSplit
    user_id_to_idx: dict[str, int]
    job_id_to_idx: dict[str, int]
    skill_to_idx: dict[str, int]          # empty nếu bipartite
    idx_to_user_id: list[str]
    idx_to_job_id: list[str]
```

## 4. `CareerbuilderSplit` fields

```python
@dataclass
class CareerbuilderSplit:
    train_pairs: list[tuple[int, int]]
    val_pairs: list[tuple[int, int]]
    test_pairs: list[tuple[int, int]]
    num_users: int
    num_jobs: int
    num_skills: int = 0
    num_seniority: int = 0
```

## 5. Scripts public surface

```bash
# Smoke test (~5-10 min):
python backend/scripts/smoke_test_careerbuilder.py --epochs 5

# Full train 1 seed (~30-60 min GPU):
python backend/scripts/train_careerbuilder.py --seed 42 \
    --output results/careerbuilder/seed42.json

# Multi-seed via reuse benchmark_compare.py (KHÔNG cần file mới):
python backend/scripts/benchmark_compare.py \
    --train-script scripts/train_careerbuilder.py \
    --seeds 42 123 2024 \
    --output results/careerbuilder/summary.json
```

(Nếu `benchmark_compare.py` hiện hardcode `train_movielens.py`, cần thêm `--train-script` param.)

## 6. Trainer / Model — KHÔNG có API mới

- `Trainer.train_generic()` của Phase 2 dùng nguyên: nhận `src_type="user"`, `dst_type="job"`
- `HeteroGraphSAGE.decode_generic()` của Phase 2 dùng nguyên
- GPU-vectorized eval của Phase 2 dùng nguyên

→ Đây là minh chứng SC-010 "code reuse ≥ 70%".

## 7. Forbidden imports

Inherited từ Phase 1 + Phase 2:
- KHÔNG `from ml_service.*`
- KHÔNG `from ml_benchmark.api/inference/verifier/reranker`
- KHÔNG dùng `torch_geometric.datasets.MovieLens` hay PyG built-in datasets

## 8. Backward compatibility

Phase 2 surface (movielens_loader, train_generic) **KHÔNG đổi**. Regression check sẽ verify:
- `scripts/smoke_test_movielens.py` vẫn PASS sau Phase 3 merge
- `scripts/smoke_test_benchmark.py` (JobFlow Phase 1) vẫn PASS

Lock contract Phase 3 cho:
- Smoke test CareerBuilder
- Full train CareerBuilder
- Multi-seed benchmark CareerBuilder

Phase 4+ (LightGCN baseline, etc.) có thể extend nhưng không được break Phase 1-3 surface.
