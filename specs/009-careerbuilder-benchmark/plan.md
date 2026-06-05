# Implementation Plan: CareerBuilder12 Main Standard Benchmark

**Branch**: `009-careerbuilder-benchmark` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-careerbuilder-benchmark/spec.md`

## Summary

Tích hợp CareerBuilder12 (CB12) làm **main standard benchmark** thay MovieLens (đã pivot Phase 2 → validation cell). Dataset CB12 từ Kaggle `jsrshivam/job-recommendation-case-study` chứa đúng schema gốc CareerBuilder Challenge 2012: `users.tsv` (35MB), `jobs.tsv` (3.4GB!), `apps.tsv` (75MB), + bonus `user_history.tsv`, `test_users.tsv`, `window_dates.tsv`. Subsample 50K user random → k-core=10 → leave-one-out split per user theo timestamp (chuẩn Phase 2). Reuse 100% infrastructure Phase 2: `Trainer.train_generic()`, GPU-vectorized eval, trainable nn.Embedding.

**Approach**: copy pattern `movielens_loader.py` → `careerbuilder_loader.py`, adapt parser cho TSV format CB12. Bipartite variant (US1 MVP) trước, hetero variant (US2 stretch) sau nếu còn budget. Regression check Phase 2 MovieLens sau khi sửa code.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PyTorch 2.x, PyTorch Geometric (HeteroData), pandas (TSV parsing), kaggle CLI (download). KHÔNG thêm dependency mới — tất cả đã có từ Phase 2.

**Storage**:
- Dataset: `Dataset/careerbuilder-12/` (cache local, gitignored — public dataset, không version)
- Checkpoint: `backend/checkpoints_benchmark/careerbuilder/` (gitignored)
- Kết quả benchmark: `backend/results/careerbuilder/` (committed — evidence luận văn)

**Testing**: Smoke test < 10 phút (FR-012). Regression check: chạy `scripts/smoke_test_movielens.py` (Phase 2) verify metric chệch < 5%.

**Target Platform**: GPU server RTX 3090 24GB (cùng setup Phase 2).

**Project Type**: Python library extension (sandbox).

**Performance Goals**:
- Smoke test: < 10 phút (FR-012)
- Full training: < 6h CPU / < 1h GPU (SC-009)
- Metric NDCG@20 trong [0.05, 0.30] (SC-002)
- Reproducibility tolerance < 0.001 (SC-003)
- Code reuse ≥ 70% từ Phase 2 (SC-010)

**Constraints**:
- KHÔNG đụng `backend/ml_service/` (SC-005)
- KHÔNG break Phase 2 MovieLens (SC-006)
- Sau subsample + k-core: ≥ 10K user × ≥ 5K job × ≥ 50K positive (SC-011)
- 50K user subsample seed=42, fixed (FR-007)

**Scale/Scope**:
- Raw: ~1.6M users × ~380K jobs × ~1.6M apps × 3.6GB disk
- Sau subsample 50K user + k-core=10: ước tính 30-40K user × 50-80K job × ~250K positive
- Số file Python mới: 3 (loader, smoke, full train) — copy pattern Phase 2
- Số file Python sửa: 0 hoặc 1 (trainer chỉ sửa nếu cần adapt CB-specific edge case)

## Constitution Check

Project chưa có constitution chính thức. Nguyên tắc engineering chung:

- **Backward compat**: Không break Phase 2 → PASS (chỉ thêm file mới, không sửa trainer trừ khi cần)
- **Reversibility**: 1 commit revert được → PASS
- **Isolation**: Chỉ thêm trong `backend/ml_benchmark/` + `backend/scripts/` + `backend/results/` → PASS
- **Reproducibility**: Seed fix, version log, subsample seed fix → PASS
- **Comparability**: k-core=10 + LOO chuẩn LightGCN → PASS (so sánh với Phase 2 + paper)

Không violation. Re-evaluation post-design: vẫn PASS.

## Project Structure

### Documentation (this feature)

```text
specs/009-careerbuilder-benchmark/
├── plan.md                          # File này
├── research.md                      # Phase 0 — quyết định dataset source, parser strategy
├── data-model.md                    # Phase 1 — CB12 raw → HeteroData mapping
├── quickstart.md                    # Phase 1 — verify steps cho reviewer
├── contracts/
│   └── careerbuilder_loader_api.md  # Public surface mới của ml_benchmark
├── checklists/
│   └── requirements.md              # Đã tạo ở /speckit-specify
└── tasks.md                         # /speckit-tasks tạo sau
```

### Source Code (repository root)

```text
backend/
├── ml_service/                      # PRODUCTION — bất khả xâm phạm
├── ml_benchmark/                    # SANDBOX (từ 007 + 008)
│   ├── data/
│   │   ├── movielens_loader.py      # (Phase 2, KHÔNG sửa)
│   │   └── careerbuilder_loader.py  # MỚI — Phase 3
│   ├── models/gnn.py                # (KHÔNG sửa — decode_generic đã có từ Phase 2)
│   ├── training/trainer.py          # (KHÔNG sửa trừ khi cần — train_generic đã có từ Phase 2)
│   └── …
├── scripts/
│   ├── smoke_test_careerbuilder.py  # MỚI
│   ├── train_careerbuilder.py       # MỚI (clone pattern train_movielens.py)
│   └── benchmark_compare.py         # (Phase 2, dùng được luôn — chỉ đổi seeds + output path)
├── results/
│   └── careerbuilder/               # MỚI — committed
│       ├── seed42.json
│       ├── seed42_run2.json         # reproducibility
│       ├── seed42_hetero.json       # (nếu làm US2)
│       └── summary.json
│
Dataset/
└── careerbuilder-12/                # MỚI — cache (gitignored qua pattern `Dataset/`)
    ├── apps.tsv
    ├── jobs.tsv
    ├── users.tsv
    ├── user_history.tsv
    ├── test_users.tsv
    └── window_dates.tsv
