# Phase 0 — Research: MovieLens-1M Benchmark Integration

**Date**: 2026-05-21
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

Mỗi mục: **Decision / Rationale / Alternatives**.

---

## R1. Naming strategy — node type `user/movie` vs reuse `cv/job`

**Discovery**: Decoder hiện tại (`MLPDecoder.decode(z_dict, cv_indices, job_indices)`) hardcode tên `cv` và `job` ở 2 chỗ. Trainer.train() signature `(data, dataset, cvs, jobs)`. MovieLens nếu nhồi user vào "cv", movie vào "job" sẽ confusing semantically.

### Decision

**Option A — Generic alias, không rename**:
- HeteroData của MovieLens dùng node type `"user"`, `"movie"` thật sự (không hack thành `cv/job`).
- Decoder thêm method mới `decode_generic(z_dict, src_indices, dst_indices, src_type, dst_type)` không xoá `decode(...)` cũ.
- Trainer thêm method mới `train_generic(data, splits, src_ids, dst_ids, src_type, dst_type, **opts)`.
- Method cũ `Trainer.train(data, dataset, cvs, jobs)` giữ nguyên — JobFlow vẫn dùng được.

### Rationale

- Additive → 0 risk regression cho JobFlow (SC-006).
- Tên `user/movie` đúng semantic, code đọc rõ.
- Decoder code chỉ thêm vài dòng wrapper, không refactor lớn.
- Defer full rename (cv→src, job→dst) sang Phase 6 hoặc dedicated cleanup; không cần thiết cho Phase 2.

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| Option B — Nhồi user vào `"cv"`, movie vào `"job"` | Semantic confusion; người đọc luận văn / code mới sẽ hỏi "tại sao MovieLens dùng cv/job?" |
| Option C — Full rename `cv→src`, `job→dst` toàn sandbox | Diff lớn, rủi ro break JobFlow; vượt phạm vi Phase 2 |
| Option D — Tạo class riêng `MovielensGraphSAGE` không kế thừa | Trùng lặp 90% code; tổn hại "model architecture comparable" trong luận văn |

---

## R2. Vị trí dataset trên disk

### Decision

Cache vào `Dataset/movielens-1m/` ở **repo root**. Cấu trúc:

```
Dataset/movielens-1m/
├── ml-1m.zip              # file gốc (tải từ GroupLens)
└── ml-1m/                 # giải nén
    ├── README
    ├── ratings.dat
    ├── movies.dat
    └── users.dat
```

Thêm pattern `Dataset/movielens-*/` vào `.gitignore` root.

### Rationale

- Repo đã có `Dataset/` ở root (chứa CV PDFs cho thesis); dataset benchmark đặt cùng chỗ ⇒ convention nhất quán.
- MovieLens-1M là public dataset (~30 MB sau giải nén); không cần version trong git, ai cũng tải được.
- Gitignore prefix `movielens-` (không phải `movielens-1m`) để sau Phase 3 nếu thêm CareerBuilder/MovieLens-10M không phải update lại.

### Alternatives considered

- Đặt trong `backend/data/processed/` — sai bản chất (đó là dataset đã processed của JobFlow), confusing.
- Đặt trong `backend/ml_benchmark/data/movielens/` — pollute code dir với artifact runtime.
- Tạo `~/.cache/jobflow-benchmark/` (XDG-style) — không reproducible across machine, khó cho reviewer.

---

## R3. Cơ chế download

### Decision

`urllib.request.urlretrieve()` (stdlib) với:
- Custom hook in progress mỗi 5%.
- Retry tối đa 3 lần với exponential backoff (1s, 2s, 4s).
- Timeout 60s mỗi attempt.
- URL hardcode: `https://files.grouplens.org/datasets/movielens/ml-1m.zip`.

### Rationale

- stdlib → không thêm dep `requests`.
- MovieLens file nhỏ (~5 MB nén), không cần streaming chunk fancy.
- Retry đủ để chịu được flaky network (ví dụ wifi yếu).

### Alternatives considered

- `requests.get(stream=True)` — tốn dep mới, không thực sự cần thiết với 5 MB.
- `torchvision.datasets.MovieLens` — không tồn tại; `torch_geometric.datasets.MovieLens` có nhưng đặt opaque schema không khớp HeteroData của ta.
- Manual download instruction trong quickstart — vi phạm SC-001 ("1 lệnh from scratch to metric").

---

## R4. Validation tải xong

### Decision

Hai-layer validation:

