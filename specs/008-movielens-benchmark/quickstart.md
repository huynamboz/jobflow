# Quickstart — Verify MovieLens Benchmark

**Date**: 2026-05-21
**Audience**: Reviewer cần xác nhận Phase 2 MovieLens chạy đúng + không break JobFlow.

Mất ~15 phút (chưa kể full training).

---

## Tiền điều kiện

- Branch `008-movielens-benchmark` đã checkout.
- Feature 007 đã merged (sandbox `backend/ml_benchmark/` tồn tại, smoke test JobFlow đã pass).
- Env Python (`backend/.venv/`) đã có PyTorch + PyG.
- Có internet ở lần chạy đầu (để tải MovieLens-1M).
- Có ~30 MB disk free cho `Dataset/movielens-1m/`.

---

## Bước 1 — Smoke test MovieLens (5 epoch, < 10 phút)

```bash
cd backend
./.venv/bin/python scripts/smoke_test_movielens.py
```

**Kết quả mong đợi**:
- Lần đầu: in tiến trình tải MovieLens-1M (~5 MB), giải nén vào `Dataset/movielens-1m/ml-1m/`.
- Lần sau: skip download, in `Using cached dataset`.
- Build graph với k-core=5, subsample 1000 user.
- Train 5 epoch, in mỗi epoch loss + val_ndcg@20.
- Cuối in:
  ```
  ✓ Smoke test MovieLens completed
    Wall time: ~5-8 phút
    Final NDCG@20: 0.XX  (không yêu cầu match paper)
    No NaN, no exception.
  ```
- Exit code 0.

---

## Bước 2 — Verify dataset cache (idempotent download)

```bash
ls Dataset/movielens-1m/
# Expected: ml-1m.zip + ml-1m/{ratings.dat, movies.dat, users.dat, README}

# Chạy lại smoke — KHÔNG được tải lại:
./.venv/bin/python scripts/smoke_test_movielens.py 2>&1 | grep -i "download\|cached"
# Expected: thấy "Using cached dataset", KHÔNG thấy "Downloading"
```

---

## Bước 3 — Regression check JobFlow (SC-006)

Quan trọng nhất — đảm bảo Phase 2 không break Phase 1.

```bash
cd backend
./.venv/bin/python scripts/smoke_test_benchmark.py --epochs 5 --checkpoint-dir checkpoints_benchmark 2>&1 | tail -10
```

**Kết quả mong đợi**:
- Exit 0, không exception.
- Final metric chệch < 5% so với baseline 007:
  - Baseline NDCG@10 = 0.9266 → cho phép trong [0.88, 0.97]
  - Baseline AUC = 0.6550 → cho phép trong [0.62, 0.69]
  - Wall time ~94s, cho phép trong [50s, 150s] (CPU noise)

Nếu chệch > 5% → BUG trong decoder/Trainer generalization. Rollback ngay.

---

## Bước 4 — Full train 1 seed (chuẩn bị benchmark)

```bash
cd backend
./.venv/bin/python scripts/train_movielens.py --seed 42 --output results/movielens/seed42.json
```

**Kết quả mong đợi**:
- Wall time: < 6 giờ CPU hoặc < 1 giờ GPU (SC-009).
- Sinh file `backend/results/movielens/seed42.json` với schema theo [data-model.md §E8](data-model.md#e8-output-result-schema).
- Test metric NDCG@20 trong [0.10, 0.35], Recall@20 trong [0.10, 0.40] (SC-002 — order of magnitude paper).

---

## Bước 5 — Verify reproducibility (SC-003)

```bash
# Lưu kết quả lần 1:
cp results/movielens/seed42.json results/movielens/seed42_run1.json

# Chạy lại với cùng seed:
./.venv/bin/python scripts/train_movielens.py --seed 42 --output results/movielens/seed42_run2.json

# So sánh:
./.venv/bin/python -c "
import json
a = json.load(open('results/movielens/seed42_run1.json'))['test_metrics']
b = json.load(open('results/movielens/seed42_run2.json'))['test_metrics']
for k in a:
    diff = abs(a[k] - b[k])
    print(f'{k}: a={a[k]:.4f} b={b[k]:.4f} diff={diff:.6f}', 'OK' if diff < 0.001 else 'FAIL')
"
```

**Kết quả mong đợi**: mọi metric chệch < 0.001.

---

## Bước 6 — Multi-seed gộp summary (optional)

```bash
cd backend
./.venv/bin/python scripts/benchmark_compare.py --seeds 42 123 2024 --output results/movielens/summary.json
```

Sinh `summary.json` với mean ± std cho mỗi metric, sẵn sàng copy vào bảng luận văn.

---

## Bước 7 — Verify production untouched (SC-005)

```bash
git diff --stat backend/ml_service/
```

**Expected**: rỗng (chỉ có 2 file pre-existing từ baseline trước 007, nếu chưa commit).

---

## Bước 8 — Verify hetero variant (US2 stretch, optional)

Chỉ chạy nếu US2 đã được implement.

```bash
cd backend
./.venv/bin/python scripts/train_movielens.py --seed 42 --hetero --output results/movielens/seed42_hetero.json

# Compare bipartite vs hetero:
./.venv/bin/python -c "
import json
b = json.load(open('results/movielens/seed42.json'))['test_metrics']
h = json.load(open('results/movielens/seed42_hetero.json'))['test_metrics']
print(f\"{'Metric':<12} {'Bipartite':>10} {'Hetero':>10} {'Delta':>10}\")
for k in b:
    delta = h[k] - b[k]
    print(f'{k:<12} {b[k]:>10.4f} {h[k]:>10.4f} {delta:>+10.4f}')
"
```

Document thấy gì (hetero > bipartite hay ngược lại) — cả hai đều là kết quả nghiên cứu hợp lệ.

---

## Bước 9 — Verify result file format (SC-007)

```bash
./.venv/bin/python -c "
import json
r = json.load(open('results/movielens/seed42.json'))
# Required keys:
assert 'test_metrics' in r
assert 'ndcg@20' in r['test_metrics']
assert 'recall@20' in r['test_metrics']
assert 'hr@20' in r['test_metrics']
assert 'mrr' in r['test_metrics']
assert 'config' in r
assert 'versions' in r
print('Schema OK — ready for thesis table')
"
```

---

## Bước 10 — Single commit verify (sau khi xong implement)

```bash
git log --oneline -- backend/ml_benchmark/ backend/scripts/ backend/results/
# Expected: 1-2 commit cho Phase 2 (1 chính, 1 cho results nếu tách)
```

---

## Bảng PASS/FAIL

| Bước | Tiêu chí | Kết quả |
|---|---|---|
| 1 | Smoke MovieLens 5 epoch, < 10 phút, no NaN | ☐ |
| 2 | Cache dataset, không re-download | ☐ |
| 3 | JobFlow regression: metric chệch < 5% | ☐ |
| 4 | Full train + sinh seed42.json, metric trong order-of-magnitude paper | ☐ |
| 5 | Reproducibility: 2 run cùng seed, diff < 0.001 | ☐ |
| 6 | Multi-seed summary (optional) | ☐ |
| 7 | `git diff backend/ml_service/` rỗng | ☐ |
| 8 | Hetero variant (US2 stretch, optional) | ☐ |
| 9 | Result schema đầy đủ | ☐ |
| 10 | Commit history sạch | ☐ |

Tất cả PASS (bước 6, 8 optional) → Phase 2 ready để close. Sang Phase 3 (CareerBuilder).
