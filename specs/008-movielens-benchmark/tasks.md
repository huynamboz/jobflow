---

description: "Task list for feature 008 — MovieLens-1M Benchmark Integration"
---

# Tasks: MovieLens-1M Benchmark Integration

**Input**: Design documents from `/specs/008-movielens-benchmark/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/ml_benchmark_extension.md](contracts/ml_benchmark_extension.md), [quickstart.md](quickstart.md)

**Tests**: Spec không yêu cầu unit test mới. Verification dùng smoke test scripts + regression check JobFlow + verify output schema. KHÔNG generate test tasks dạng TDD.

**Organization**: Tasks grouped by user story (US1 = P1 MVP bipartite, US2 = P2 stretch hetero). US1 close-able là điều kiện đủ cho Phase 2 (per SC-008).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Khác file, không dependency đang dở → có thể parallel
- **[Story]**: User story tag
- Mọi task có file path cụ thể

## Path Conventions

- Repo root: `/Users/huynam/Documents/PROJECT/jobflow-gnn/`
- Sandbox code: `backend/ml_benchmark/`
- Scripts: `backend/scripts/`
- Result evidence (committed): `backend/results/movielens/`
- Dataset cache (gitignored): `Dataset/movielens-1m/`
- Production (read-only): `backend/ml_service/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Chuẩn bị filesystem + gitignore trước khi viết code.

- [ ] T001 [P] Thêm pattern `Dataset/movielens-*/` vào `.gitignore` root để dataset cache không vào git.
- [ ] T002 [P] Tạo thư mục `backend/results/movielens/` (committed dir) với file `.gitkeep` để giữ structure ngay cả khi chưa có kết quả.
- [ ] T003 Capture baseline metric JobFlow để dùng làm regression baseline ở Phase 3. Đọc giá trị từ `specs/007-duplicate-ml-benchmark/_smoke_test_log.txt` (NDCG@10=0.9266, AUC=0.6550, wall time ~94s) và ghi vào `specs/008-movielens-benchmark/_jobflow_baseline.txt` (untracked) để Phase 3 dễ tham chiếu.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Generalize sandbox model + trainer để chấp nhận MovieLens schema. Các thay đổi này phải additive (không break JobFlow).

**⚠️ CRITICAL**: Phase 2 phải xong trước khi US1 implementation. Sau Phase 2 PHẢI chạy regression check JobFlow ngay (T007) — nếu fail, rollback trước khi đi tiếp.

