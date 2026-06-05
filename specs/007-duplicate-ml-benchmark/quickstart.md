# Quickstart — Verify the ML Benchmark Sandbox

**Date**: 2026-05-21
**Audience**: Reviewer cần xác nhận sandbox `backend/ml_benchmark/` được duplicate đúng và không ảnh hưởng production.

Quy trình này mất ~15 phút (chưa kể smoke test training ~5–10 phút).

---

## Tiền điều kiện

- Đang ở repo `jobflow-gnn`, checkout branch `007-duplicate-ml-benchmark`.
- Python env đã setup (virtualenv `backend/.venv` hoặc tương đương) với PyTorch + PyTorch Geometric.
- Có dataset JobFlow ở `backend/data/processed/` (smoke test cần).

---

## Bước 1 — Chạy script duplicate

```bash
cd /Users/huynam/Documents/PROJECT/jobflow-gnn
bash backend/scripts/duplicate_ml_service.sh
```

**Kết quả mong đợi**:
- Nếu `backend/ml_benchmark/` chưa tồn tại → script tạo mới, in tiến trình từng bước (copy → cleanup cache → strip modules → rewrite imports).
- Nếu `backend/ml_benchmark/` đã tồn tại → script abort với message:
  ```
  ERROR: backend/ml_benchmark already exists. Refusing to overwrite.
  To re-run, manually: rm -rf backend/ml_benchmark && bash backend/scripts/duplicate_ml_service.sh
  ```

---

## Bước 2 — Verify cấu trúc thư mục

```bash
ls backend/ml_benchmark/
```

**Kết quả mong đợi**:
```
__init__.py
baselines/
config/
crawler/      # chỉ có base.py + __init__.py rút gọn
cv_parser/    # đầy đủ
data/
embedding/
evaluation/
graph/
models/
training/
utils/
```

Các module sau **PHẢI KHÔNG xuất hiện**: `api/`, `inference/`, `reranker/`, `verifier/`, `crawler/factory.py`, `crawler/scheduler.py`, `crawler/storage.py`, `crawler/providers/`.

```bash
ls backend/ml_benchmark/crawler/
# Expected: __init__.py  base.py
```

---

## Bước 3 — Verify production nguyên vẹn (R-INV-1)

```bash
git diff --stat backend/ml_service/
```

**Kết quả mong đợi**: rỗng (không có dòng output nào).

```bash
git status backend/ml_service/
# Expected: "nothing to commit" cho subtree này
```

---

## Bước 4 — Verify 0 reference `ml_service` trong sandbox (R-INV-2)

```bash
grep -rn "from ml_service\|import ml_service" backend/ml_benchmark --include='*.py'
```

**Kết quả mong đợi**: rỗng. Nếu có hit:
- Nếu hit là **import statement** → BUG, phải sửa.
- Nếu hit là **comment / docstring / string literal** → review thủ công, có thể giữ nếu có chủ ý (nên đổi thành "ml_benchmark" cho nhất quán).

---

## Bước 5 — Verify cache đã dọn (R-INV-5)

```bash
find backend/ml_benchmark \( -name __pycache__ -o -name '*.pyc' -o -name .pytest_cache \) -print
```

**Kết quả mong đợi**: rỗng.

---

## Bước 6 — Verify import standalone (R-INV-3)

```bash
cd backend
python -c "
import ml_benchmark
import ml_benchmark.training
import ml_benchmark.models
import ml_benchmark.evaluation
import ml_benchmark.baselines
import ml_benchmark.graph
import ml_benchmark.data
import ml_benchmark.embedding
import ml_benchmark.config
import ml_benchmark.utils
print('All sandbox imports OK')
print('ml_benchmark.__file__ =', ml_benchmark.__file__)
"
```

**Kết quả mong đợi**:
```
All sandbox imports OK
ml_benchmark.__file__ = .../backend/ml_benchmark/__init__.py
```

Nếu có ImportError ở module nào → bug, đọc traceback, có thể là cross-dependency bị sót.

---

## Bước 7 — Verify load đồng thời (R-INV-4)

```bash
cd backend
python -c "
import ml_service
import ml_benchmark
assert ml_service.__file__ != ml_benchmark.__file__
assert ml_service.__path__ != ml_benchmark.__path__
print('Production:', ml_service.__file__)
print('Sandbox:   ', ml_benchmark.__file__)
print('Both loaded independently')
"
```

**Kết quả mong đợi**: hai path khác nhau, không có ImportError hay warning.

---

## Bước 8 — Smoke test training pipeline

```bash
cd backend
python scripts/smoke_test_benchmark.py --epochs 5 --checkpoint-dir checkpoints_benchmark
```

**Kết quả mong đợi**:
- Script chạy xong trong < 10 phút trên CPU.
- In ra cuối:
  ```
  ✓ Smoke test completed
  Final metrics: ndcg@10=0.X..., recall@10=0.X..., auc=0.X...
  Checkpoint saved to: backend/checkpoints_benchmark/...
  ```
- Không có exception, không có `nan` trong metric.
- Metric "hợp lý" — NDCG@10 > 0.3 (giá trị bình thường của GraphSAGE trên dataset này; không yêu cầu khớp baseline ±1% ở smoke test này vì chỉ 5 epoch).

Nếu thất bại → kiểm tra dataset path, log lỗi import.

---

## Bước 9 — Verify checkpoint không động production (R-INV-?)

```bash
ls backend/checkpoints/ | head
ls backend/checkpoints_benchmark/ | head
```

**Kết quả mong đợi**:
- `checkpoints/` không có file mới (so với trước khi chạy smoke test) — kiểm bằng `git status backend/checkpoints/`.
- `checkpoints_benchmark/` có file checkpoint mới từ smoke test.

---

## Bước 10 — Verify single commit (R-INV-6)

```bash
git log --oneline -- backend/ml_benchmark/
```

**Kết quả mong đợi**: đúng 1 dòng với message tương tự:
```
<sha> chore(ml_benchmark): duplicate ml_service for thesis benchmarking
```

```bash
git log --oneline -- backend/ml_service/ | head
```

**Kết quả mong đợi**: lịch sử cũ của production, **KHÔNG** có commit duplicate xen vào.

---

## Bảng tổng hợp PASS/FAIL

Reviewer điền:

| Bước | Tiêu chí | Kết quả |
|---|---|---|
| 2 | Cấu trúc thư mục sandbox đúng | ☐ PASS / ☐ FAIL |
| 3 | `backend/ml_service/` git diff rỗng | ☐ PASS / ☐ FAIL |
| 4 | 0 reference `ml_service` trong sandbox | ☐ PASS / ☐ FAIL |
| 5 | 0 file cache trong sandbox | ☐ PASS / ☐ FAIL |
| 6 | Import sandbox standalone OK | ☐ PASS / ☐ FAIL |
| 7 | Load đồng thời cả hai không xung đột | ☐ PASS / ☐ FAIL |
| 8 | Smoke test chạy hết + metric hợp lý | ☐ PASS / ☐ FAIL |
| 9 | Checkpoint tách biệt | ☐ PASS / ☐ FAIL |
| 10 | Single commit đúng message | ☐ PASS / ☐ FAIL |

Tất cả PASS → feature 007 ready để merge / tiếp tục Phase 2 (MovieLens).
