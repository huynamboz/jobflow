# Implementation Plan: MovieLens-1M Benchmark Integration

**Branch**: `008-movielens-benchmark` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-movielens-benchmark/spec.md`

## Summary

Mở rộng sandbox `backend/ml_benchmark/` (do feature 007 tạo) để train HeteroGraphSAGE trên MovieLens-1M, sinh metric NDCG@20 / Recall@20 / HR@20 / MRR cùng order of magnitude với LightGCN paper (Recall@20 ≈ 0.26, NDCG@20 ≈ 0.22). Trọng tâm là (a) viết loader MovieLens-1M với k-core=10 preprocessing và leave-one-out split, (b) tạo thin "adapter" cho loader/trainer chấp nhận dataset có schema khác CV/Job, (c) train + report metric vào file kết quả copy-paste-able. KHÔNG đụng `backend/ml_service/`; KHÔNG break smoke test JobFlow của 007.

**Approach kỹ thuật**: Reuse tối đa code 007 — `HeteroGraphSAGE` đã chấp nhận `node_dims` động (chỉ default hardcode), `Trainer.train()` chạy được trên metadata bất kỳ. Đụng độ duy nhất là **naming**: decoder/Trainer dùng `cv_indices`/`job_indices` và arg `cvs/jobs`. Giải pháp tối thiểu xâm phạm: (1) thêm method `Trainer.train_generic(data, splits, src_ids, dst_ids, src_type, dst_type)` không thay thế method cũ, (2) đổi decoder accept generic `src/dst` indices nhưng giữ alias `cv/job` cho backward-compat. Loader MovieLens map user→"user" node type, movie→"movie" node type — trực tiếp, không lừa naming.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PyTorch 2.x, PyTorch Geometric (HeteroData, GraphSAGE, to_hetero), NumPy, pandas (đọc `ratings.dat`), requests (download). Tất cả đã có trong env hiện tại; không thêm dependency mới.

**Storage**:
- Dataset: `Dataset/movielens-1m/` (cache local, gitignored — public dataset, không cần version)
- Checkpoint: `backend/checkpoints_benchmark/movielens/` (gitignored, thừa hưởng `.gitignore` của 007)
- Kết quả benchmark: `backend/results/movielens/` (mới — sẽ commit để có evidence cho luận văn)

**Testing**: Smoke test script chạy 5 epoch < 10 phút (FR-011). Regression check: chạy lại `backend/scripts/smoke_test_benchmark.py` của 007, kiểm metric JobFlow chệch < 5% (SC-006).

**Target Platform**: macOS Apple Silicon CPU (dev), tùy ý Linux CUDA (full train). Code phải tự pick device qua `_get_device()` đã có.

**Project Type**: Python library extension (sandbox); không có frontend/mobile.

**Performance Goals**:
- Smoke test (5 epoch): < 10 phút trên CPU (FR-011)
- Full training (max 500 epoch + early stop patience 50): < 6 giờ CPU hoặc < 1 giờ GPU (SC-009)
- Đạt metric trong cùng order of magnitude LightGCN paper (SC-002)

**Constraints**:
- KHÔNG đụng `backend/ml_service/` (SC-005)
- Generalize HeteroGraphSAGE phải backward-compat — JobFlow smoke test pass với chệch < 5% (SC-006)
- Reproducibility: cùng seed → metric bit-identical (SC-003)

**Scale/Scope**:
- MovieLens-1M raw: ~6,000 users × ~3,700 movies × ~1M ratings
- Sau k-core=10: ước tính ~5,900 users × ~3,400 movies × ~575K positive interactions (tham khảo LightGCN paper Table 1)
- Số file Python mới ước tính: 4-6 file trong `backend/ml_benchmark/data/` + `backend/scripts/`
- 1 commit chính cho Phase 2

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Project chưa có constitution chính thức ([.specify/memory/constitution.md](../../.specify/memory/constitution.md) vẫn template). Áp dụng nguyên tắc engineering chung:

- **Backward compatibility**: Generalize HeteroGraphSAGE không được break JobFlow → PASS (giải pháp thêm method mới, không thay đổi signature cũ).
- **Reversibility**: Phase 2 có thể revert bằng `git revert` đơn lẻ → PASS (chủ yếu thêm file mới trong sandbox).
- **Isolation**: Không đụng production → PASS (mọi thay đổi trong `backend/ml_benchmark/` + `backend/scripts/` + `backend/results/`).
- **Reproducibility**: Có yêu cầu cụ thể (SC-003, FR-009, FR-010) + seed + version log → PASS.
- **Comparability**: Áp dụng k-core=10 chuẩn LightGCN paper → PASS (SC-002 khả thi).

Không violation cần justify. Re-evaluation sau Phase 1: vẫn PASS — design không phát sinh shared state hay coupling mới.

## Project Structure

### Documentation (this feature)

```text
specs/008-movielens-benchmark/
├── plan.md                          # File này
├── research.md                      # Phase 0 — quyết định kỹ thuật
├── data-model.md                    # Phase 1 — entity + schema mapping
├── quickstart.md                    # Phase 1 — quy trình verify cho reviewer
├── contracts/
│   └── ml_benchmark_extension.md    # Phase 1 — public surface bổ sung cho ml_benchmark
├── checklists/
│   └── requirements.md              # Đã tạo ở /speckit-specify
└── tasks.md                         # /speckit-tasks tạo sau
```

### Source Code (repository root)

```text
backend/
├── ml_service/                      # PRODUCTION — bất khả xâm phạm
│   └── …                            # (không thay đổi)
│
├── ml_benchmark/                    # SANDBOX (từ 007), Phase 2 thêm/sửa:
│   ├── data/
│   │   ├── movielens_loader.py      # MỚI — download + k-core + LOO split + HeteroData
│   │   └── splits.py                # MỚI (optional) — generic split utilities
│   ├── models/
│   │   └── gnn.py                   # SỬA (additive) — decoder support src/dst alias
│   ├── training/
│   │   └── trainer.py               # SỬA (additive) — thêm train_generic()
│   └── evaluation/
│       └── metrics.py               # (kiểm tra) — bổ sung @20 metric nếu chưa có
│
├── scripts/
│   ├── duplicate_ml_service.sh      # (007)
│   ├── smoke_test_benchmark.py      # (007) — dùng làm regression check
│   ├── smoke_test_movielens.py      # MỚI — 5 epoch quick verify
│   ├── train_movielens.py           # MỚI — full train + report
│   └── benchmark_compare.py         # MỚI (optional) — chạy nhiều seed, gộp mean±std
│
├── results/                         # MỚI — committed (evidence cho luận văn)
│   └── movielens/
│       ├── seed42.json              # Mỗi seed một file
│       └── summary.json             # Mean ± std qua các seed
│
├── checkpoints_benchmark/           # (007, gitignored)
│   └── movielens/                   # MỚI subdir
│
Dataset/
└── movielens-1m/                    # MỚI — cache (gitignored)
    ├── ml-1m.zip
    └── ml-1m/                       # giải nén
        ├── ratings.dat
        ├── movies.dat
        └── users.dat
