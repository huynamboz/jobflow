---

description: "Task list for feature 009 — CareerBuilder12 Main Standard Benchmark"
---

# Tasks: CareerBuilder12 Main Standard Benchmark

**Input**: Design documents from `/specs/009-careerbuilder-benchmark/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/careerbuilder_loader_api.md](contracts/careerbuilder_loader_api.md), [quickstart.md](quickstart.md)

**Tests**: Spec không yêu cầu TDD. Verification dùng smoke + reproducibility + Phase 2 regression check.

**Organization**: Tasks grouped by user story (US1 P1 bipartite, US2 P2 stretch hetero). US1 close-able là điều kiện đủ cho Phase 3 (per SC-008).

**Code reuse target**: ≥ 70% logic từ Phase 2 (SC-010) — loader pattern, train script pattern, trainer/model UNTOUCHED.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Khác file, không dependency đang dở → song song
- **[Story]**: US1, US2
- Mọi task có file path cụ thể

## Path Conventions

- Repo root: `/Users/huynam/Documents/PROJECT/jobflow-gnn/`
- Sandbox: `backend/ml_benchmark/` (KHÔNG sửa trainer/gnn — chỉ thêm loader)
- Scripts: `backend/scripts/`
- Result (committed): `backend/results/careerbuilder/`
- Dataset cache (gitignored qua `Dataset/`): `Dataset/careerbuilder-12/`
- Server workspace: `/home/dana/huynam/jobflow-gnn/backend/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Chuẩn bị filesystem + dataset trước khi viết code.

- [ ] T001 [P] Tạo `backend/results/careerbuilder/` (committed dir) với `.gitkeep` để giữ structure.
- [ ] T002 [P] Verify Kaggle credential vẫn work: chạy `~/.kaggle/kaggle.json` exists + `backend/.venv/bin/kaggle datasets list -s "careerbuilder" | head -3`. Nếu fail, follow flow Phase 2 setup Kaggle.
- [ ] T003 Capture Phase 2 baseline metric cho regression check sau: lấy NDCG@20 từ `backend/results/movielens/seed42.json` ghi vào `specs/009-careerbuilder-benchmark/_phase2_baseline.txt` (untracked) — phục vụ T015 verify.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Download CB12 dataset (lần đầu mất ~5-10 phút với 766MB) — block mọi train tasks.

**⚠️ CRITICAL**: Phase 2 phải xong trước US1 implementation.

- [ ] T004 Download CB12 dataset: `mkdir -p Dataset/careerbuilder-12 && cd Dataset/careerbuilder-12 && /Users/huynam/Documents/PROJECT/jobflow-gnn/backend/.venv/bin/kaggle datasets download -d jsrshivam/job-recommendation-case-study --unzip`. Verify: `ls Dataset/careerbuilder-12/` ra ≥ 6 file `.tsv` + `popular_jobs.csv`. Tổng disk usage ~3.6GB.
- [ ] T005 Verify CB12 file integrity: chạy `wc -l Dataset/careerbuilder-12/{apps,users}.tsv` (jobs.tsv quá lớn). Expected: apps ~1.6M lines, users ~1.6M lines. Nếu thấp đáng kể → corrupt, re-download.
- [ ] T006 Sync dataset lên server (tùy chọn — nếu chạy training trên server thay vì local): `sshpass -e rsync -avz Dataset/careerbuilder-12/ dana@10.9.0.4:/home/dana/huynam/jobflow-gnn/Dataset/careerbuilder-12/`. Skip nếu chạy local.

**Checkpoint**: Dataset ready local (và server nếu T006 chạy). US1 có thể bắt đầu.

---

## Phase 3: User Story 1 — Bipartite CareerBuilder12 train (Priority: P1) 🎯 MVP MAIN THESIS RESULT

**Goal**: Researcher chạy 1 lệnh, có metric NDCG/Recall/HR/MRR@20 trên CareerBuilder12 bipartite, đưa thẳng vào bảng luận văn.