```

**Structure Decision**: Y hệt pattern Phase 2 — chỉ thay `movielens` → `careerbuilder` ở mọi tên file. Đây là minh chứng "code reuse 70%+".

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none)    | —          | —                                    |

---

## Phase 0 — Outline & Research

Đã hoàn tất ở [research.md](research.md). 8 quyết định kỹ thuật chính:

| ID | Topic | Decision |
|---|---|---|
| R1 | Dataset source | Kaggle `jsrshivam/job-recommendation-case-study` (~766MB compressed, ~3.6GB extracted). Confirmed có đủ schema `users.tsv`, `jobs.tsv`, `apps.tsv`. |
| R2 | Download mechanism | `kaggle datasets download -d jsrshivam/job-recommendation-case-study --unzip` — reuse pattern Phase 2 (đã có Kaggle auth) |
| R3 | TSV parsing | `pandas.read_csv(sep='\t', encoding='ISO-8859-1', on_bad_lines='warn')`. CB12 có nhiều bad row, không strict. |
| R4 | jobs.tsv 3.4GB issue | Stream parse — chỉ giữ cột cần (JobID, StartDate, EndDate, City, State); skip Description text (vì US1 bipartite không cần). Drop sau khi build idx mapping. |
| R5 | Subsample strategy | Random 50K user từ users.tsv (seed=42), filter apps.tsv chỉ giữ tương tác của subset user, sau đó k-core=10 |
| R6 | k-core algorithm | Identical Phase 2 R5 — iterative until converge, drop both user và job < k |
| R7 | LOO split | Identical Phase 2 R6 — sort apps theo `ApplicationDate` per user, last → test, second-last → val, rest → train |
| R8 | Hetero variant (US2) | Defer detail — tentative skill extraction từ `jobs.tsv` Description cột bằng keyword matching từ `skill-alias.json` (reuse từ JobFlow sandbox) |

## Phase 1 — Design & Contracts

Đã hoàn tất:
- [data-model.md](data-model.md): CB12 TSV schema → HeteroData mapping, invariant rules
- [contracts/careerbuilder_loader_api.md](contracts/careerbuilder_loader_api.md): public API của loader mới
- [quickstart.md](quickstart.md): verify procedure cho reviewer

Agent context (CLAUDE.md) đã được cập nhật.

---

## Phase 2 — Tasks (KHÔNG tạo ở /speckit-plan)

`/speckit-tasks` sẽ sinh `tasks.md`. Dự kiến task chính:

1. Setup: `Dataset/careerbuilder-12/` dir + `backend/results/careerbuilder/.gitkeep`
2. Download CB12 via Kaggle (cùng credential Phase 2)
3. Viết `backend/ml_benchmark/data/careerbuilder_loader.py` (copy pattern movielens_loader.py)
4. Viết `backend/scripts/smoke_test_careerbuilder.py`
5. Sync server + chạy smoke
6. Verify metric hợp lý
7. Viết `backend/scripts/train_careerbuilder.py`
8. Chạy full train seed 42 trên server
9. Chạy reproducibility run seed 42 (T014-equivalent)
10. Verify SC-002, SC-003, SC-007, SC-011
11. **REGRESSION**: chạy lại `smoke_test_movielens.py` verify Phase 2 không break
12. (Stretch) US2 hetero variant
13. (Stretch) Multi-seed
14. Phase 6 commit

---

## Re-evaluation post-design

- Backward compat: PASS — chỉ thêm 1 loader file mới
- Reversibility: PASS — 1 commit
- Isolation: PASS — không động ml_service
- Reproducibility: PASS — subsample seed + training seed fix
- Comparability: PASS — k-core=10 + LOO chuẩn

Không cần update Complexity Tracking.
