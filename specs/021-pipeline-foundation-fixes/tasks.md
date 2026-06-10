---
description: "Task list — Pipeline Foundation Fixes (Đợt 0)"
---

# Tasks: Pipeline Foundation Fixes (Đợt 0)

**Input**: Design documents from `specs/021-pipeline-foundation-fixes/`
**Prerequisites**: plan.md, spec.md, research.md (decisions R1-R7), data-model.md, contracts/, rubric-tests.md
**Tests**: Unit tests per fix (FR-010). Backend root = `backend/`.

## Format: `[ID] [P?] [Story] Description`
Story map: US1 = clean supervision (0.2) · US2 = ordering (0.3) · US3 = experience fields (0.1) · US4 = per-CV metrics (0.4) · US5 = rubric (0.5) · US6 = job dedup (0.6). Baseline 0.7 = Polish.

---

## Phase 1: Setup

- [ ] T001 Snapshot trạng thái trước fix để so sánh: chạy `eval_matching` ghi log pre-fix (`/tmp/eval_prefix.log`) + xác nhận test suite xanh trên `backend/` (apps.matching, apps.employees, apps.jobs).

---

## Phase 2: User Story 3 — Experience fields về pool (P1, nhỏ nhất, làm trước)

**Goal**: gate kinh nghiệm + experience_fit hoạt động trên pool live.

- [ ] T002 [US3] Sửa `backend/apps/matching/services/matching_service.py::build_jobdata_from_db`: thêm `experience_min=float(job.experience_min or 0.0), experience_max=job.experience_max` vào JobData(...).
- [ ] T003 [US3] Unit test trong `backend/apps/matching/tests.py`: build_jobdata_from_db trả JobData mang experience_min từ Job (tạo Job exp_min=5 → JobData.experience_min==5.0).

---

## Phase 3: User Story 1 — Clean supervision (P1)

**Goal**: export unique per pair; graph từ chối cặp xung đột.

- [ ] T004 [US1] Sửa `backend/export_dataset.py`: dedup HumanLabel per `pair_id` — giữ bản mới nhất (`created_at` DESC, `id` DESC); metadata thêm `dedup: latest_per_pair` + `num_dropped_duplicates` (R1).
- [ ] T005 [US1] Sửa `backend/ml_service/graph/builder.py::build` (label-edge ~L209-229): track seen (cv_idx, job_idx) theo loại; nếu một cặp rơi vào CẢ match lẫn no_match → `raise ValueError` kèm số lượng (R2).
- [ ] T006 [P] [US1] Unit test guard trong `backend/apps/matching/tests.py` (hoặc tests_ml): build với 1 cặp xung đột synthetic → ValueError; không xung đột → pass.
- [ ] T007 [US1] Chạy export thật: `python export_dataset.py --output data/processed/v3_dedup` → verify labels.json unique (cv_idx, job_idx), dropped ≈ 2.9k; build graph từ dataset này không raise (SC-001).

---

## Phase 4: User Story 2 — Ordering nhất quán (P1, đổi hành vi lớn nhất)

**Goal**: final order = reranker × penalty; display monotonic.

- [ ] T008 [US2] Sửa `backend/ml_service/inference/engine.py::match_cv`: tách penalty thành `penalty_product` per candidate (exp ×0.40/×0.85, sen ×0.70, overqual ×0.75 — giá trị giữ nguyên); `rank_score = (reranker_score nếu có else stage1_raw) × penalty_product`; sort cuối theo rank_score; `JobMatchResult.score` = rank_score normalize về display range per-request (min-max trên candidate set map vào dải display stage-1 — R3); fallback không reranker = hành vi cũ.
- [ ] T009 [US2] Unit test monotonicity trong `backend/apps/matching/tests.py`: kết quả match_cv (mock/fixture nhỏ hoặc qua eval path) có scores non-increasing theo thứ tự list.
- [ ] T010 [US2] Cập nhật `docs/codebase-knowledge/06-inference-pipeline.md`: semantics mới (order = reranker×penalty, display==order, fallback) — thay đoạn cũ "điểm hiển thị = stage-1, thứ tự = reranker".

---

## Phase 5: User Story 4 — Per-CV metrics (P2)

