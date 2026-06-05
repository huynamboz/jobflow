# Implementation Plan: Duplicate ML Service for Benchmark

**Branch**: `007-duplicate-ml-benchmark` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-duplicate-ml-benchmark/spec.md`

## Summary

Tạo sandbox `backend/ml_benchmark/` là bản fork đông cứng của `backend/ml_service/`, chỉ giữ lại module cần cho benchmark, để Phase 2–6 (MovieLens, CareerBuilder, LightGCN baseline, full benchmark, write-up) có không gian refactor tự do mà không động đến production.

**Approach kỹ thuật**: dùng `cp -r` để copy nguyên trạng, `rm -rf` các module loại bỏ, `find … -name __pycache__ -exec rm -rf` để dọn cache, `grep -rl 'ml_service' | xargs sed -i ''` để rewrite import. Đặc biệt giữ lại `crawler/base.py` (định nghĩa `RawJob` dataclass) và toàn bộ `cv_parser/` vì hai file `data/skill_extractor.py` và `data/linkedin_cv_loader.py` phụ thuộc cứng vào chúng — đây là exception so với danh sách strip ban đầu, được justify ở [research.md](research.md). Verify bằng grep (`0 reference tới ml_service`), bằng `git diff backend/ml_service` (rỗng), và bằng smoke test chạy `run_train_save.py` sandbox-aware trên dataset JobFlow.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PyTorch 2.x, PyTorch Geometric (HeteroData, GraphSAGE, R-GCN, to_hetero), NumPy, scikit-learn. Django (chỉ phía app, không phải sandbox); sandbox là pure Python package độc lập.

**Storage**: Filesystem only cho sandbox — checkpoint vào `backend/checkpoints_benchmark/`, dataset JobFlow đọc read-only từ `backend/data/` và `Dataset/`. Không động Postgres của Django app.

**Testing**: pytest (đã dùng trong `backend/tests_ml/`). Sandbox sẽ KHÔNG copy thư mục test ngay — smoke test ở Phase 1 là một script chạy training pipeline mini (1 epoch, dataset nhỏ) so sánh metric, không phải unit test.

**Target Platform**: Local dev (macOS Apple Silicon CPU theo `_get_device()` trong [trainer.py](../../backend/ml_service/training/trainer.py)) — sandbox kế thừa cùng device strategy. Sau này khi benchmark sẽ chạy trên CUDA nếu có.

**Project Type**: Python library (sandbox là package độc lập). Không có frontend/mobile thay đổi trong feature này.

**Performance Goals**: Smoke test phải chạy xong trong < 10 phút trên CPU local; metric (NDCG@10, Recall@10, AUC) trên JobFlow sandbox khớp baseline production trong ±1% (đặc tả ở SC-001).

**Constraints**:
- Không động `backend/ml_service/` (SC-002 đòi `git diff` rỗng cho thư mục này).
- Sandbox phải import được đồng thời với production trong cùng Python session (SC-006).
- Sandbox không được `from ml_service import …` ở bất cứ đâu (FR-010, SC-004).
- Hoàn thành trong ≤ 1 ngày làm việc (SC-008).

**Scale/Scope**: ~16 module gốc, dự kiến strip còn 9 module + 2 file exception. Tổng LOC sandbox ước tính 5–7k (giảm ~40% so với production). 1 commit duy nhất.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project chưa có constitution chính thức ([.specify/memory/constitution.md](../../.specify/memory/constitution.md) vẫn ở dạng template chưa điền). Áp dụng nguyên tắc engineering chung:

- **Separation of concerns**: Sandbox và production tách hoàn toàn → PASS (cấu trúc thư mục riêng, namespace riêng).
- **Reversibility**: Sandbox có thể xóa bằng một `git revert` → PASS (cô lập trong 1 commit + 1 thư mục).
- **No production risk**: Feature không sửa code production → PASS (FR-004 + SC-002 enforced).
- **Reproducibility**: Smoke test có metric mục tiêu cụ thể → PASS (SC-001).

Không có violation cần justify ở Complexity Tracking. Re-evaluation sau Phase 1: vẫn PASS — design không phát sinh dependency mới hay shared mutable state nào.

## Project Structure

### Documentation (this feature)

```text
specs/007-duplicate-ml-benchmark/
├── plan.md                          # File này
├── research.md                      # Phase 0 — quyết định module exception, namespace strategy
├── data-model.md                    # Phase 1 — bảng mapping module + decision rules
├── quickstart.md                    # Phase 1 — quy trình verify cho người review
├── contracts/
│   └── import_surface.md            # Phase 1 — public import surface của ml_benchmark
├── checklists/
│   └── requirements.md              # Đã tạo ở /speckit-specify
└── tasks.md                         # /speckit-tasks tạo sau
```

### Source Code (repository root)

```text
backend/
├── ml_service/                      # PRODUCTION — bất khả xâm phạm
│   ├── api/                         # giữ nguyên (sandbox không copy)
│   ├── baselines/                   # giữ nguyên (sandbox copy)
│   ├── config/                      # giữ nguyên (sandbox copy, sửa checkpoint path)
│   ├── crawler/                     # giữ nguyên (sandbox chỉ giữ base.py)
│   ├── cv_parser/                   # giữ nguyên (sandbox copy đầy đủ)
│   ├── data/                        # giữ nguyên (sandbox copy)
│   ├── embedding/                   # giữ nguyên (sandbox copy)
│   ├── evaluation/                  # giữ nguyên (sandbox copy)
│   ├── graph/                       # giữ nguyên (sandbox copy)
│   ├── inference/                   # giữ nguyên (sandbox không copy)
│   ├── models/                      # giữ nguyên (sandbox copy)
│   ├── reranker/                    # giữ nguyên (sandbox không copy)
│   ├── training/                    # giữ nguyên (sandbox copy)
│   ├── utils/                       # giữ nguyên (sandbox copy)
│   └── verifier/                    # giữ nguyên (sandbox không copy)
│
├── ml_benchmark/                    # SANDBOX — feature này tạo mới
│   ├── __init__.py                  # docstring riêng, không re-export
│   ├── baselines/                   # ↩ copy nguyên
│   ├── config/                      # ↩ copy + sửa checkpoint path
│   ├── crawler/
│   │   ├── __init__.py              # ↩ rút gọn, chỉ export RawJob
│   │   └── base.py                  # ↩ copy nguyên (dep của data/skill_extractor.py)
│   ├── cv_parser/                   # ↩ copy nguyên (dep của data/linkedin_cv_loader.py)
│   ├── data/                        # ↩ copy nguyên + đổi import
│   ├── embedding/                   # ↩ copy nguyên + đổi import
│   ├── evaluation/                  # ↩ copy nguyên + đổi import
│   ├── graph/                       # ↩ copy nguyên + đổi import
│   ├── models/                      # ↩ copy nguyên + đổi import
│   ├── training/                    # ↩ copy nguyên + đổi import
│   └── utils/                       # ↩ copy nguyên + đổi import
│
├── checkpoints/                     # PRODUCTION output (đang dùng)
├── checkpoints_benchmark/           # SANDBOX output (feature này tạo, thêm vào .gitignore)
└── scripts/
    └── duplicate_ml_service.sh      # Script idempotent thực hiện duplicate (feature này thêm)
