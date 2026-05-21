---

description: "Task list for feature 007 — Duplicate ML Service for Benchmark"
---

# Tasks: Duplicate ML Service for Benchmark

**Input**: Design documents from `/specs/007-duplicate-ml-benchmark/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/import_surface.md](contracts/import_surface.md), [quickstart.md](quickstart.md)

**Tests**: Spec không yêu cầu unit test mới. Verification dùng grep, git diff, smoke test script (đã định nghĩa trong quickstart). KHÔNG generate test tasks dạng TDD.

**Organization**: Tasks grouped by user story (US1 = P1, US2 = P2). US1 là MVP — hoàn thành xong là sandbox đã usable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Có thể chạy song song (khác file, không có dependency đang dở)
- **[Story]**: User story tương ứng (US1, US2)
- Mọi task có file path cụ thể

## Path Conventions

- Working dir: `/Users/huynam/Documents/PROJECT/jobflow-gnn/`
- Sandbox đích: `backend/ml_benchmark/`
- Production (read-only ràng buộc): `backend/ml_service/`
- Script artefact: `backend/scripts/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Chuẩn bị thư mục script và state baseline trước khi đụng `backend/`.

- [ ] T001 Tạo thư mục `backend/scripts/` nếu chưa tồn tại; nếu đã có, xác nhận không có file cùng tên `duplicate_ml_service.sh` hoặc `smoke_test_benchmark.py`.
- [ ] T002 Capture baseline state: chạy `git status backend/ml_service backend/ml_benchmark backend/checkpoints` và lưu output vào `specs/007-duplicate-ml-benchmark/_baseline_git_status.txt` (untracked, không commit) — phục vụ đối chiếu sau cùng để chứng minh production không bị động.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Viết script orchestration mà mọi user story phía sau dùng. Phải xong trước khi chạm thư mục sandbox thật.

**⚠️ CRITICAL**: Không user story nào được bắt đầu trước khi Phase 2 xong.

