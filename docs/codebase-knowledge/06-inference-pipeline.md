# Inference / Serving Pipeline

## Tổng quan 2 tầng

```
match_cv(CVData, top_k)                          [engine.py:366-503]
│
├─ STAGE 1 — RETRIEVE (toàn bộ pool ~6.5k jobs)
│   encode CV text 1 lần + lấy CV GNN embedding 1 lần
│   _score_pair_fast mỗi job:
│     base = α·GNN + β·skill + γ·seniority + δ·domain     ← weights từ metadata.json (tuned 019/020)
│       GNN      = 0.6·sigmoid(model.decode) + 0.4·cosine(text)
│       skill    = semantic overlap (importance-weighted, exact + related·0.6)
│       seniority= max(0, 1−|Δsen|·0.4)
│       domain   = _role_domain_fit: 1.0 cùng role / 0.5 job thiếu nhãn / 0.0 lệch
│     × role_match_penalty (1.0/0.7/0.45)
│     × must_have_penalty (thiếu 1/2/3+ required → 0.9/0.75/0.6)
│     × edge_case (CV<4 skills 0.85 · overqualified 0.8 · job sparse 0.8 · chỉ-tool 0.75)
│   → top retrieve_n=200 candidates
│
├─ STAGE 2 — RERANK (nếu reranker đã train)
│   reranker.score_batch_with_dims(23 features, gồm gnn_score/stage1_score)
│   → match_level: ≥0.30 strong / ≥0.22 good / ≥0 weak
│
└─ PENALTIES + FINAL ORDER (021/A3 — mọi candidate)
    penalty_product: experience gate cv_exp < 80%·exp_min → ×0.40 · overqual >3yr → ×0.85
                     seniority gate gap≥2 (hoặc gap≥1 & job senior & cv junior) → ×0.70 · overqual sen≥2 → ×0.75
    rank_score = (reranker_score nếu có, else stage-1 raw) × penalty_product
    THỨ TỰ CUỐI = sort theo rank_score (engine._finalize_results)
    ĐIỂM HIỂN THỊ = rank_score min-max remap vào dải display của result set
                    → monotonic với thứ tự (job #2 không bao giờ % cao hơn #1)
    fallback không reranker: rank = stage-1×penalty = hành vi cũ, không remap
    dim_scores = _dimension_scores (công thức minh bạch, feature 019):
      skill = Σimp(matched)/Σimp(required) · experience = 1−deficit/exp_min
      seniority = 1−|Δ|·0.3 · domain = role match — gate cứng cap 0.15
    eligible = score ≥ 0.65·top
```

**Semantics (chốt ở 021)**: thứ tự cuối = **reranker × penalty gates**; display == order (monotonic by construction). Trước 021, sort cuối theo display stage-1 đã vô hiệu hoá reranker (audit A3).

## Engine lifecycle

- **Singleton/process**: `matching_service._get_engine()` (double-check lock); mỗi lần gọi chạy `maybe_reload_job_pool()` — stat mtime snapshot, rẻ.
- **from_checkpoint** (engine.py:153): load model/graph/cvs/jobs/metadata → **hybrid_weights {α,β,γ,δ} từ metadata.json** (fallback 0.55/0.30/0.15/0) → nếu có snapshot `checkpoints/job_pool/` với `model_sig` khớp → **override pool bằng live catalog** (feature 018).
- **model_signature**: SHA1(state_dict + cv_dim) — gate tin cậy snapshot.

## Job pool live (feature 018)

- `rebuild_job_pool(jobs)` (engine.py:619): thay pool + `_inductive_gnn_encode_jobs` — dựng lại 3 edge types của job (requires_skill/requires_seniority/similar_to — GHI ĐÈ chứ không xoá, metadata model cố định) trên graph CV/skill đông cứng → `model.encode()` 1 lần.
- `snapshot_job_pool` → `job_pool_snapshot.save` (atomic temp-dir swap): jobs.json + job_embeddings.pt + job_text_vecs.npy + meta.json{model_sig}.
- Commands: `rebuild_job_pool` (--limit/--dry-run), bước 1 của `morning_refresh`.

## Các path gọi matching

| Path | LLM? | Dùng cho |
|---|---|---|
| `match_cv_text` / `match_cv_file` | có (LLMCVParser) | API public `/api/matching/cv` |
| `match_cv_data(skills, seniority, exp, text, top_k)` | **không** | employees re-match, eval_matching |
| `rematch_employee` | không — re-extract text từ file CV (500 từ) | rematch_employees, morning_refresh, nút "Refresh jobs" |

`_enrich`: tra `Job` theo pk (live pool) → fallback JDExtractionRecord/LabelingJob (pool đóng băng cũ). `_apply_lifecycle_filter` bỏ job expired.

## Persist (apps/employees/tasks.py)

- `MATCH_TOP_K=100`. `_persist_matches`: resolve Job pk→source_url fallback; upsert (row mới = SUGGESTED, row cũ **giữ status HR**); **prune** SUGGESTED không còn trong top-K mới (giữ engaged + dismissed).
- `EmployeeJobMatch`: match_score, matched/missing_skills, seniority_gap, **dim_scores** (JSON, numeric 0-1), status: suggested→pursuing→applied→won(Accepted)/in_progress→completed/lost(Rejected) + dismissed (ẩn, negative label tương lai).
- Async: Celery `parse_and_match_employee` → fallback thread-pool 3 worker (`_process_employee`, views.py:48) khi không có broker. `rematch` endpoint chạy **sync**.

