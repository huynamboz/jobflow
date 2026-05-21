# Phase 0 — Research: Duplicate ML Service for Benchmark

**Date**: 2026-05-21
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

Tài liệu này resolve các quyết định kỹ thuật cần thiết trước khi viết script duplicate. Mỗi mục theo format: **Decision / Rationale / Alternatives**.

---

## R1. Cross-module dependencies từ modules-to-keep sang modules-to-strip

**Discovery**: Khảo sát bằng `grep -rn "ml_service\.\(verifier\|crawler\|cv_parser\|inference\|reranker\|api\)" backend/ml_service/{graph,models,training,evaluation,baselines,data,embedding,config,utils}` ra **2 hit**:

- `backend/ml_service/data/skill_extractor.py:13` → `from ml_service.crawler.base import RawJob`
- `backend/ml_service/data/linkedin_cv_loader.py:21` → `from ml_service.cv_parser import CVParser`

Nếu strip thẳng `crawler/` và `cv_parser/`, hai file `data/` trên sẽ gãy import → vi phạm FR-006 (sandbox phải chạy lại pipeline JobFlow).

### Decision

**Giữ exception**: copy thêm vào sandbox:

- `crawler/__init__.py` (rút gọn — chỉ re-export `RawJob`)
- `crawler/base.py` (nguyên file, 57 dòng — chứa `RawJob` dataclass)
- Toàn bộ `cv_parser/` (`__init__.py` + `parser.py`, ~320 dòng)

**KHÔNG copy** các file còn lại của `crawler/` (`factory.py`, `scheduler.py`, `storage.py`, `providers/`, `README.md`) vì không có dependency từ modules-to-keep.

### Rationale

- Mục tiêu spec là loại module không cần cho benchmark, không phải tối thiểu hóa LOC bằng mọi giá.
- `crawler/base.py` là 1 file đơn lẻ, 57 dòng, không kéo theo dependency phụ — chi phí giữ rất thấp.
- `cv_parser/` cần cho `linkedin_cv_loader.py` mà loader này lại là entry point dataset JobFlow → nếu strip phải viết lại loader, vượt phạm vi Phase 1.
- Document exception trong [data-model.md](data-model.md) để Phase 2 (refactor abstraction layer) có thể quyết định strip tiếp khi không còn cần.

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| Strip cả `crawler/` và `cv_parser/`, sửa `data/skill_extractor.py` + `data/linkedin_cv_loader.py` để tự định nghĩa `RawJob`/parser inline | Vượt phạm vi feature (thay vì duplicate đơn thuần thì thành refactor); rủi ro sai logic. |
| Stub `crawler.base` và `cv_parser` bằng empty module | Vẫn vi phạm vì import sẽ thành công nhưng `RawJob`/`CVParser` không có → AttributeError runtime. |
| Giữ nguyên cả `crawler/` và `cv_parser/` đầy đủ | Vi phạm tinh thần FR-002 (strip module không cần). `crawler/providers/` đặc biệt nặng và chứa code crawler không liên quan benchmark. |

---

## R2. Namespace strategy — top-level vs nested

**Discovery**: Có 2 cách đặt sandbox: (a) top-level package `ml_benchmark` song song `ml_service`, (b) nested `ml_service.benchmark`.

### Decision

**Top-level package** `backend/ml_benchmark/` song song với `backend/ml_service/`.

### Rationale

- Nested `ml_service.benchmark` đòi sửa `ml_service/__init__.py` → vi phạm FR-004 (không động production).
- Top-level đảm bảo SC-006 (cả hai load đồng thời không xung đột) bằng Python module system mặc định — không cần namespace package magic.
- Đơn giản nhất để xóa sau này: `rm -rf backend/ml_benchmark/` + `git revert` 1 commit.

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| `ml_service.benchmark` (nested) | Cần sửa `ml_service/__init__.py` |
| `backend.benchmark` (đặt ngang `backend/ml_service/`) | Đặt sai chỗ về mặt semantic — benchmark là ML không phải backend chung. |
| Đặt ngoài `backend/` (vd `thesis/ml_benchmark/`) | Mất khả năng share dataset path tương đối với production scripts; CWD = `backend/` là convention hiện tại. |

---

## R3. Import rewriting tool

