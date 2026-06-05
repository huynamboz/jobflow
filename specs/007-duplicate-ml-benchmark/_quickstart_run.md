# Quickstart Run Log — 2026-05-21

Reviewer: Claude Code (automated execution via `/speckit-implement`).
Branch: `007-duplicate-ml-benchmark`
Commit: `c865c3f`

| Bước | Tiêu chí | Kết quả |
|---|---|---|
| 2 | Cấu trúc thư mục sandbox đúng | ✅ PASS — 11 module + `crawler/{__init__,base}` chính xác |
| 3 | `backend/ml_service/` git diff rỗng (so với baseline) | ✅ PASS — chỉ có 2 file `verifier/` pre-existing từ baseline, không phải do feature 007 |
| 4 | 0 reference `ml_service` trong sandbox | ✅ PASS — `grep -rn 'from ml_service\|import ml_service' backend/ml_benchmark --include='*.py'` rỗng |
| 5 | 0 file cache trong sandbox | ✅ PASS — `find` ra rỗng |
| 6 | Import sandbox standalone OK | ✅ PASS — `import ml_benchmark.*` 12 module thành công |
| 7 | Load đồng thời cả hai không xung đột | ✅ PASS — `ml_service.__file__` ≠ `ml_benchmark.__file__` |
| 8 | Smoke test chạy hết + metric hợp lý | ✅ PASS — 94s, NDCG@10=0.9266, AUC=0.6550, không NaN |
| 9 | Checkpoint tách biệt | ✅ PASS — `git status backend/checkpoints/` clean; sandbox dir tồn tại nhưng smoke test không save (intentional per R6) |
| 10 | Single commit đúng message | ✅ PASS — commit `c865c3f` chứa "duplicate", "benchmark", "thesis" |

**Tổng kết: 9/9 PASS. Feature 007 ready.**

## Notes phát hiện trong khi thực thi

- Schema JSON `jobs.json` khác với giả định ban đầu trong smoke test (key là `skills`/`experience_min/max`/`salary_min/max`/`role_category`, KHÔNG phải `required_skills`/`required_years_*`). Đã fix smoke test khớp với production loader.
- Script `smoke_test_benchmark.py` cần thêm `sys.path.insert(0, BACKEND_DIR)` ở đầu vì nằm trong `backend/scripts/` (không phải `backend/`) → `import config` (Django settings) sẽ fail nếu không.
- Django startup tự warm-up production inference engine → in nhiều log `ml_service.inference.*` ở đầu output. Đây là hành vi của apps.matching.apps, KHÔNG phải sandbox đang gọi production code.