## Management commands

| Command | Việc |
|---|---|
| `rebuild_job_pool` | catalog → JobData → inductive encode → snapshot |
| `rematch_employees [--employee N]` | re-match (không LLM) |
| `morning_refresh [--no-rebuild --no-digest]` | rebuild pool → rematch all → HR digest |
| `tune_hybrid_weights` | grid 4-weight, dual metric, ablation, --write metadata (xem 07) |
| `eval_matching [--k]` | 20-CV harness → on-domain rate (xem 07) |

## Tối ưu hiệu năng

Precompute CV/job GNN embeddings + job text vecs lúc init · encode CV 1 lần/request · reuse stage-1 GNN scores cho reranker · inductive lock chống encode trùng · mtime hot-reload · atomic snapshot swap. Cold load ~60-90s (embeddings + GNN forward); rebuild pool ~61s/6.5k jobs.

## Cập nhật GNN v2 (024 — 2026-06-11)

- **Checkpoint↔provider phải đồng bộ**: model production train bằng embedding ĐA NGỮ →
  serving bắt buộc `EMBEDDING_PROVIDER=multilingual` trong backend/.env (engine encode CV
  text lúc request bằng provider này). Lệch provider = điểm vô nghĩa âm thầm.
- Weights serving mới: α=0.30/β=0.20/γ=0.10/δ=0.40 (metadata) — GNN gánh tín hiệu thật
  (slice 0.705); domain gate + exp/sen gates giữ nguyên; reranker acc 0.706 (A14-synced,
  guard tự warn nếu lệch).
- Checkpoint loader: strict=False (module train-only như role_head) + model_type-aware
  (graphsage|gat từ metadata train_config).

## Cập nhật 025 (role xác định + hợp nhất đường employee — 2026-06-11)

- **`CVData.role_category`**: role quyết định MỘT LẦN tại nơi tạo CVData — `match_cv_data`
  (employee) suy từ **skills + position**; LLM parser (CV thật) suy từ full text + skills.
  Engine dùng `_cv_role()` (cv.role_category ưu tiên, fallback infer) ở cả 7 vị trí: domain
  term, domain gate, dimension display, CV node one-hot. Trước đó title-regex quét text tổng
  hợp "Skills: react, ..." làm role nhảy fullstack↔frontend tuỳ đường gọi → domain_fit dao
  động 0.7↔1.0 cho CÙNG một employee.
- **Upload ≡ rematch**: sau parse, upload gọi `rematch_employee` (match_cv_data) — bỏ LLM
  call thứ 2 trên text tổng hợp (đường cũ parse lại bằng LLM, output có thể lệch DB).
- **Điểm hiển thị giữa các employee KHÔNG so sánh được** (by design A3): score bị min-max
  remap theo rổ ứng viên riêng của từng CV — "0.77 của người A" không kém "0.92 của người B";
  so sánh đúng phải dùng dim_scores / thứ hạng trong rổ. Nếu cần so chéo → đổi sang
  calibrated probability (chưa làm).

## Cập nhật 025-calibrated (2026-06-12): điểm hiển thị = xác suất tuyệt đối

- **Đã XOÁ remap min-max theo rổ** (`_finalize_results`): hiển thị giờ là
  `PlattCalibrator.transform(rank_score)` — sigmoid đơn điệu ⇒ thứ tự ≡ rank
  bằng toán, không cần cơ chế. Điểm TUYỆT ĐỐI: so sánh được giữa employee, ổn
  định qua các lần chạy. Caveat "không so sánh giữa 2 employee" chính thức hết.
- Ý nghĩa số: P(cặp được ground-truth v4 chấm match≥1) — có điều kiện theo phân
  phối nhãn bucket-selected (framing trung thực, không phải xác suất phổ quát).
- `eligible = P ≥ 0.50` (hằng `ELIGIBLE_MIN_PROB` — "more likely than not";
  thay threshold tương đối 0.65×top). Đo lúc rollout: 76% → 96% trên top-100
  persisted (top-100 của 5.8k vốn toàn match tốt — hợp lý).
- Calibrator: fit sklearn LBFGS (GD cũ không hội tụ — span 0.17 vô dụng) trên
  **rank_score val** (reranker × gates qua CHUNG helper `_penalty_product` với
  serving) trong train_reranker (`--calibrate-only` refit ~2 phút CPU, không
  GPU). Fit gates: a>0 (từ chối nếu nghịch), span≥0.5, reliability per-decile
  ≤0.15 (đo thật: span 0.916, worst gap 0.145).
- Guard (họ A14): `calibration.json.trained_with = sha256(reranker.pt)[:16]` —
  engine WARN lúc boot khi lệch. Thiếu/chưa fit → hiển thị RAW rank + WARN to
  (không bao giờ rơi về remap — đã xoá hẳn).
- score_breakdown thêm `calibrated` (= điểm hiển thị) — chuỗi giải trình khép
  kín: stage1 components → reranker → gates → rank_score → calibrated.
- Đỉnh bão hoà ~0.995 (reranker saturation) → ties hiển thị ở 4dp — chấp nhận.
- Eval persona suites giờ nằm trong repo: `backend/evals/` (holdout/30cv/realcv)
  — /tmp từng bị macOS dọn mất.