```

**Structure Decision**: Sandbox sống cạnh production trong `backend/`, là Python package độc lập. Đặt cùng `backend/` thay vì thư mục thesis riêng vì các smoke test script và training entry point (vd `run_train_save.py` sandbox-aware mới) cần CWD = `backend/` để dùng cùng dataset, settings.py imports. Tách checkpoint dir là cách rẻ và đủ rõ để tránh nhầm output.

Script `duplicate_ml_service.sh` được viết idempotent: chạy lại nếu sandbox đã tồn tại thì abort an toàn (không xóa) — giúp người review chạy lại để verify mà không sợ mất sandbox đã sửa.

## Complexity Tracking

Không có violation Constitution Check ⇒ bảng này để trống.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none)    | —          | —                                    |

---

## Phase 0 — Outline & Research

Đã hoàn tất ở [research.md](research.md). Tóm tắt các quyết định chốt:

1. **Exception danh sách strip**: Giữ `crawler/base.py` (chỉ file này) và toàn bộ `cv_parser/`. Lý do: `data/skill_extractor.py` và `data/linkedin_cv_loader.py` phụ thuộc cứng, nếu strip sẽ vi phạm FR-006.
2. **Namespace strategy**: `ml_benchmark` là top-level package song song với `ml_service`. Không dùng nested namespace (vd `ml_service.benchmark`) vì sẽ vi phạm FR-004 (không động production).
3. **Import rewriting**: Dùng `grep -rl 'from ml_service' | xargs sed -i ''` (BSD sed cho macOS) + verify bằng grep ngược. Không dùng AST tool vì regex đủ và rủi ro thấp.
4. **Cache cleanup**: Dọn `__pycache__/` và `*.pyc` trong sandbox ngay sau khi copy (trước khi sửa import), tránh bytecode lỗi thời.
5. **Checkpoint path tách**: Sửa default `checkpoint_dir` trong `ml_benchmark/config/` (nếu có hardcode) hoặc thêm env var `BENCHMARK_CHECKPOINT_DIR`. Quyết định cụ thể trong [research.md](research.md).
6. **Smoke test định nghĩa**: Script `backend/scripts/smoke_test_benchmark.py` chạy training 5 epoch với dataset JobFlow nhỏ, in metric. Tiêu chí pass: chạy không lỗi import + metric trong ±1% baseline.

## Phase 1 — Design & Contracts

Đã hoàn tất. Output:

- [data-model.md](data-model.md) — bảng mapping chi tiết "module gốc → module sandbox" với policy (copy/strip/partial), kèm rule rewrite import.
- [contracts/import_surface.md](contracts/import_surface.md) — định nghĩa public import surface của `ml_benchmark` (cái gì external code được phép import từ sandbox).
- [quickstart.md](quickstart.md) — quy trình verify đầy đủ cho người review (clone branch → chạy script → grep verify → smoke test → đối chiếu metric).

Agent context (CLAUDE.md) cũng được cập nhật để trỏ tới plan này.

---

## Phase 2 — Tasks (KHÔNG tạo ở /speckit-plan)

`/speckit-tasks` sẽ sinh `tasks.md` từ artifacts trên. Dự kiến các task chính:

1. Viết `backend/scripts/duplicate_ml_service.sh` (idempotent, có dry-run).
2. Chạy script → tạo `backend/ml_benchmark/`.
3. Rà soát + xác nhận policy exception (giữ `crawler/base.py` + `cv_parser/`).
4. Rewrite import bằng sed; verify grep.
5. Sửa checkpoint path trong sandbox config.
6. Viết `backend/scripts/smoke_test_benchmark.py`.
7. Chạy smoke test → ghi nhận metric.
8. Verify `git diff backend/ml_service` rỗng.
9. Verify `git diff backend/checkpoints` rỗng (không có file mới).
10. Cập nhật `.gitignore` cho `checkpoints_benchmark/` nếu cần.
11. Commit duy nhất với message đã định.

---

## Re-evaluation post-design

- **Separation of concerns**: vẫn PASS — phát hiện exception nhưng cô lập rõ ràng trong data-model.md.
- **Reversibility**: vẫn PASS — vẫn là 1 commit + 1 thư mục.
- **No production risk**: vẫn PASS — không có thay đổi nào trong design phát sinh ghi vào production.
- **Reproducibility**: vẫn PASS — smoke test có script + tiêu chí pass cụ thể.

Không cần update Complexity Tracking.