- [ ] T004 Sửa `backend/ml_benchmark/models/gnn.py`: thêm method `HeteroGraphSAGE.decode_generic(z_dict, src_indices, dst_indices, src_type, dst_type)` theo [contract §2](contracts/ml_benchmark_extension.md#2-decoder-generic-alias-additive). KHÔNG sửa method `decode()` cũ. KHÔNG sửa `MLPDecoder`. Áp dụng tương tự cho `HeteroRGCN` nếu file chứa (kiểm bằng grep `class HeteroRGCN`); nếu RGCN cũng có decoder riêng, thêm `decode_generic` ở đó. Ngoài ra: kiểm tra fallback `node_dims` mặc định ở constructor (đang fix CV/Job/Skill/Seniority) — giữ nguyên fallback, KHÔNG sửa.
- [ ] T005 Sửa `backend/ml_benchmark/training/trainer.py`: thêm method `Trainer.train_generic(data, train_pairs, val_pairs, test_pairs, *, src_type='user', dst_type='movie', num_src, num_dst, eval_at_k=(20,))` theo [contract §3](contracts/ml_benchmark_extension.md#3-trainertrain_generic-additive). KHÔNG sửa method `train()` cũ. Logic: (a) strip label edges nếu có (`_strip_label_edges` đã có), (b) prepare_data_for_gnn, (c) build `HeteroGraphSAGE` với metadata động (đã hỗ trợ), (d) loop BPR sampling 1 negative random dst per positive, dùng `decode_generic`, (e) early stopping theo `cfg.patience` trên val NDCG@K[0], (f) eval cuối trên test pairs, trả về `TrainResult` (dataclass đã có).
- [ ] T006 Kiểm tra `backend/ml_benchmark/evaluation/metrics.py`: function `compute_all_metrics` hoặc tương đương có hỗ trợ k=20 không? Nếu chưa, bổ sung (NDCG@20, Recall@20, HR@20, MRR). Đọc file trước, chỉ thêm nếu thiếu — không refactor.
- [ ] T007 **Regression check JobFlow ngay** (R-INV của 007 + SC-006): chạy `cd backend && .venv/bin/python scripts/smoke_test_benchmark.py --epochs 5 --checkpoint-dir checkpoints_benchmark`. Verify exit 0, NDCG@10 trong [0.88, 0.97], AUC trong [0.62, 0.69], wall time < 150s. Lưu output console vào `specs/008-movielens-benchmark/_regression_jobflow.txt` (untracked). Nếu fail → rollback T004-T005, debug, rerun. **NẾU FAIL KHÔNG ĐƯỢC TIẾP TỤC.**

**Checkpoint**: Phase 2 ready khi T007 PASS. Sau đó US1 có thể bắt đầu.

---

## Phase 3: User Story 1 — Bipartite MovieLens train + result (Priority: P1) 🎯 MVP

**Goal**: Researcher chạy 1 lệnh → có metric MovieLens bipartite trong file kết quả copy-paste-able cho luận văn.

**Independent Test**: Quickstart bước 1, 2, 4, 5, 7, 9, 10 PASS. (Bước 3 regression đã xong ở T007; bước 6, 8 là optional/US2.)

### Implementation for User Story 1

- [ ] T008 [US1] Viết `backend/ml_benchmark/data/movielens_loader.py`:
  - Functions: `download_movielens_1m(cache_dir)`, `load_movielens_1m(cache_dir, *, rating_threshold=4, k_core=10, hidden_channels=64, include_genres=False, subsample_users=None, seed=42) -> MovielensDataset`.
  - Dataclasses `MovielensDataset`, `MovielensSplit` theo [data-model §E5-E6](data-model.md#e5-split-storage).
  - Download: `urllib.request.urlretrieve` với progress hook, retry 3 lần exponential backoff (R3).
  - Validation: filesize [5.5MB, 6.5MB] + `zipfile.testzip()` + presence check (R4).
  - K-core iterative algorithm theo [research §R5](research.md#r5-k-core-filtering-algorithm).
  - LOO split per user theo timestamp (R6).
  - HeteroData schema bipartite theo [data-model §E3](data-model.md#e3-heterodata-schema-bipartite--us1-mvp).
  - Embedding init: `nn.init.xavier_uniform_` cho `data["user"].x` và `data["movie"].x` shape `(num_*, hidden_channels)`, dạng tensor (không phải `nn.Embedding` module).
  - Encoding cho `ratings.dat`: ISO-8859-1, delimiter `::`.
  - Pre-condition assert: 7 invariant rules ở [data-model §E7](data-model.md#e7-invariant-rules) — fail-fast nếu broken.
- [ ] T009 [US1] Viết `backend/scripts/smoke_test_movielens.py` theo [research §R8](research.md#r8-smoke-test-design-movielens):
  - `sys.path` bootstrap giống smoke_test_benchmark.py của 007 (insert backend/).
  - CLI args: `--epochs 5`, `--k-core 5`, `--subsample-users 1000`, `--hidden 64`, `--seed 42`.
  - Load MovieLens với `subsample_users=1000`, `k_core=5` (nhẹ hơn).
  - Train 5 epoch bằng `Trainer.train_generic()`.
  - In NDCG@20, Recall@20 mỗi epoch + final test metrics.
  - Exit 0 nếu chạy hết không exception, không có metric NaN.
- [ ] T010 [US1] Chạy smoke test MovieLens lần đầu: `cd backend && .venv/bin/python scripts/smoke_test_movielens.py 2>&1 | tee /Users/huynam/Documents/PROJECT/jobflow-gnn/specs/008-movielens-benchmark/_smoke_movielens_log.txt`. Verify: (a) download MovieLens-1M thành công (~5MB), (b) wall time < 10 phút, (c) exit 0, (d) metric không NaN. Nếu fail → đọc traceback, fix loader/trainer.
- [ ] T011 [US1] Chạy smoke test MovieLens lần thứ hai (cùng env): verify dataset KHÔNG re-download (output chứa "Using cached" hoặc tương đương). Nếu thấy re-download → bug trong cache logic của T008.
- [ ] T012 [P] [US1] Viết `backend/scripts/train_movielens.py`:
  - Args: `--seed 42`, `--max-epochs 500`, `--patience 50`, `--hidden 64`, `--output results/movielens/seed{seed}.json`.
  - Load MovieLens với `k_core=10`, no subsample.
  - Train bằng `Trainer.train_generic()` (hoặc gọi qua wrapper).
  - Eval cuối → sinh JSON theo [data-model §E8](data-model.md#e8-output-result-schema).
  - Log `torch.__version__`, `torch_geometric.__version__`, `python --version` vào `versions` field.
  - Fix random seed: `torch.manual_seed`, `numpy.random.seed`, `random.seed`.
- [ ] T013 [US1] Chạy full train seed 42: `cd backend && .venv/bin/python scripts/train_movielens.py --seed 42 --output results/movielens/seed42.json`. Verify (a) wall time < 6h CPU hoặc < 1h GPU, (b) file `backend/results/movielens/seed42.json` tồn tại, (c) test_metrics.ndcg@20 trong [0.10, 0.35] và test_metrics.recall@20 trong [0.10, 0.40] (SC-002).
- [ ] T014 [US1] Verify reproducibility (SC-003): copy `results/movielens/seed42.json` → `seed42_run1.json` (untracked), chạy lại train_movielens với cùng seed → `seed42_run2.json` (untracked), so sánh — mọi metric chệch < 0.001. Nếu fail → tìm nguồn ngẫu nhiên chưa fix seed (thường là dataloader shuffle hoặc PyG random).
- [ ] T015 [P] [US1] Verify result schema (SC-007): chạy snippet ở [quickstart bước 9](quickstart.md) — assert mọi key required tồn tại trong `seed42.json`. Sửa T012 nếu thiếu key nào.
- [ ] T016 [P] [US1] Verify production untouched (SC-005): `git diff --stat backend/ml_service/` ra rỗng (chỉ có 2 file pre-existing baseline). Nếu xuất hiện file mới do feature 008 → BUG, debug.

**Checkpoint**: User Story 1 done khi T010, T011, T013, T014, T015, T016 đều PASS. Sandbox sinh ra metric MovieLens hoàn chỉnh. Phase 2 close-able (SC-008).

---

## Phase 4: User Story 2 — Hetero variant với genre (Priority: P2, **stretch**)

**Goal**: Cho phép so sánh bipartite vs hetero (có genre node) trên cùng MovieLens dataset.

**⚠️ STRETCH**: Chỉ làm nếu US1 đã PASS hoàn toàn VÀ còn budget thời gian. Nếu skip, Phase 2 vẫn close được.

**Independent Test**: Quickstart bước 8 PASS — có file `seed42_hetero.json` và bảng so sánh bipartite vs hetero.

### Implementation for User Story 2

- [ ] T017 [US2] Mở rộng `movielens_loader.py` (file đã có từ T008): khi `include_genres=True`, parse `movies.dat` (encoding ISO-8859-1, delimiter `::`, format `MovieID::Title::Genres`), split genres bằng `|`, build `genre_to_idx` mapping, thêm node `data["genre"].x = xavier_init(num_genres, hidden_channels)`, thêm edge `data["movie", "has_genre", "genre"].edge_index` theo [data-model §E4](data-model.md#e4-heterodata-schema-hetero--us2-stretch).
- [ ] T018 [US2] Mở rộng `train_movielens.py`: thêm CLI flag `--hetero`. Khi flag set, gọi `load_movielens_1m(include_genres=True)`. Output file default đổi thành `results/movielens/seed{seed}_hetero.json`.
- [ ] T019 [US2] Chạy hetero train seed 42: `cd backend && .venv/bin/python scripts/train_movielens.py --hetero --seed 42 --output results/movielens/seed42_hetero.json`. Verify file tồn tại + metric không NaN. KHÔNG yêu cầu metric cao hơn bipartite — cả hai hướng đều là kết quả nghiên cứu hợp lệ.
- [ ] T020 [US2] So sánh bipartite vs hetero: chạy snippet ở [quickstart bước 8](quickstart.md). Ghi nhận kết quả (hetero > hay < bipartite trên từng metric) vào `specs/008-movielens-benchmark/_hetero_comparison.md` (untracked) — sẽ dùng cho discussion luận văn ở Phase 6.

**Checkpoint**: User Story 2 done (stretch).

---

## Phase 5: Multi-seed benchmark (Polish + Optional)

**Purpose**: Sinh mean ± std qua nhiều seed cho bảng luận văn. Optional nhưng strongly recommended.

- [ ] T021 [P] Viết `backend/scripts/benchmark_compare.py`:
  - Args: `--seeds 42 123 2024 --output results/movielens/summary.json` (hoặc tương tự cho hetero).
  - Loop chạy `train_movielens.py` mỗi seed (subprocess), parse JSON output.
  - Tính mean ± std cho mỗi metric.
  - Sinh `summary.json` theo [data-model §E8](data-model.md#e8-output-result-schema) (block summary).
- [ ] T022 Chạy multi-seed bipartite: `cd backend && .venv/bin/python scripts/benchmark_compare.py --seeds 42 123 2024 --output results/movielens/summary.json`. Wall time ~3× T013. Verify file `summary.json` tồn tại với mean ± std cho mọi metric.
- [ ] T023 [P] Mark Phase 2 trong `specs/006-multi-dataset-benchmark/phases.md` là DONE (tick checkbox của Phase 2); thêm reference tới feature 008 (vd "Implemented in: [008-movielens-benchmark](../008-movielens-benchmark/)"). Document trạng thái US2 (done/stretch-skipped).

---

## Phase 6: Commit & close

- [ ] T024 Stage chỉ feature 008 artifacts: `git add backend/ml_benchmark/models/gnn.py backend/ml_benchmark/training/trainer.py backend/ml_benchmark/data/movielens_loader.py backend/ml_benchmark/evaluation/metrics.py backend/scripts/smoke_test_movielens.py backend/scripts/train_movielens.py backend/scripts/benchmark_compare.py backend/results/movielens/ .gitignore CLAUDE.md specs/008-movielens-benchmark/ specs/006-multi-dataset-benchmark/phases.md`. **TUYỆT ĐỐI KHÔNG** `git add backend/ml_service/` hoặc `git add -A`. (Lưu ý chỉ include `evaluation/metrics.py` nếu T006 thật sự sửa file đó.)
- [ ] T025 Verify staged set sạch: `git diff --cached --stat | grep "ml_service/"` phải rỗng. Verify `git status` cho thấy chỉ các file feature 008 trong staged area.
- [ ] T026 Commit:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat(ml_benchmark): MovieLens-1M benchmark integration

  - Add movielens_loader with k-core=10 + LOO-per-user split (LightGCN convention).
  - Generalize Trainer with train_generic() + HeteroGraphSAGE.decode_generic()
    (additive — JobFlow training path untouched).
  - Add smoke + full train scripts; multi-seed benchmark compare.
  - Sinh evidence cho luận văn: backend/results/movielens/{seedN,summary}.json.
  - Spec: specs/008-movielens-benchmark/spec.md
  - Plan: specs/008-movielens-benchmark/plan.md
  EOF
  )"
  ```
- [ ] T027 Verify commit: `git log --oneline -- backend/ml_benchmark/ backend/scripts/smoke_test_movielens.py backend/scripts/train_movielens.py` — ra 1-2 dòng (tuỳ T024 chia 1 hay nhiều commit).
- [ ] T028 Verify production history clean: `git log --oneline -- backend/ml_service/ | head -3` — KHÔNG có commit của 008 xen vào.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Không phụ thuộc; chạy đầu tiên.
- **Phase 2 (Foundational)**: Phụ thuộc Phase 1. **BLOCKING** US1/US2. T007 (regression check) là gate — fail = stop.
- **Phase 3 (US1)**: Phụ thuộc Phase 2 PASS. Là MVP.
- **Phase 4 (US2)**: Phụ thuộc US1 done. Stretch — có thể skip.
- **Phase 5 (Multi-seed + Polish)**: Phụ thuộc US1 PASS (optional cho US2).
- **Phase 6 (Commit)**: Sau cùng.

### User Story Dependencies

- **US1 (P1)**: Sau Phase 2. MVP.
- **US2 (P2)**: Sau US1 — vì US2 reuse loader/trainer của US1, không độc lập hoàn toàn. Khác pattern thông thường — document rõ.

### Within Each User Story

- US1: T008 (loader) → T009 (smoke script) → T010 (run smoke 1) → T011 (run smoke 2) → T012 (full train script) → T013 (run full train) → T014 (reproducibility) → T015 (schema verify) → T016 (production untouched).
- US2: T017 (loader extend) → T018 (script extend) → T019 (run) → T020 (compare).

### Parallel Opportunities

- **Phase 1**: T001 + T002 + T003 ([P]) parallel — file riêng.
- **Phase 2**: T004 + T005 + T006 KHÔNG parallel — đụng file gnn.py (T004), trainer.py (T005), metrics.py (T006) — nhưng review T005 phụ thuộc T004 hoàn thành để dùng `decode_generic`. Sequence T004 → T005 → T006 → T007.
- **US1**: T015 + T016 ([P]) parallel sau T013 (cùng đọc, không ghi).
- **US2**: tuần tự.
- **Phase 5**: T021 + T023 ([P]) parallel.
- **Phase 6**: tuần tự.

---

## Parallel Example: Phase 1 Setup

```bash
# Có thể chạy song song:
Task T001: Append `Dataset/movielens-*/` to .gitignore
Task T002: Create backend/results/movielens/.gitkeep
Task T003: Write _jobflow_baseline.txt
```

## Parallel Example: US1 verify

```bash
# Sau T013, parallel:
Task T015: Verify result schema (JSON keys)
Task T016: git diff backend/ml_service/ empty check
```

---

## Implementation Strategy

### MVP First (US1 only, skip US2)

1. Phase 1 Setup (T001-T003) — ~10 phút.
2. Phase 2 Foundational (T004-T007) — ~2-3 giờ (T007 regression test có thể tốn nếu fail).
3. Phase 3 US1 (T008-T016) — ~1-2 ngày (T013 full train là điểm nghẽn ~6h CPU; nếu có GPU rút xuống ~1h).
4. **STOP & VALIDATE**: Bipartite MovieLens done, có metric, JobFlow nguyên vẹn.
5. Phase 6 Commit (T024-T028).

→ Phase 2 close-able tại đây.

### Full Phase 2 (US1 + US2 + Multi-seed)

Thêm Phase 4 (US2) và Phase 5 sau bước 4 trên. Tổng thời gian ~3 ngày khớp budget SC-008.

### Solo Developer

Vì T013 (full train CPU ~6h) là điểm nghẽn không parallelize được, lịch hợp lý:
- Ngày 1: Phase 1 + Phase 2 + bắt đầu Phase 3 (T008-T012).
- Ngày 2: T013 full train background; lúc đó làm Phase 4 (US2) trên branch riêng hoặc viết Phase 5 script.
- Ngày 3: Verify + multi-seed + commit.

---

## Notes

- **Critical invariant T007**: T007 (regression check JobFlow) PHẢI pass sau Phase 2 trước khi đi tiếp. Nếu fail = decoder/trainer change broke JobFlow → rollback T004-T005, redesign.
- **Critical invariant T025**: Trước khi commit, verify `git diff --cached` không có file nào trong `backend/ml_service/`. Nếu sai → unstage cho đến khi sạch.
- **Untracked artifacts** (chủ ý, không commit): `_jobflow_baseline.txt`, `_regression_jobflow.txt`, `_smoke_movielens_log.txt`, `_hetero_comparison.md`, `seed*_run{1,2}.json`.
- **Committed evidence**: `backend/results/movielens/seed42.json` (+ thêm seed nếu chạy multi-seed) + `summary.json` (nếu Phase 5 chạy). Đây là tài sản cho luận văn.
- **No tests requested**: Không sinh TDD task. Verification dựa trên smoke scripts + regression + schema assert.
- **Drift acceptance**: Phase 2 ship được với chỉ US1; US2 hetero có thể defer sang sau Phase 3.