1. **Filesize check**: ml-1m.zip phải có size trong khoảng [5.5 MB, 6.5 MB] (giá trị thực tế là ~5.79 MB; cho khoảng để chịu được nếu GroupLens repackage).
2. **Extract test**: thử `zipfile.ZipFile(...).testzip()` — trả None nếu OK, list file lỗi nếu corrupt.
3. **Post-extract presence check**: 3 file `ratings.dat`, `movies.dat`, `users.dat` phải tồn tại trong `ml-1m/`.

KHÔNG dùng SHA256 hash hardcode vì GroupLens không công bố hash chính thức cho file này, và họ có thể repackage không thay đổi nội dung — hash mismatch sẽ gây false positive.

### Rationale

- Filesize + extract test + presence check là combo rất mạnh: corrupt download sẽ fail extract; partial download fail size check; tampered file gần như không xảy ra (HTTPS).
- Không phụ thuộc hash mà ta không quản lý → tránh maintenance burden.

### Alternatives considered

- Hash SHA256 hardcode — risk false positive nếu GroupLens repack.
- Hash kiểm pre-flight bằng HTTP HEAD content-length — quá phức tạp với benefit nhỏ.

---

## R5. K-core filtering algorithm

### Discovery

Spec FR-005 (sau clarify): k-core = 10. Cần định nghĩa chính xác thuật toán vì có nhiều cách hiểu.

### Decision

**Iterative bipartite k-core**:

```python
def k_core_filter(interactions: list[(user, movie)], k: int = 10) -> list[(user, movie)]:
    while True:
        # Đếm bậc của mỗi user và mỗi movie
        user_deg = Counter(u for u, _ in interactions)
        movie_deg = Counter(m for _, m in interactions)
        # Drop interaction nếu user OR movie có bậc < k
        new = [(u, m) for u, m in interactions
               if user_deg[u] >= k and movie_deg[m] >= k]
        if len(new) == len(interactions):  # converged
            return new
        interactions = new
```

Áp dụng SAU khi lọc rating ≥ 4 (positive only), TRƯỚC khi split.

### Rationale