**Discovery**: Cần đổi mọi `from ml_service.X import Y` và `import ml_service.X` thành `ml_benchmark.X` trong sandbox. Số lượng file ước tính ~20–30 file Python.

### Decision

Dùng `grep` để liệt kê file chứa pattern, rồi `sed -i ''` (BSD sed trên macOS) với 2 pattern:

```bash
# 1. import ml_service.X → import ml_benchmark.X
grep -rl --include='*.py' 'ml_service' backend/ml_benchmark \
  | xargs sed -i '' -E 's/(^|[^a-zA-Z_])ml_service([.\b])/\1ml_benchmark\2/g'
```

Sau đó verify ngược:

```bash
grep -rn 'ml_service' backend/ml_benchmark --include='*.py'
# Expected: empty (0 hits)
```

Nếu grep verify ra hit → manual fix (có thể là string literal, comment, docstring đề cập).

### Rationale

- Regex đủ vì cú pháp Python `ml_service.X` rất ổn định, không có obfuscation.
- AST-based rewriter (vd `rope`, `libcst`) overkill cho 20–30 file, tăng dependency mới.
- 2-step (rewrite → verify ngược bằng grep) đảm bảo 0 false negative.

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| Dùng `libcst` hoặc `rope` để rewrite AST | Overkill, thêm dependency runtime/dev. |
| Dùng `ruff --fix` với rule import | `ruff` không có rule rename package. |
| Dùng IDE-level rename (PyCharm) | Không tái tạo lại được, không scriptable. |
| Manual edit từng file | Tốn thời gian, dễ sót. |

---

## R4. Cache cleanup ordering

**Discovery**: `cp -r backend/ml_service backend/ml_benchmark` sẽ kéo theo `__pycache__/` chứa `.pyc` với reference tới module path cũ.

### Decision

Dọn cache **NGAY SAU** khi copy, **TRƯỚC** khi rewrite import:

```bash
cp -r backend/ml_service backend/ml_benchmark
find backend/ml_benchmark -type d -name __pycache__ -exec rm -rf {} +
find backend/ml_benchmark -type d -name '.pytest_cache' -exec rm -rf {} +
find backend/ml_benchmark -name '*.pyc' -delete
# Strip modules ở R6
# Rewrite imports ở R3
```

### Rationale

- Tránh dọn lại sau rewrite (sed không động `.pyc`).
- Đảm bảo `__pycache__` không bị regenerate trong khi sed đang chạy (Python không chạy trong script).
- Khớp FR-012 + SC-007.

### Alternatives considered

- Để Python tự regenerate `.pyc` lần đầu import → vẫn ổn, nhưng giai đoạn debug đầu tiên dễ confused vì `.pyc` ban đầu trỏ path cũ.
- `.gitignore` đã có `__pycache__` → việc commit vẫn sạch dù không dọn, nhưng làm việc local sẽ messy.

---

## R5. Checkpoint path separation

**Discovery**: Khảo sát bằng `grep -l "checkpoints" backend/ml_service --include="*.py" -r` ra **2 hit**: `api/app.py` và `inference/engine.py` — cả hai đều ở module bị strip, không ảnh hưởng sandbox.

`training/trainer.py` không hardcode đường dẫn checkpoint — nhận `checkpoint_dir` qua tham số từ caller. Caller chính là các script `backend/run_train_save.py` (production) và `backend/run_experiment_*.py`.

### Decision

**Không cần sửa code trong `ml_benchmark/`** cho checkpoint path. Thay vào đó:

- Khi viết smoke test script ở task tiếp theo, truyền `--checkpoint-dir backend/checkpoints_benchmark/` rõ ràng.
- Thêm `backend/checkpoints_benchmark/` vào `.gitignore` (nếu chưa có cho `checkpoints/`).
- Document quy ước này trong [quickstart.md](quickstart.md): bất kỳ training script nào dùng sandbox PHẢI trỏ tới `checkpoints_benchmark/`.

### Rationale

- Trainer đã được thiết kế đúng — checkpoint path là input, không phải hardcode.
- Sửa default value trong sandbox chỉ là syntactic sugar; rủi ro lớn hơn nếu user dùng entry point production-style mà quên override.
- Convention rõ trong quickstart > code change.

### Alternatives considered

