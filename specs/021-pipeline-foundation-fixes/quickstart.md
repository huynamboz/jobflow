# Quickstart: Pipeline Foundation Fixes (Đợt 0)

Thứ tự chạy + lệnh verify từng fix. (Code đường dẫn: backend/.)

## 0.1 — experience fields về pool

```bash
cd backend
# sau khi sửa build_jobdata_from_db:
.venv/bin/python manage.py rebuild_job_pool
# verify: job exp_min=5 × CV 1y bị phạt + experience_fit < 1
.venv/bin/python manage.py eval_matching --k 3   # quan sát experience_fit đa dạng (không còn toàn 1.0)
```

## 0.2 — dedup export + guard

```bash
.venv/bin/python export_dataset.py --output data/processed/v3_dedup
# → metadata: num_dropped_duplicates ≈ 2.9k; labels.json unique (cv_idx, job_idx)
.venv/bin/python manage.py test apps.matching   # gồm test guard: cặp xung đột → ValueError
```

## 0.3 — thứ tự cuối + monotonic

```bash
.venv/bin/python manage.py test apps.matching   # test monotonicity
.venv/bin/python manage.py eval_matching        # so sánh trước/sau (ordering đổi là CHỦ ĐÍCH)
```

## 0.4 — per-CV metrics

```bash
# re-evaluate checkpoint hiện tại (không retrain) → số honest:
.venv/bin/python manage.py test apps.matching   # unit test per-CV metric helper
# số per-CV mới ghi vào docs (0.7)
```

## 0.5 — rubric

Đọc `specs/021-pipeline-foundation-fixes/rubric-tests.md` — 3 case phải pass với prompt vá.

## 0.6 — dedup jobs

```bash
.venv/bin/python manage.py dedup_jobs --dry-run   # XEM KẾ HOẠCH trước
.venv/bin/python manage.py dedup_jobs             # deactivate (reversible)
.venv/bin/python manage.py rebuild_job_pool       # pool bỏ job đã deactivate
```

## 0.7 — baseline mới

```bash
.venv/bin/python manage.py eval_matching                     # ghi top1_on_domain + on_domain@5
.venv/bin/python manage.py test apps.matching apps.employees apps.jobs
.venv/bin/python manage.py rematch_employees                 # adopt ordering mới cho match đã lưu
# restart server; cập nhật docs 06/09/10 (checkbox + baseline)
```

## Success signals

- labels.json unique, builder 0 conflict (SC-001)
- list trả về monotonic + theo reranker×penalty (SC-002)
- experience gate sống lại (SC-003) · per-CV metrics hết 1.0 artifact (SC-004)
- 3 rubric case pass (SC-005) · 0 nhóm job trùng active, top-5 không lặp (SC-006)
- baseline mới ghi vào 10-master-plan (SC-007)

## Rollback

- 0.6: `Job.objects.filter(...).update(is_active=True)` (log command in ra id) 
- 0.3: revert commit (ordering cũ) — không ảnh hưởng data
- 0.1: revert + rebuild pool