- [ ] T003 Viết `backend/scripts/duplicate_ml_service.sh` (idempotent, refuse-overwrite theo R7 trong [research.md](research.md#r7-idempotency-của-script-duplicate)). Script PHẢI thực hiện theo đúng thứ tự: (a) abort nếu `backend/ml_benchmark/` đã tồn tại trừ khi pass `--force`; (b) `cp -r backend/ml_service backend/ml_benchmark`; (c) dọn `__pycache__/`, `*.pyc`, `.pytest_cache/` trong sandbox (R4); (d) `rm -rf` các module strip (`api/`, `inference/`, `reranker/`, `verifier/`, `crawler/factory.py`, `crawler/scheduler.py`, `crawler/storage.py`, `crawler/providers/`, `crawler/README.md`) — KHÔNG xóa `crawler/base.py`, `crawler/__init__.py`, `cv_parser/`; (e) rewrite imports bằng `grep -rl --include='*.py' 'ml_service' backend/ml_benchmark | xargs sed -i '' -E 's/(^|[^a-zA-Z_])ml_service([.[:space:]])/\1ml_benchmark\2/g'`; (f) in tóm tắt số file thay đổi và số module còn lại. Script bắt đầu bằng `set -euo pipefail`.
- [ ] T004 Viết `backend/scripts/smoke_test_benchmark.py` theo R6 trong [research.md](research.md#r6-smoke-test-design). Phải có CLI args `--epochs` (default 5), `--checkpoint-dir` (default `backend/checkpoints_benchmark`), `--dataset` (default trỏ về dataset JobFlow nhỏ nhất hiện có). Script PHẢI import từ `ml_benchmark.*` (không `ml_service.*`), chạy training pipeline ngắn, in metrics `ndcg@10`, `recall@10`, `auc` cuối, exit 0 nếu hoàn tất / exit 1 nếu exception. Confirm tên dataset cụ thể bằng cách `ls backend/data/processed/` trước khi hardcode default. Không gọi script này trong T004 — chỉ viết.
- [ ] T005 [P] Thêm `backend/checkpoints_benchmark/` vào `.gitignore` (kiểm tra root `.gitignore` và `backend/.gitignore` nếu có; thêm pattern `backend/checkpoints_benchmark/` ở chỗ phù hợp, đặt cạnh pattern `backend/checkpoints/` nếu tồn tại để rõ context).

**Checkpoint**: Foundation ready — scripts đã có nhưng CHƯA chạy. Sandbox chưa tồn tại. Production còn nguyên.

---

## Phase 3: User Story 1 — Sandbox usable cho benchmark (Priority: P1) 🎯 MVP

**Goal**: Sandbox `backend/ml_benchmark/` tồn tại, import được, chạy training pipeline JobFlow thành công, production còn nguyên.

**Independent Test**: Tất cả bước 1–9 trong [quickstart.md](quickstart.md) PASS.

### Implementation for User Story 1

- [ ] T006 [US1] Chạy `bash backend/scripts/duplicate_ml_service.sh`. Verify exit code 0, không có error trong stdout/stderr. Verify `backend/ml_benchmark/` đã được tạo. (Tham chiếu bước 1 quickstart)
- [ ] T007 [US1] Verify cấu trúc thư mục sandbox đúng: `ls backend/ml_benchmark/` ra đúng `__init__.py baselines/ config/ crawler/ cv_parser/ data/ embedding/ evaluation/ graph/ models/ training/ utils/`; `ls backend/ml_benchmark/crawler/` ra đúng `__init__.py base.py`. (Tham chiếu bước 2 quickstart, [data-model.md §E1](data-model.md))
- [ ] T008 [US1] Verify production nguyên vẹn (R-INV-1): `git diff --stat backend/ml_service/` ra rỗng; `git status backend/ml_service/` không có file modified/untracked nào ngoài state baseline đã capture ở T002. (Tham chiếu bước 3 quickstart)
- [ ] T009 [US1] Verify 0 reference `ml_service` trong sandbox (R-INV-2, SC-004): `grep -rn "from ml_service\|import ml_service" backend/ml_benchmark --include='*.py'` ra rỗng. Nếu có hit là import statement → mở file, sửa thủ công (hiếm, vì sed regex ở T003 đã catch); nếu hit là string literal trong docstring/comment → review thủ công, đổi sang "ml_benchmark" cho nhất quán. (Tham chiếu bước 4 quickstart)
- [ ] T010 [US1] Verify cache đã dọn (R-INV-5, SC-007): `find backend/ml_benchmark \( -name __pycache__ -o -name '*.pyc' -o -name .pytest_cache \) -print` ra rỗng. Nếu có hit → xóa.
- [ ] T011 [US1] Sửa `backend/ml_benchmark/__init__.py` rewrite docstring: bỏ liệt kê module `inference`, `crawler` (chỉ giữ `base`), `cv_parser` (vẫn liệt kê vì giữ lại), `reranker` (bỏ); thêm chú thích ngắn ở đầu docstring nói "benchmark sandbox forked from ml_service for thesis multi-dataset benchmarking — do not import from production". (Tham chiếu [data-model.md §E1](data-model.md))
- [ ] T012 [US1] Sửa `backend/ml_benchmark/crawler/__init__.py` rút gọn còn `from ml_benchmark.crawler.base import RawJob` + `__all__ = ['RawJob']`; bỏ mọi re-export khác nếu có. (Tham chiếu [data-model.md §E1](data-model.md))
- [ ] T013 [P] [US1] Verify import standalone (R-INV-3, SC-003): chạy
  ```bash
  cd backend && python -c "
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
  import ml_benchmark.crawler  # phải import được vì giữ base.py
  import ml_benchmark.cv_parser
  print('OK')
  "
  ```
  Phải in `OK`. Nếu có ImportError → đọc traceback, fix cross-dependency bị sót.
- [ ] T014 [P] [US1] Verify load đồng thời (R-INV-4, SC-006): chạy
  ```bash
  cd backend && python -c "
  import ml_service, ml_benchmark
  assert ml_service.__file__ != ml_benchmark.__file__
  assert ml_service.__path__ != ml_benchmark.__path__
  print('Both loaded independently')
  "
  ```
  Phải in `Both loaded independently`.
- [ ] T015 [US1] Confirm dataset path cho smoke test. Chạy `ls backend/data/processed/` và xác định dataset nhỏ nhất sẵn có. Cập nhật default `--dataset` trong `backend/scripts/smoke_test_benchmark.py` (đã viết ở T004) nếu cần. Document tên dataset chọn vào comment đầu file.
- [ ] T016 [US1] Chạy smoke test: `cd backend && python scripts/smoke_test_benchmark.py --epochs 5 --checkpoint-dir checkpoints_benchmark`. Yêu cầu: exit 0, không exception, metric không phải NaN, `ndcg@10 > 0.3`. Lưu output console vào `specs/007-duplicate-ml-benchmark/_smoke_test_log.txt` (untracked, không commit). (Tham chiếu bước 8 quickstart, [research.md §R6](research.md#r6-smoke-test-design))
- [ ] T017 [US1] Verify checkpoint không động production: `git status backend/checkpoints/` không có file mới; `ls backend/checkpoints_benchmark/` có file checkpoint từ smoke test. (Tham chiếu bước 9 quickstart)

**Checkpoint**: User Story 1 done. Sandbox usable. Mọi invariant R-INV-1..5 đã verify. Smoke test pass. Production chưa bị động.

---

## Phase 4: User Story 2 — Lịch sử git sạch (Priority: P2)

**Goal**: Đúng 1 commit duy nhất giới thiệu sandbox, message rõ ràng, lịch sử production không bị xen lẫn.

**Independent Test**: `git log --oneline -- backend/ml_benchmark/` ra đúng 1 dòng; `git log -- backend/ml_service/` không có commit của benchmark xen vào.

### Implementation for User Story 2

- [ ] T018 [US2] Stage chỉ các artifact của sandbox + script + .gitignore + spec docs: `git add backend/ml_benchmark/ backend/scripts/duplicate_ml_service.sh backend/scripts/smoke_test_benchmark.py .gitignore specs/007-duplicate-ml-benchmark/ CLAUDE.md`. **Tuyệt đối KHÔNG** `git add backend/ml_service/` hoặc `git add -A`. Verify bằng `git diff --cached --stat` không có file nào trong `backend/ml_service/`.
- [ ] T019 [US2] Verify staged set sạch trước commit: `git status` phải cho thấy chỉ các file ở T018; nếu có file untracked không liên quan (vd `_smoke_test_log.txt`, `_baseline_git_status.txt`) thì giữ untracked.
- [ ] T020 [US2] Commit bằng heredoc với message theo R8 trong [research.md](research.md#r8-git-commit-message):
  ```bash
  git commit -m "$(cat <<'EOF'
  chore(ml_benchmark): duplicate ml_service for thesis benchmarking

  - Fork backend/ml_service → backend/ml_benchmark as a frozen sandbox.
  - Keep: graph, models, training, evaluation, baselines, data, embedding,
    config, utils, plus crawler/base.py and full cv_parser/ (deps of data/).
  - Strip: api, inference, reranker, verifier, plus crawler/{factory,
    scheduler,storage,providers}.
  - Rewrite imports ml_service.* → ml_benchmark.*.
  - Spec: specs/007-duplicate-ml-benchmark/spec.md
  - Plan: specs/007-duplicate-ml-benchmark/plan.md
  EOF
  )"
  ```
- [ ] T021 [US2] Verify single commit (R-INV-6, SC-005): `git log --oneline -- backend/ml_benchmark/` ra đúng 1 dòng, message chứa "duplicate", "benchmark", "thesis". (Tham chiếu bước 10 quickstart)
- [ ] T022 [US2] Verify lịch sử production không bị xen lẫn: `git log --oneline -- backend/ml_service/ | head -5` ra đúng 5 commit cũ trước đó, KHÔNG có sha của T020.

**Checkpoint**: User Story 2 done. Cả 2 user story đã pass. Feature 007 sẵn sàng merge.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Cập nhật roadmap và đóng phase.

- [ ] T023 [P] Mark Phase 1 trong `specs/006-multi-dataset-benchmark/phases.md` là DONE: tick các checkbox của Phase 1 (Duplicate service); thêm dòng reference tới feature 007 đã hoàn thành (vd "Implemented in: [007-duplicate-ml-benchmark](../007-duplicate-ml-benchmark/)").
- [ ] T024 [P] Chạy lại [quickstart.md](quickstart.md) bảng tổng hợp PASS/FAIL từ đầu, tick all PASS; ghi tay vào `specs/007-duplicate-ml-benchmark/_quickstart_run.md` (untracked).
- [ ] T025 Cập nhật CLAUDE.md SPECKIT block: trỏ active feature sang Phase 2 (MovieLens) khi sẵn sàng, hoặc giữ trỏ 007 nếu user muốn pause review. (Quyết định cùng user — đặt task này cuối cùng để hỏi).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Không phụ thuộc; chạy đầu tiên.
- **Phase 2 (Foundational)**: Phụ thuộc Phase 1; **BLOCK** mọi user story.
- **Phase 3 (US1)**: Phụ thuộc Phase 2; là MVP.
- **Phase 4 (US2)**: Phụ thuộc Phase 3 hoàn tất (vì US2 commit sandbox đã verified, không có nghĩa commit khi import còn lỗi).
- **Phase 5 (Polish)**: Phụ thuộc Phase 4.

### User Story Dependencies

- **US1 (P1)**: Sau Phase 2. Là MVP.
- **US2 (P2)**: Sau US1 — không thể commit sandbox nếu chưa verify hoạt động. Đây là exception so với pattern thông thường (user stories độc lập); document rõ vì US2 về bản chất là "lưu kết quả của US1 vào git history".

### Within Each User Story

- US1: T006 (chạy script) → T007–T010 (verify cấu trúc + ràng buộc) → T011, T012 (sửa __init__) → T013, T014 (verify import) → T015 (confirm dataset) → T016, T017 (smoke test).
- US2: T018 → T019 (stage + verify staged) → T020 (commit) → T021, T022 (verify commit).

### Parallel Opportunities

- **Trong Phase 2**: T005 ([P]) có thể song song với T003 và T004.
- **Trong US1**: T013 và T014 ([P]) có thể song song (cùng đọc, không ghi).
- **Trong Polish**: T023 và T024 ([P]) song song.
- KHÔNG có cơ hội song song giữa US1 và US2 (do dependency).

---

## Parallel Example: Phase 2 Foundation

```bash
# Có thể chạy song song:
Task T003: Viết backend/scripts/duplicate_ml_service.sh
Task T004: Viết backend/scripts/smoke_test_benchmark.py
Task T005: Thêm .gitignore pattern checkpoints_benchmark/
```

## Parallel Example: US1 verification

```bash
# Có thể chạy song song sau khi T011, T012 xong:
Task T013: python -c "import ml_benchmark.*; ..."
Task T014: python -c "import ml_service; import ml_benchmark; assert..."
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1: Setup (T001–T002).
2. Phase 2: Foundational (T003–T005). **CRITICAL — block US1.**
3. Phase 3: US1 (T006–T017).
4. **STOP and VALIDATE**: Run quickstart.md bước 1–9. Nếu pass → sandbox usable, có thể demo cho thầy ngay cả khi chưa commit.

### Incremental Delivery

1. Setup + Foundational ⇒ scripts ready.
2. US1 ⇒ sandbox tồn tại + verify (demo được, chưa commit).
3. US2 ⇒ commit sạch (deliverable cuối).
4. Polish ⇒ đóng feature, mở Phase 2 MovieLens.

### Solo Developer Strategy

Vì feature này nhỏ + linear (US2 phụ thuộc US1), không tận dụng parallel team được. Một dev chạy tuần tự T001 → T025 trong ~1 ngày làm việc (đặc tả SC-008).

---

## Notes

- **Critical invariant**: Không bao giờ chạy `git add backend/ml_service/` hoặc `git add -A` ở bất kỳ task nào. Nếu thấy mình sắp làm vậy → STOP và đọc lại T018.
- **Recovery**: Nếu sai ở Phase 3 (vd import gãy), rollback bằng `rm -rf backend/ml_benchmark/` rồi quay lại T006. Production không bị động (R-INV-1 luôn hold).
- **No tests requested**: Không sinh task TDD. Verification dựa trên grep + git diff + smoke test script (đã định nghĩa quickstart).
- **Commit policy**: 1 commit duy nhất ở T020 cho toàn bộ feature. Các artifact phụ (`_baseline_git_status.txt`, `_smoke_test_log.txt`, `_quickstart_run.md`) untracked, không commit.
- **Drift risk**: Sau feature 007, mọi bug fix trong `ml_service/` sẽ KHÔNG tự động chảy sang `ml_benchmark/`. Chấp nhận (assumption trong spec).
