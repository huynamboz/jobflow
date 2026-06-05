# Phase 1 — Data Model: Module Mapping

**Date**: 2026-05-21
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

Feature này không tạo dữ liệu nghiệp vụ mới (không có DB schema, không có API entity). "Data model" ở đây là **bảng mapping module gốc → module sandbox**, vì đó chính là cấu trúc dữ liệu chính của output (cây thư mục `backend/ml_benchmark/`).

---

## E1. Bảng mapping module

| Module gốc (`backend/ml_service/…`) | Policy | Module sandbox (`backend/ml_benchmark/…`) | Lý do |
|---|---|---|---|
| `__init__.py` | **Rewrite** | `__init__.py` | Docstring nguyên gốc nhắc `inference/crawler/cv_parser/reranker` — sửa lại để chỉ liệt kê module sandbox còn giữ. |
| `graph/` | **Copy đầy đủ** | `graph/` | Core. Sandbox cần để build HeteroData. |
| `models/` | **Copy đầy đủ** | `models/` | Core. Chứa `HeteroGraphSAGE`, `HeteroRGCN`. |
| `training/` | **Copy đầy đủ** | `training/` | Core. Chứa trainer + BPR loss orchestration. |
| `evaluation/` | **Copy đầy đủ** | `evaluation/` | Core. Metrics (NDCG, Recall, AUC). |
| `baselines/` | **Copy đầy đủ** | `baselines/` | BM25 / Cosine / SkillOverlap — đối thủ để so sánh. |
| `data/` | **Copy đầy đủ** | `data/` | Loader, labeler, generator, skill normalization. |
| `embedding/` | **Copy đầy đủ** | `embedding/` | Sentence embedding provider — CareerBuilder sẽ cần. |
| `config/` | **Copy đầy đủ** | `config/` | Settings, default constants. |
| `utils/` | **Copy đầy đủ** | `utils/` | Helper functions. |
| `crawler/base.py` | **Copy file đơn lẻ** | `crawler/base.py` | Exception R1: `data/skill_extractor.py` import `RawJob` từ đây. |
| `crawler/__init__.py` | **Rewrite rút gọn** | `crawler/__init__.py` | Chỉ giữ `from ml_benchmark.crawler.base import RawJob`; bỏ re-export các provider không copy. |
| `cv_parser/` | **Copy đầy đủ** | `cv_parser/` | Exception R1: `data/linkedin_cv_loader.py` import `CVParser`. |
| `crawler/factory.py` | **Strip** | — | Không cần (crawler logic chỉ liên quan ingest, không liên quan benchmark). |
| `crawler/scheduler.py` | **Strip** | — | Production crawler scheduler — không thuộc benchmark. |
| `crawler/storage.py` | **Strip** | — | Persistence layer crawler — không thuộc benchmark. |
| `crawler/providers/` | **Strip** | — | LinkedIn/Adzuna/RemoteOK/JobSpy/Remotive — production-only. |
| `crawler/README.md` | **Strip** | — | Doc về crawler production, không liên quan. |
| `verifier/` | **Strip** | — | Job-verifier (sản phẩm production), không thuộc benchmark. |
| `inference/` | **Strip** | — | InferenceEngine cho production API. |
| `reranker/` | **Strip** | — | Production reranker (đã có model + Platt calibration cho serve). |
| `api/` | **Strip** | — | HTTP API layer. |
| `__pycache__/` | **Strip** | — | FR-012 + SC-007. |
| `*.pyc` | **Strip** | — | Same as above. |
| `.pytest_cache/` (nếu có) | **Strip** | — | Same. |

---

## E2. Rule rewrite import

Áp dụng cho mọi `.py` trong `backend/ml_benchmark/`:

| Pattern gốc | Pattern sau rewrite | Ghi chú |
|---|---|---|
| `from ml_service.X import Y` | `from ml_benchmark.X import Y` | Trường hợp phổ biến nhất. |
| `from ml_service import X` | `from ml_benchmark import X` | |
| `import ml_service.X as Z` | `import ml_benchmark.X as Z` | |
| `import ml_service` | `import ml_benchmark` | Hiếm gặp. |
| String literal `"ml_service"` trong docstring / comment / log message | **Giữ nguyên** (review thủ công) | Đôi khi reference có chủ ý. Sẽ duyệt sau khi verify grep. |

**Regex sed**: `s/(^|[^a-zA-Z_])ml_service([.\b])/\1ml_benchmark\2/g` — chỉ bắt khi `ml_service` đứng giữa boundary token, tránh false match như `my_ml_service_name` (không tồn tại trong codebase nhưng đề phòng).

---

## E3. Invariant rules

| Rule | Kiểm chứng |
|---|---|
| R-INV-1: 0 file trong `backend/ml_service/` bị thay đổi | `git diff --stat backend/ml_service/` ra rỗng. |
| R-INV-2: 0 reference tới `ml_service` (import statement) trong `backend/ml_benchmark/` | `grep -rn "from ml_service\|import ml_service" backend/ml_benchmark --include='*.py'` ra rỗng. |
| R-INV-3: Mọi module sandbox import được mà không lỗi | `python -c "import ml_benchmark.training; import ml_benchmark.models; import ml_benchmark.evaluation; import ml_benchmark.baselines; import ml_benchmark.graph; import ml_benchmark.data; import ml_benchmark.embedding"` exit 0. |
| R-INV-4: Cả production và sandbox load đồng thời | `python -c "import ml_service; import ml_benchmark; assert ml_service.__file__ != ml_benchmark.__file__"` exit 0. |
| R-INV-5: Sandbox không có cache | `find backend/ml_benchmark -name __pycache__ -o -name '*.pyc' -o -name .pytest_cache` ra rỗng. |
| R-INV-6: Sandbox commit là single commit | `git log --oneline backend/ml_benchmark/` đúng 1 dòng tại thời điểm hoàn thành. |

---

## E4. State transitions

Sandbox không có runtime state. State transition duy nhất là **lifecycle của thư mục `ml_benchmark/`**:

```
[không tồn tại]
      │
      │ (script duplicate_ml_service.sh chạy thành công)
      ▼
[duplicated — chưa rewrite]
      │
      │ (cleanup cache + strip modules)
      ▼
[stripped]
      │
      │ (rewrite imports)
      ▼
[ready — pass R-INV-2..R-INV-5]
      │
      │ (single commit)
      ▼
[committed — pass R-INV-6]
      │
      │ (smoke test pass)
      ▼
[verified — DONE]
```

Lỗi ở bất kỳ bước nào → rollback bằng `rm -rf backend/ml_benchmark/` + chạy lại script. Production không bị động trong mọi tình huống (R-INV-1 luôn pass vì không có thao tác ghi vào `ml_service/`).