- [ ] T011 [US4] Sửa `backend/ml_service/training/trainer.py::_evaluate_split`: group theo cv_id; CV đủ điều kiện (≥1 positive, ≥2 pairs) tính precision@k/recall@k/ndcg@k/mrr/hit_rate trong tập riêng rồi mean; AUC giữ global; thêm `num_cvs_evaluated`; metadata `metrics_mode: per_cv` (R4).
- [ ] T012 [P] [US4] Unit test per-CV metric: fixture 2 CV × vài pairs với ranking biết trước → giá trị mean đúng tay tính; case CV 0 positive bị loại.

---

## Phase 6: User Story 5 — Rubric patches (P2)

- [ ] T013 [US5] Vá `backend/apps/labeling/prompts/pair_scoring.md`: (a) thêm rule `skill_fit=2 AND domain_fit=0 → overall=0`; (b) skill_fit: transferable/equivalent skills tính partial (~half) credit + ví dụ (Flask≈Django, Vue≈React, MySQL≈PostgreSQL, GCP≈AWS, GitLab CI≈Jenkins); (c) bảng domain: mobile↔mobile=2, ba↔ba=2, other↔other=1, mobile↔frontend=1 (R5).
- [ ] T014 [US5] Verify 3 case trong `specs/021-pipeline-foundation-fixes/rubric-tests.md` cho kết quả đúng theo rubric mới (đối chiếu tay từng rule — đây là fixture cho labeler Đợt 1).

---

## Phase 7: User Story 6 — Job dedup (P3)

- [ ] T015 [US6] Tạo `backend/apps/jobs/management/commands/dedup_jobs.py`: group active theo (title, company_id); keeper = row có EmployeeJobMatch engaged (pursuing/applied/won/in_progress/completed/lost) else newest created_at; ≥2 engaged → giữ tất cả engaged + log manual review; losers `is_active=False`; `--dry-run` in kế hoạch đầy đủ (R6).
- [ ] T016 [US6] Serving guard trong `backend/apps/matching/services/matching_service.py` (sau `_enrich`): bỏ row trùng normalized (title, company_name) sau row đầu, áp trong các wrapper match_cv_* trước khi cắt top_k.
- [ ] T017 [P] [US6] Unit test: (a) dedup_jobs giữ row engaged/newest, không đụng engaged; (b) serving guard bỏ trùng (fixture 2 job cùng title+company).
- [ ] T018 [US6] Chạy thật: `dedup_jobs --dry-run` → review → `dedup_jobs` → verify 0 nhóm trùng active, 0 engaged match orphan (SC-006 phần catalog).

---

## Phase 8: Polish & Baseline (0.7)

- [ ] T019 Rebuild pool + adopt: `rebuild_job_pool` → `rematch_employees` → restart server (pool có exp fields + bỏ job deactivated; match lưu adopt ordering mới).
- [ ] T020 Full suite + eval: `manage.py test apps.matching apps.employees apps.jobs` xanh; `eval_matching` → ghi nhận top1_on_domain/on_domain@5 + không lặp title+company trong top-5 (SC-002/003/006/007).
- [ ] T021 Docs baseline: cập nhật `docs/codebase-knowledge/10-master-plan.md` (tick 0.1-0.7 + bảng baseline post-fix), `09-pipeline-audit.md` (đánh dấu A1/A2/A3/A4-A6/A7/A9 FIXED), CLAUDE.md gotcha nếu cần.

---

## Dependencies & Execution Order

- T001 trước hết (snapshot so sánh). US3 (T002-T003) → US1 (T004-T007) → US2 (T008-T010) → US4 (T011-T012) → US5 (T013-T014) → US6 (T015-T018) → Polish (T019-T021).
- US1/US3/US5 độc lập nhau (có thể đảo); US2 nên sau US3 (eval so sánh sạch hơn); US6 trước Polish (rebuild 1 lần).
- [P]: T006, T012, T017 viết test song song với fix kế tiếp.

### MVP
US3 + US1 (supervision sạch + gate sống) là giá trị cốt lõi cho Đợt 1-2; US2 là thay đổi hành vi lớn nhất cho UX.

### Lưu ý rủi ro
- T008 đổi thứ tự user thấy (chủ đích — ghi docs T010).
- T018 đụng DB: bắt buộc `--dry-run` trước, deactivate reversible, không đụng engaged.
