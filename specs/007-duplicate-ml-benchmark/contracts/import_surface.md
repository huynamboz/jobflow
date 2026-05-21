# Contract — Public Import Surface of `ml_benchmark`

**Date**: 2026-05-21
**Spec**: [../spec.md](../spec.md)

Tài liệu này định nghĩa **những gì external code (script benchmark, smoke test, future Phase 2–6 code) được phép import từ `ml_benchmark`**. Phần ngoài contract này coi như private — có thể đổi mà không cần migration.

> **Lưu ý**: Đây không phải HTTP/RPC API — đây là "Python import contract" tương tự `__all__` của một package. Tôn trọng contract giúp Phase 2+ refactor nội bộ sandbox mà không vỡ smoke test.

---

## 1. Top-level package

```python
import ml_benchmark
```

**Cho phép**:
- Import package để kiểm tra `ml_benchmark.__file__`, `ml_benchmark.__doc__`.

**Không cho phép**:
- Dựa vào `ml_benchmark.<anything>` ở top-level (vd `ml_benchmark.HeteroGraphSAGE`). Phải import từ submodule cụ thể.

---

## 2. Training contract

```python
from ml_benchmark.training.trainer import TrainConfig, TrainResult, train_model
```

**TrainConfig**: dataclass với các field (kế thừa từ production):
- `model_type: str` ("graphsage" | "rgcn")
- `hidden_channels: int`, `num_layers: int`, `lr: float`, `weight_decay: float`, `epochs: int`, `patience: int`
- `dropout: float`, `drop_edge_rate: float`, `full_space_neg: bool`, `warmup_epochs: int`
- `hybrid_alpha/beta/gamma: float`, `seed: int`

**train_model(data, splits, config) → TrainResult**: tên function chính xác sẽ confirm khi đọc trainer; smoke test phải dùng đúng signature production.

**TrainResult**: dataclass chứa `best_epoch`, `train_losses`, `val_metrics_history`, `test_metrics`, `model`, `data_clean`.

---

## 3. Model contract

```python
from ml_benchmark.models.gnn import HeteroGraphSAGE, HeteroRGCN, prepare_data_for_gnn
from ml_benchmark.models.losses import bpr_loss
```

Signature giữ nguyên production. Nếu Phase 2 cần đổi kiến trúc, có thể thay thế HOẶC thêm class mới (không xóa cái cũ trong feature này).

---

## 4. Graph contract

```python
from ml_benchmark.graph.schema import (
    NodeType, EdgeType, EDGE_TRIPLETS,
    CVData, JobData, LabeledPair, DatasetSplit,
    SeniorityLevel, EducationLevel, SkillCategory,
)
from ml_benchmark.graph.builder import GraphBuilder
```

**Lưu ý quan trọng**: Tên `NodeType.CV`, `NodeType.JOB` v.v. được giữ nguyên ở Phase 1. Phase 2 có thể generalize thành `NodeType.USER`, `NodeType.ITEM` — đó là refactor của phase sau, không thuộc contract Phase 1.

---

## 5. Data loader contract

```python
from ml_benchmark.data.linkedin_cv_loader import load_cvs   # tên hàm: confirm khi đọc file
from ml_benchmark.data.generator import generate_synthetic   # nếu có
from ml_benchmark.data.labeler import label_pairs            # nếu có
from ml_benchmark.data.skill_normalization import SkillNormalizer
from ml_benchmark.data.skill_extractor import SkillExtractor
```

Phase 2 sẽ thêm `ml_benchmark.data.movielens_loader` và `careerbuilder_loader` — không cần khai báo ở contract này.

---

## 6. Evaluation contract

```python
from ml_benchmark.evaluation.metrics import compute_all_metrics
```

Smoke test sẽ gọi function này.

---

## 7. Baselines contract

```python
from ml_benchmark.baselines.bm25 import BM25Scorer
from ml_benchmark.baselines.cosine import CosineScorer
from ml_benchmark.baselines.skill_overlap import SkillOverlapScorer
```

Phase 4 sẽ thêm `ml_benchmark.baselines.lightgcn` — không thuộc contract Phase 1.

---

## 8. Embedding contract

```python
from ml_benchmark.embedding import get_provider
```

Khi Phase 3 (CareerBuilder) cần encode job description, sẽ gọi function này.

---

## 9. Forbidden imports

- `from ml_service.* import …` trong bất kỳ file nào của `ml_benchmark/` → vi phạm FR-010.
- `from ml_benchmark.api import …` → không tồn tại (api/ đã strip).
- `from ml_benchmark.inference import …` → không tồn tại (inference/ đã strip).
- `from ml_benchmark.verifier import …` → không tồn tại (verifier/ đã strip).
- `from ml_benchmark.reranker import …` → không tồn tại (reranker/ đã strip).
- `from ml_benchmark.crawler.{factory,scheduler,storage,providers}` → không tồn tại (chỉ giữ `crawler/base.py`).

---

## 10. Compatibility note

Contract này được lock cho **smoke test ở Phase 1**. Khi Phase 2 refactor (vd generalize schema), contract sẽ được phép breaking change miễn là:

- Spec/plan mới cho Phase 2 document rõ change.
- Smoke test Phase 1 được cập nhật cùng commit.

Không cần backward compatibility với `ml_service` ở bất kỳ chiều nào.
