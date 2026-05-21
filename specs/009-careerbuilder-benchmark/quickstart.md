# Quickstart — Verify CareerBuilder12 Benchmark

**Date**: 2026-05-21
**Audience**: Reviewer xác nhận Phase 3 CB12 chạy đúng + không break Phase 1/2.

Mất ~30-60 phút (chưa kể full training trên GPU).

---

## Tiền điều kiện

- Branch `009-careerbuilder-benchmark` đã checkout
- Phase 1 (007) + Phase 2 (008) đã merge
- Env Python (`backend/.venv/`) đã có torch + PyG + kaggle + pandas
- Kaggle credential (`~/.kaggle/kaggle.json`) đã setup (đã có từ Phase 2)
- Disk free ≥ 20GB (CB12 raw ~3.6GB + processed cache + checkpoint)
- GPU recommended (CPU fallback OK nhưng chậm)

---

## Bước 1 — Download CareerBuilder12

```bash
mkdir -p Dataset/careerbuilder-12 && cd Dataset/careerbuilder-12 && \
  /Users/huynam/Documents/PROJECT/jobflow-gnn/backend/.venv/bin/kaggle datasets download \
  -d jsrshivam/job-recommendation-case-study --unzip
```

**Expected**: download ~766MB, extract → 6-7 .tsv/.csv files với tổng ~3.6GB.

```bash
ls -la Dataset/careerbuilder-12/
# Expected: apps.tsv (75M), jobs.tsv (3.4G), users.tsv (35M), 
#           user_history.tsv (72M), test_users.tsv (234K), 
#           window_dates.tsv (<1K), popular_jobs.csv (24M)
```

---

## Bước 2 — Smoke test (5 epoch, < 10 phút)

```bash
cd backend
./.venv/bin/python scripts/smoke_test_careerbuilder.py
```

**Expected**:
- Load + subsample + k-core trong < 2 phút
- Train 5 epoch
- In metric: NDCG@20, Recall@20, HR@20, MRR (giá trị nhỏ ở epoch 5, không NaN)
- Exit code 0

---

## Bước 3 — Verify cache (run 2 lần liên tiếp)

```bash
./.venv/bin/python scripts/smoke_test_careerbuilder.py 2>&1 | grep -i "using cached\|downloading"
```

**Expected**: thấy "Using cached dataset", KHÔNG thấy "Downloading".

---

## Bước 4 — Regression check Phase 2 (SC-006)

```bash
cd backend
./.venv/bin/python scripts/smoke_test_movielens.py --epochs 5 2>&1 | tail -10
```

**Expected**: NDCG@20=0.0179 (smoke), wall time < 30s. KHÔNG bị break.

---

## Bước 5 — Full train seed 42 (~30-60 min GPU)

```bash
cd backend
./.venv/bin/python scripts/train_careerbuilder.py --seed 42 \
    --output results/careerbuilder/seed42.json
```

**Expected**:
- Wall time < 1h GPU (SC-009)
- File `backend/results/careerbuilder/seed42.json` sinh ra
- `test_metrics.ndcg@20` trong [0.05, 0.30] (SC-002)
- Stats sau k-core: ≥ 10K user × ≥ 5K job × ≥ 50K positive (SC-011)

---

## Bước 6 — Reproducibility (SC-003)

```bash
cd backend
./.venv/bin/python scripts/train_careerbuilder.py --seed 42 \
    --output results/careerbuilder/seed42_run2.json

# Compare
./.venv/bin/python -c "
import json
r1 = json.load(open('results/careerbuilder/seed42.json'))['test_metrics']
r2 = json.load(open('results/careerbuilder/seed42_run2.json'))['test_metrics']
for k in r1:
    diff = abs(r1[k] - r2[k])
    print(f'{k}: diff={diff:.6f}', 'OK' if diff < 0.001 else 'FAIL')
"
```

**Expected**: mọi diff < 0.001.

---

## Bước 7 — Verify result schema (SC-007)

```bash
./.venv/bin/python -c "
import json
r = json.load(open('results/careerbuilder/seed42.json'))
required = ['feature','dataset','variant','preprocessing','model','config','stats','training','test_metrics','versions']
missing = [k for k in required if k not in r]
print('Top-level:', 'OK' if not missing else f'MISSING {missing}')
for k in ['ndcg@20','recall@20','hr@20','mrr']:
    assert k in r['test_metrics'], f'missing test_metrics.{k}'
print('All required test_metrics present')
"
```

---

## Bước 8 — Verify production untouched (SC-005)

```bash
git diff --stat backend/ml_service/
```

**Expected**: trống (chỉ có 2 file pre-existing baseline từ trước 007).

---

## Bước 9 — (Optional) US2 hetero variant

Chỉ chạy nếu đã implement Phase 4-stretch US2.

```bash
cd backend
./.venv/bin/python scripts/train_careerbuilder.py --hetero --seed 42 \
    --output results/careerbuilder/seed42_hetero.json
```

So sánh với bipartite seed42.json.

---

## Bước 10 — (Optional) Multi-seed

```bash
cd backend
./.venv/bin/python scripts/benchmark_compare.py \
    --train-script scripts/train_careerbuilder.py \
    --seeds 42 123 2024 \
    --output results/careerbuilder/summary.json
```

---

## Bảng PASS/FAIL

| Bước | Tiêu chí | Kết quả |
|---|---|---|
| 1 | Dataset download + extract | ☐ |
| 2 | Smoke test < 10 min, no NaN | ☐ |
| 3 | Cache hit (không re-download) | ☐ |
| 4 | Phase 2 MovieLens regression PASS | ☐ |
| 5 | Full train seed 42, NDCG@20 ∈ [0.05, 0.30] | ☐ |
| 6 | Reproducibility diff < 0.001 | ☐ |
| 7 | Schema đầy đủ | ☐ |
| 8 | Production untouched | ☐ |
| 9 | (Optional) Hetero variant | ☐ |
| 10 | (Optional) Multi-seed summary | ☐ |

Tất cả non-optional PASS → Phase 3 ready close → Phase 4 LightGCN baseline.