```

**Structure Decision**:
- **`results/movielens/` được commit** (khác `checkpoints_benchmark/`) — vì kết quả benchmark là evidence cho luận văn, cần lưu trong git.
- **`Dataset/movielens-1m/` không commit** — public dataset, ai cũng tải được; commit thì làm phình repo (~30 MB).
- **MovieLens loader nằm trong `data/`** ngang hàng với `linkedin_cv_loader.py` của JobFlow — giữ pattern hiện có, không tạo thư mục `datasets/` mới (YAGNI cho Phase 2; nếu Phase 3 CareerBuilder cần thì refactor sau).
- **Decoder generalization là additive** (thêm alias `src/dst` chứ không rename `cv/job`) → JobFlow vẫn chạy nguyên.

## Complexity Tracking

Không có violation Constitution Check ⇒ bảng để trống.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none)    | —          | —                                    |

---

## Phase 0 — Outline & Research

Đã hoàn tất ở [research.md](research.md). Tóm tắt 10 quyết định kỹ thuật:

| ID | Topic | Decision |
|---|---|---|
| R1 | Naming strategy cho user/movie vs cv/job | **Option A**: dùng node type `"user"` / `"movie"` riêng; decoder thêm alias `src/dst` (additive, không rename cv/job) |
| R2 | Vị trí dataset trên disk | `Dataset/movielens-1m/` (gitignored, public dataset) |
| R3 | Cơ chế download | `urllib.request.urlretrieve` (stdlib, không thêm dep), với progress + retry |
| R4 | Validation tải xong | SHA256 checksum (hardcode hash chính thức của ml-1m.zip = `c4d9eecfca2ab87c1945afe126590906ca465011` — confirm khi implement) + extract test |
| R5 | K-core filtering | Iterative until convergence: lặp drop user < 10 inter + drop movie < 10 inter cho đến khi cả hai stable |
| R6 | Leave-one-out split | Sort interactions theo timestamp per user, lấy cuối → test, áp chót → val, còn lại → train |
| R7 | Trainer compatibility | Thêm method `Trainer.train_generic()` chấp nhận `src_ids`, `dst_ids`, `src_type`, `dst_type`; method cũ `train()` giữ nguyên cho JobFlow |
| R8 | Smoke test design | 5 epoch, k-core nhẹ hơn (=5) để tăng tốc dev; in metric, exit code 0 nếu chạy hết, không yêu cầu match paper |
| R9 | Regression check JobFlow | Tự động chạy lại `smoke_test_benchmark.py` sau khi sửa decoder; compare metric với baseline log của 007 |
| R10 | Embedding init cho user/movie | `nn.Embedding(num_x, hidden_channels)` với init `xavier_uniform` (chuẩn LightGCN), gắn vào sandbox model qua node feature `x` shape `(num_users, hidden_channels)` |

## Phase 1 — Design & Contracts

Đã hoàn tất. Output:

- [data-model.md](data-model.md) — schema mapping MovieLens raw → HeteroData; entity + relationship + invariants
- [contracts/ml_benchmark_extension.md](contracts/ml_benchmark_extension.md) — public surface mới của ml_benchmark sau khi extend (movielens_loader, train_generic, decoder alias)
- [quickstart.md](quickstart.md) — quy trình verify 10 bước cho reviewer

Agent context (CLAUDE.md) đã được cập nhật ở step Phase 1.3.

---

## Phase 2 — Tasks (KHÔNG tạo ở /speckit-plan)

`/speckit-tasks` sẽ sinh `tasks.md` từ artifacts trên. Dự kiến các task chính:

1. Viết `backend/ml_benchmark/data/movielens_loader.py` (download + k-core + split + HeteroData)
2. Sửa `backend/ml_benchmark/models/gnn.py` thêm decoder alias `src/dst`
3. Sửa `backend/ml_benchmark/training/trainer.py` thêm `train_generic()`
4. (Nếu cần) Bổ sung metric @20 trong `evaluation/metrics.py`
5. Viết `backend/scripts/smoke_test_movielens.py`
6. Chạy smoke test MovieLens → verify
7. Chạy regression check `smoke_test_benchmark.py` (JobFlow) → verify SC-006
8. Viết `backend/scripts/train_movielens.py` (full train + multi-seed)
9. Chạy full train 3 seed → sinh `results/movielens/seedN.json`
10. (Optional) `benchmark_compare.py` gộp summary
11. Verify SC-002 (metric trong order of magnitude paper) + SC-007 (file format đúng)
12. Stage + commit (1 commit chính + commit kết quả tách riêng nếu muốn)

---

## Re-evaluation post-design

- **Backward compatibility**: PASS — decoder + Trainer chỉ thêm method mới, không sửa method cũ
- **Reversibility**: PASS — phần additive có thể revert; loader mới là file riêng
- **Isolation**: PASS — chỉ thêm/sửa trong `backend/ml_benchmark/`, `backend/scripts/`, `backend/results/`
- **Reproducibility**: PASS — quyết định ở R5-R10 đều có algorithm cụ thể, không phụ thuộc môi trường

Không cần update Complexity Tracking.