**Independent Test**: Quickstart bước 1, 2, 3, 5, 6, 7, 8 PASS.

### Implementation for User Story 1

- [ ] T007 [US1] Viết `backend/ml_benchmark/data/careerbuilder_loader.py`:
  - **Pattern**: copy structure từ `movielens_loader.py` (dataclasses, load fn, helper)
  - Dataclasses `CareerbuilderDataset`, `CareerbuilderSplit` theo [data-model §E5-E6](data-model.md#e5-split-storage)
  - `download_careerbuilder_12(cache_dir)`: kiểm cache, nếu chưa có thì `subprocess.run(['kaggle', 'datasets', 'download', '-d', 'jsrshivam/job-recommendation-case-study', '--unzip', '-p', cache_dir])`. Đơn giản hơn urllib retry vì Kaggle CLI đã handle retry.
  - `load_careerbuilder_12(...)` signature theo [contract §2](contracts/careerbuilder_loader_api.md#2-load_careerbuilder_12-signature):
    - Parse `users.tsv` (chỉ cột `UserID`) bằng `pandas.read_csv(sep='\t', encoding='ISO-8859-1', usecols=['UserID'], dtype=str)`
    - Subsample 50K user (default) bằng `np.random.default_rng(subsample_seed).choice(...)`
    - Parse `apps.tsv` (cột `UserID`, `JobID`, `ApplicationDate`), filter chỉ giữ subsampled users
    - Parse `jobs.tsv` Tier 1 (chỉ `JobID`) — dùng `chunksize=100000` để stream parse, build set of valid job IDs (chỉ giữ jobs xuất hiện trong filtered apps để giảm graph size)
    - K-core=10 iterative (copy function `_k_core_filter` từ movielens_loader, đổi term)
    - Build dense idx mapping (UserID string → int)
    - LOO split per user theo `ApplicationDate` (copy `_leave_one_out_split` từ movielens_loader)
    - Build HeteroData bipartite: `user`, `job` nodes với learnable xavier embed; edge `("user", "applied", "job")` chỉ train_pairs
    - 8 invariant asserts theo [data-model §E7](data-model.md#e7-invariant-rules)
  - **KHÔNG sửa** `trainer.py`, `gnn.py` (reuse Phase 2 API)
- [ ] T008 [US1] Viết `backend/scripts/smoke_test_careerbuilder.py`:
  - Pattern: copy từ `smoke_test_movielens.py`, đổi import `movielens_loader` → `careerbuilder_loader`
  - Sklearn pre-warm + django setup + torch_geometric pre-import (Phase 2 lessons R8-R9)
  - Default args: `--epochs 5`, `--subsample-users 5000` (smoke nhỏ hơn full), `--k-core 5`
  - Train với `Trainer.train_generic()` reuse, `src_type="user"`, `dst_type="job"`
  - Exit 0 nếu hoàn tất, exit 1 nếu NaN
- [ ] T009 [US1] Sync code lên server: `sshpass -e rsync -avz backend/ml_benchmark/data/careerbuilder_loader.py backend/scripts/smoke_test_careerbuilder.py dana@10.9.0.4:/home/dana/huynam/jobflow-gnn/backend/{ml_benchmark/data/,scripts/}/`. Skip nếu local-only.
- [ ] T010 [US1] Run smoke test trên server (recommend) hoặc local: `cd backend && .venv/bin/python scripts/smoke_test_careerbuilder.py 2>&1 | tee /tmp/cb_smoke.log`. Sync log về `specs/009-careerbuilder-benchmark/_smoke_cb_log.txt` (untracked). Verify: exit 0, no NaN, wall time < 10 min.
- [ ] T011 [P] [US1] Viết `backend/scripts/train_careerbuilder.py`:
  - Pattern: copy từ `train_movielens.py`, đổi import + đổi loader call + đổi `src_type/dst_type`
  - Default config: hidden=64, layers=2, lr=1e-3, weight_decay=1e-4, max_epochs=500, patience=50, seed=42 (giống Phase 2)
  - Output JSON theo [data-model §E8](data-model.md#e8-output-result-schema) — đổi `dataset: "CareerBuilder12"`, `feature: "009-careerbuilder-benchmark"`, thêm `preprocessing.subsample_users: 50000`
- [ ] T012 [US1] Sync train script lên server + chạy full train seed 42: `nohup .venv/bin/python scripts/train_careerbuilder.py --seed 42 --output results/careerbuilder/seed42.json > logs/train_cb_seed42.log 2>&1 &`. Monitor bằng pattern Phase 2 (30s tick). Wall time expected: 30-60 min GPU.
- [ ] T013 [US1] Sync result về local: `sshpass -e rsync -avz dana@10.9.0.4:/home/dana/huynam/jobflow-gnn/backend/results/careerbuilder/seed42.json backend/results/careerbuilder/`.
- [ ] T014 [US1] Verify SC-002 metric range: `python -c "import json; r=json.load(open('backend/results/careerbuilder/seed42.json'))['test_metrics']; assert 0.05 <= r['ndcg@20'] <= 0.30, f'NDCG@20={r[\"ndcg@20\"]} ngoài [0.05, 0.30]'"`. Nếu fail, kiểm subsample size + k-core threshold.
- [ ] T015 [US1] Verify SC-011 dataset size sau k-core: từ `result['stats']`, assert `num_users >= 10000 AND num_jobs >= 5000 AND num_train_pairs >= 50000`.
- [ ] T016 [US1] Verify SC-007 schema: chạy snippet ở [quickstart bước 7](quickstart.md). Mọi required key tồn tại.
- [ ] T017 [P] [US1] Verify SC-005 production untouched: `git diff --stat backend/ml_service/` ra rỗng (chỉ pre-existing baseline).
- [ ] T018 [P] [US1] **REGRESSION (SC-006)**: chạy lại Phase 2 smoke `cd backend && .venv/bin/python scripts/smoke_test_movielens.py --epochs 5`. Verify final NDCG@20 chệch < 5% so với baseline ở `_phase2_baseline.txt` (T003). Nếu fail → Phase 3 code broke Phase 2, rollback ngay.

**Checkpoint**: US1 done khi T010, T012, T014, T015, T016, T017, T018 PASS. Phase 3 close-able.

---

## Phase 4: User Story 1 Reproducibility verification (Priority: P1)

**Goal**: Verify SC-003 — chạy lại cùng seed cho metric chệch < 0.001.

- [ ] T019 [US1] Re-run train_careerbuilder seed 42, output `results/careerbuilder/seed42_run2.json`: `nohup .venv/bin/python scripts/train_careerbuilder.py --seed 42 --output results/careerbuilder/seed42_run2.json > logs/train_cb_seed42_run2.log 2>&1 &`. Monitor.
- [ ] T020 [US1] Sync `seed42_run2.json` về local.
- [ ] T021 [US1] Compare 2 runs:
  ```bash
  python -c "
  import json
  r1 = json.load(open('backend/results/careerbuilder/seed42.json'))['test_metrics']
  r2 = json.load(open('backend/results/careerbuilder/seed42_run2.json'))['test_metrics']
  for k in r1:
      diff = abs(r1[k] - r2[k])
      print(f'{k}: {r1[k]:.6f} vs {r2[k]:.6f} diff={diff:.6f}', 'OK' if diff < 0.001 else 'FAIL')
  "
  ```
  Mọi diff < 0.001 → PASS SC-003.

---

## Phase 5: User Story 2 — Hetero variant (Priority: P2, **stretch**)

**Goal**: Cho phép so sánh bipartite vs hetero (với skill + seniority node) trên CareerBuilder12.

**⚠️ STRETCH**: Chỉ làm nếu US1 đã PASS hoàn toàn VÀ còn budget. Phase 3 close-able mà không cần US2.

### Implementation for User Story 2

- [ ] T022 [US2] Mở rộng `careerbuilder_loader.py`: khi `include_hetero=True`:
  - Re-parse `jobs.tsv` Tier 2: `usecols=['JobID', 'Title', 'Description', 'City', 'State']`, `chunksize=100000`
  - Extract skill từ `Description` bằng keyword match từ `backend/ml_benchmark/data/skill-alias.json` (reuse sandbox)
  - Parse seniority từ `Title` bằng regex (Junior/Mid/Senior/Lead/Manager) — adapt từ `ml_benchmark/graph/schema.py` `SeniorityLevel`
  - Thêm `data["skill"].x`, `data["seniority"].x` (xavier init)
  - Thêm edges `("job", "requires_skill", "skill")`, `("job", "requires_seniority", "seniority")`
- [ ] T023 [US2] Mở rộng `train_careerbuilder.py`: thêm CLI flag `--hetero`. Khi set, gọi `load_careerbuilder_12(include_hetero=True)`, output filename mặc định `results/careerbuilder/seed42_hetero.json`.
- [ ] T024 [US2] Sync code + chạy hetero train seed 42 trên server. ~30-60 min GPU.
- [ ] T025 [US2] Sync result về + compare bipartite vs hetero. Ghi nhận vào `specs/009-careerbuilder-benchmark/_hetero_comparison.md` (untracked) — discussion luận văn.

**Checkpoint**: US2 done (stretch).

---

## Phase 6: Multi-seed benchmark (Polish, Optional)

**Purpose**: Mean ± std qua nhiều seed cho thesis table chuyên nghiệp.

- [ ] T026 [P] Update `backend/scripts/benchmark_compare.py` thêm `--train-script` arg (nếu hiện chưa hỗ trợ — kiểm code trước). Nếu đã có thì skip task này.
- [ ] T027 Chạy multi-seed (3 seeds × ~45 min = ~2-3 giờ GPU): `nohup .venv/bin/python scripts/benchmark_compare.py --train-script scripts/train_careerbuilder.py --seeds 42 123 2024 --output results/careerbuilder/summary.json &`. Monitor pattern Phase 2. Sync `summary.json` về local.
- [ ] T028 [P] Mark Phase 3 DONE trong `specs/006-multi-dataset-benchmark/phases.md` + thêm link tới 009.

---

## Phase 7: Commit & close

- [ ] T029 Stage chọn lọc:
  ```bash
  git add backend/ml_benchmark/data/careerbuilder_loader.py \
          backend/scripts/smoke_test_careerbuilder.py \
          backend/scripts/train_careerbuilder.py \
          backend/results/careerbuilder/ \
          CLAUDE.md \
          specs/009-careerbuilder-benchmark/ \
          specs/006-multi-dataset-benchmark/phases.md \
          .specify/feature.json
  # Optional nếu US2 done: thêm code thay đổi cho hetero
  # Optional nếu T026 phải sửa: thêm benchmark_compare.py
  ```
  **TUYỆT ĐỐI KHÔNG** `git add backend/ml_service/` hoặc `git add -A`.
- [ ] T030 Verify staged sạch: `git diff --cached --stat | grep ml_service` rỗng.
- [ ] T031 Commit bằng heredoc:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat(ml_benchmark): CareerBuilder12 main standard benchmark

  Implements Phase 3 of multi-dataset benchmark on CareerBuilder12 as
  the main standard benchmark cell (per Option B pivot — replacing
  MovieLens which is demoted to validation).

  Reuses Phase 2 infrastructure: Trainer.train_generic(),
  HeteroGraphSAGE.decode_generic(), GPU-vectorized eval, trainable
  nn.Embedding pattern. Only new file is the loader; trainer + model
  unchanged (SC-010 ≥ 70% code reuse confirmed).

  Dataset: jsrshivam/job-recommendation-case-study (Kaggle),
  subsampled to 50K users (seed=42) + k-core=10 (LightGCN convention).
  
  Results: see backend/results/careerbuilder/seed42.json
  Spec: specs/009-careerbuilder-benchmark/spec.md
  Plan: specs/009-careerbuilder-benchmark/plan.md
  EOF
  )"
  ```
- [ ] T032 Verify single commit cho new files: `git log --oneline -- backend/ml_benchmark/data/careerbuilder_loader.py` ra đúng 1 dòng.
- [ ] T033 Verify production history clean: `git log --oneline -- backend/ml_service/ | head -3` không có commit của 009.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Không phụ thuộc. Chạy đầu.
- **Phase 2 (Foundational)**: Phụ thuộc T002 (Kaggle OK). **BLOCK** mọi US.
- **Phase 3 (US1)**: Phụ thuộc Phase 2.
- **Phase 4 (Reproducibility)**: Phụ thuộc US1 PASS.
- **Phase 5 (US2 stretch)**: Phụ thuộc US1 done.
- **Phase 6 (Multi-seed)**: Phụ thuộc US1 PASS.
- **Phase 7 (Commit)**: Cuối cùng.

### Within Each Phase

- **Phase 3 US1**: T007 (loader) → T008 (smoke script) → T009 (sync) → T010 (smoke run) → T011 (train script) → T012 (full train) → T013 (sync result) → T014, T015, T016, T017, T018 (verify) parallel.
- **Phase 4**: T019 → T020 → T021.
- **Phase 5**: T022 → T023 → T024 → T025.
- **Phase 7**: tuần tự.

### Parallel Opportunities

- **Phase 1**: T001 + T002 + T003 ([P]) parallel
- **Phase 3 US1**: T011 ([P]) song song với T010 (chỉ cần T007/T008 xong); T017 + T018 ([P]) parallel
- **Phase 6**: T026 + T028 ([P]) parallel

---

## Parallel Example: Phase 3 US1 verification batch

```bash
Task T014: Verify NDCG@20 ∈ [0.05, 0.30]
Task T015: Verify dataset size ≥ thresholds
Task T016: Verify schema keys
Task T017: git diff backend/ml_service empty
Task T018: Phase 2 regression smoke
```

---

## Implementation Strategy

### MVP First (US1 only, skip US2 + multi-seed)

1. Phase 1 (T001-T003) — 10 min
2. Phase 2 (T004-T006) — 10 min (download dataset)
3. Phase 3 US1 (T007-T018) — 1-2 ngày work + ~1h GPU train
4. Phase 4 reproducibility (T019-T021) — ~1h GPU
5. Phase 7 commit (T029-T033) — 5 min

→ Phase 3 close-able tại đây. Total: ~1-2 ngày.

### Full Phase 3 (US1 + US2 + Multi-seed)

Thêm Phase 5 US2 (~1h GPU) + Phase 6 multi-seed (~2-3h GPU).

Total: ~2-3 ngày (khớp budget SC-008).

---

## Notes

- **Critical invariant T018**: Regression Phase 2 PHẢI pass sau Phase 3 code. Nếu fail = pipeline thay đổi accidentally → rollback T007/T008 ngay.
- **Critical invariant T030**: Trước commit, `git diff --cached | grep ml_service` rỗng.
- **Untracked artifacts** (chủ ý): `_phase2_baseline.txt`, `_smoke_cb_log.txt`, `_hetero_comparison.md`, `seed*_run{1,2}.json` (cho phase reproducibility nếu giữ).
- **Committed evidence**: `backend/results/careerbuilder/seed42.json` (+ run2 + hetero + summary nếu có).
- **No tests requested**: không sinh TDD task. Verify dựa trên smoke + regression + schema assert + reproducibility check.
- **Code reuse target**: T007 loader + T008/T011 scripts là toàn bộ Python mới. Loader ~300 dòng, scripts ~150 dòng mỗi. Tổng < 700 dòng mới — confirm SC-010 ≥ 70% reuse.
- **Server vs local**: train tasks (T010, T012, T019, T024, T027) recommend chạy trên server GPU (Phase 2 setup đã có). Local fallback OK nhưng chậm.