- Lặp đến converge là chuẩn — drop một user có thể làm movie tụt < 10 inter, phải drop tiếp.
- Đơn giản, complexity O(I * iter) với iter thường < 5 trên MovieLens.
- Khớp đúng implementation của LightGCN (https://github.com/kuandeng/LightGCN/blob/master/Data/preprocessing.py).

### Alternatives considered

- Một lần lọc duy nhất (không lặp) — không đảm bảo invariant "mọi user/movie đều ≥ k inter".
- Networkx k-core API — overkill, thêm dep `networkx`.

---

## R6. Leave-one-out split

### Decision

Per user:
1. Sort interactions theo `timestamp` ascending.
2. Item cuối → test, item áp chót → val, còn lại → train.
3. Nếu sau k-core user có < 3 interactions (về lý thuyết không xảy ra vì k=10, nhưng defensively) → gộp tất cả vào train, không đóng góp vào val/test.

### Rationale

- Chuẩn LightGCN paper §4.1.2.
- Per-user split bảo toàn user signal (mỗi user xuất hiện ở train, có 1 val + 1 test).
- Timestamp-based mô phỏng real-world "predict tương lai từ quá khứ".

### Alternatives considered

- Random split 80/10/10 — không mô phỏng được "future prediction", không khớp paper.
- Leave-N-out (N>1) — tăng data evaluation nhưng giảm training, không cần cho 1M interactions.

---

## R7. Trainer compatibility

### Discovery

`Trainer.train(data, dataset, cvs, jobs)` cần `cvs` và `jobs` lists để build id-to-idx map cho BPR sampling. MovieLens không có `CVData`/`JobData` — chỉ có user_id và movie_id integers.

### Decision

Thêm method mới `Trainer.train_generic`:

```python
def train_generic(
    self,
    data: HeteroData,
    train_pairs: list[tuple[int, int]],   # (src_idx, dst_idx) positive interactions
    val_pairs: list[tuple[int, int]],
    test_pairs: list[tuple[int, int]],
    src_type: str = "user",
    dst_type: str = "movie",
    num_src: int | None = None,            # for negative sampling range
    num_dst: int | None = None,
) -> TrainResult: ...
```

Internal logic:
- Strip label edges nếu có.
- Build model với metadata động (đã hỗ trợ sẵn).
- BPR negative sampling: random dst index từ `[0, num_dst)` cho mỗi pair.
- Loop forward/backward giống `train()` nhưng gọi `decode_generic(z, src, dst, src_type, dst_type)`.
- Evaluate trên val/test bằng cùng metrics module.

Method cũ `train(data, dataset, cvs, jobs)` giữ nguyên — wrapper gọi `train_generic` với `src_type="cv"`, `dst_type="job"` (refactor đó là **optional**, chỉ làm nếu thấy có lợi mà không break test).

### Rationale

- Additive, không break JobFlow.
- Signature mới tự nhiên cho MovieLens (chỉ cần list of (user_idx, movie_idx) pairs).
- Reuse 90% code: model build, optimizer, eval loop chung.

### Alternatives considered

- Refactor `train()` thành generic + adapter — risk break JobFlow.
- Subclass `MovielensTrainer(Trainer)` — vẫn cần generic core function, không khác bản chất.

---

## R8. Smoke test design (MovieLens)

### Decision

`backend/scripts/smoke_test_movielens.py`:

- Tải MovieLens-1M (nếu chưa).
- K-core = 5 (không phải 10 — để tăng tốc dev, ít interaction hơn → graph nhỏ hơn).
- Subsample: chỉ giữ 1000 user random (out of ~6000) để smoke chạy nhanh.
- Train 5 epoch, `hidden_channels = 64` (paper dùng 64, không cần lớn hơn cho smoke).
- In metric, exit 0 nếu chạy hết, không yêu cầu match paper.

Tiêu chí pass:
- Exit 0
- Không exception
- Metric không NaN
- Wall time < 10 phút trên CPU

### Rationale

- Smoke mục tiêu "code không gãy", không phải "model train tốt".
- K-core nhẹ + subsample user là cách standard để dev nhanh.
- Tham số nhỏ tránh OOM hoặc chậm trên dev laptop.

### Alternatives considered

- Full dataset 5 epoch — có thể > 10 phút trên CPU.
- Synthetic mini-dataset không phải MovieLens — không verify được loader.

---

## R9. Regression check JobFlow

### Decision

Sau khi sửa `gnn.py` (decoder alias) và `trainer.py` (train_generic), chạy lại:

```bash
cd backend && python scripts/smoke_test_benchmark.py --epochs 5 --checkpoint-dir checkpoints_benchmark
```

So sánh với baseline log của 007 (`specs/007-duplicate-ml-benchmark/_smoke_test_log.txt` — NDCG@10=0.9266, AUC=0.6550, wall time ~94s).

Tiêu chí pass:
- Wall time chệch < 50% (CPU noise tolerant).
- Mỗi metric chệch < 5% absolute (vd NDCG@10 từ 0.9266 → trong khoảng [0.88, 0.97]).
- Exit code 0.

Document vào `_regression_jobflow.md` (untracked) sau khi chạy.

### Rationale

- SC-006 yêu cầu chệch < 5%.
- Baseline đã có từ 007 → so trực tiếp.
- CPU noise tolerance 50% cho wall time vì macOS có thể thermal throttle.

### Alternatives considered

- Bit-exact check — không khả thi do floating-point on CPU.
- Skip regression — vi phạm SC-006.

---

## R10. Embedding init cho user/movie

### Discovery

MovieLens không có rich features (text/skill). HeteroGraphSAGE cần `data[node_type].x` để forward. Solution: learnable embedding.

### Decision

Trong loader, gán:

```python
data["user"].x = nn.Embedding(num_users, hidden_channels)(torch.arange(num_users)).detach()
data["movie"].x = nn.Embedding(num_movies, hidden_channels)(torch.arange(num_movies)).detach()
```

Init bằng `xavier_uniform_` (chuẩn LightGCN paper §3.1).

**Quan trọng**: Embedding KHÔNG là parameter trainable của model GNN — model GNN sẽ project qua `nn.Linear(hidden_channels, hidden_channels)` trong `HeteroGraphSAGE.projections`. Vì vậy embedding ban đầu là frozen, signal training chảy qua projection layer.

Nếu muốn embedding cũng trainable: chuyển vào `nn.Parameter` và pass qua `nn.Embedding` thực sự trong forward. Defer optimization này — sandbox dev sẽ thấy ngay nếu metric quá thấp.

### Rationale

- Match cách HeteroGraphSAGE expect `data[ntype].x` là tensor.
- Xavier init là chuẩn paper.
- Frozen embedding ban đầu là conservative; có thể nâng cấp nếu cần.

### Alternatives considered

- One-hot encoding — explode memory với 6000 users.
- Random Gaussian init — không khác Xavier nhiều cho purpose này; chọn Xavier để khớp paper.
- Learnable embedding ngay từ đầu — thêm complexity ở Trainer; defer.

---

## Tổng kết

10 quyết định kỹ thuật đã chốt. Tất cả NEEDS CLARIFICATION đã resolved. Sẵn sàng Phase 1.