- Hardcode default `checkpoint_dir = 'checkpoints_benchmark'` trong `ml_benchmark/training/trainer.py` — risky vì người đọc code có thể nghĩ logic khác production.
- Dùng env var `BENCHMARK_CHECKPOINT_DIR` đọc trong trainer — thêm magic không cần thiết khi tham số function đã đủ.

---

## R6. Smoke test design

**Discovery**: SC-001 yêu cầu metric trong ±1% baseline production. Cần định nghĩa script + tiêu chí pass cụ thể.

### Decision

Viết `backend/scripts/smoke_test_benchmark.py` thực hiện:

1. Import từ `ml_benchmark.*` (không phải `ml_service.*`).
2. Load dataset JobFlow nhỏ nhất hiện có (vd `data/processed/b89` — confirm tên ở quickstart).
3. Train 5 epoch (fast, không cần converge).
4. In metric: `train_loss`, `val_ndcg@10`, `val_recall@10`, `val_auc`.
5. Exit code 0 nếu chạy hết; 1 nếu có exception.

Tiêu chí pass thủ công (người review check):

- Script chạy hết không exception.
- Metric in ra "hợp lý" — không phải NaN, NDCG > 0.3 (giá trị bình thường của model GraphSAGE trên dataset này).
- KHÔNG cần khớp baseline ±1% ở Phase 1 — vì training 5 epoch không converge. So sánh chính xác baseline sẽ ở Phase 2 khi run training full.

### Rationale

- Smoke test mục tiêu là "code chạy được, không có lỗi import/path", không phải "model train tốt".
- Nếu yêu cầu khớp baseline ±1% với chỉ 5 epoch sẽ flaky và blocking Phase 1.
- Baseline đối chiếu chặt sẽ làm ở Phase 5 (run benchmark full).

### Alternatives considered

- Train full (50 epoch) → tốn thời gian (>30 phút), vi phạm SC-008 (≤ 1 ngày).
- Chỉ chạy `import ml_benchmark; import ml_benchmark.training.trainer` rồi exit → quá yếu, không catch được lỗi runtime.
- Chạy pytest với subset test fixtures → cần copy tests_ml/, vượt phạm vi Phase 1.

---

## R7. Idempotency của script duplicate

**Discovery**: Người review cần chạy lại script để verify. Nếu script không idempotent và xóa sandbox đã sửa, sẽ mất công.

### Decision

`backend/scripts/duplicate_ml_service.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
TARGET="backend/ml_benchmark"
if [ -e "$TARGET" ]; then
  echo "ERROR: $TARGET already exists. Refusing to overwrite."
  echo "To re-run, manually: rm -rf $TARGET && $0"
  exit 1
fi
# ... rest of duplicate logic
```

Thêm flag `--force` (không document trong main usage) cho author dùng khi cần re-run nhanh.

### Rationale

- Default an toàn: từ chối overwrite.
- Có escape hatch (`--force`) cho author.
- Người review chạy `bash backend/scripts/duplicate_ml_service.sh` thấy lỗi → hiểu là phải xóa thư mục thủ công, không vô tình mất việc.

### Alternatives considered

- Auto-overwrite: nguy hiểm, có thể mất sửa của reviewer.
- Tạo backup tự động trước khi overwrite: thêm complexity không cần.

---

## R8. Git commit message

### Decision

```
chore(ml_benchmark): duplicate ml_service for thesis benchmarking

- Fork backend/ml_service → backend/ml_benchmark as a frozen sandbox.
- Keep: graph, models, training, evaluation, baselines, data, embedding,
  config, utils, plus crawler/base.py and full cv_parser/ (deps of data/).
- Strip: api, inference, reranker, verifier, plus crawler/{factory,
  scheduler,storage,providers}.
- Rewrite imports ml_service.* → ml_benchmark.*.
- Spec: specs/007-duplicate-ml-benchmark/spec.md
- Plan: specs/007-duplicate-ml-benchmark/plan.md
```

### Rationale

Thoả SC-005 (chứa từ khoá "benchmark", "thesis", "duplicate"); rõ ràng cho người maintain tương lai; link tới spec/plan để traceability.

---

## Tổng kết

Tất cả NEEDS CLARIFICATION đã được resolve. Sẵn sàng Phase 1.
