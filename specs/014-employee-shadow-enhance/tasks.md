---
description: "Task list for Employee Shadow Enhance"
---

# Tasks: Employee Shadow Enhance

**Input**: Design documents from `/specs/014-employee-shadow-enhance/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-changes.md, quickstart.md

**Tests**: Included cho logic nghiệp vụ then chốt (guard apply trùng, bỏ auto-placed, làm giàu explainability). UI verify thủ công theo quickstart.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Có thể chạy song song (file khác nhau, không phụ thuộc task chưa xong)
- **[Story]**: US1/US2/US3/US4
- Đường dẫn file tương đối từ repo root

## Path Conventions
- Backend: `backend/apps/employees/`, `backend/apps/matching/`
- Admin frontend: `admin/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Không cần khởi tạo mới — feature tái dùng app `employees`/`matching` và admin SPA đã có. Chỉ xác nhận môi trường.

- [x] T001 Xác nhận backend chạy được migration & test (`cd backend && python manage.py migrate --check`) và admin build được (`cd admin && npm run build` hoặc dev server) trên branch `014-employee-shadow-enhance`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema mở rộng cho explainability — chặn US1. Backward-compatible (default an toàn).

- [x] T002 [P] Thêm field `missing_skills` (JSONField default=list) và `seniority_gap` (IntegerField null=True, blank=True) vào model `EmployeeJobMatch` trong `backend/apps/employees/models.py`
- [x] T003 Tạo migration cho field mới: `cd backend && python manage.py makemigrations employees` → review file trong `backend/apps/employees/migrations/`

**Checkpoint**: Migration tạo xong, `migrate` chạy không lỗi trên DB hiện có.

---

## Phase 3: User Story 1 — Lý do khớp / Explainability (Priority: P1)

**Goal**: HR thấy kỹ năng khớp/thiếu + chênh cấp bậc cho từng job trên màn chi tiết nhân viên.

**Independent Test**: Mở `/admin/employees/{id}` → mỗi job hiện matched/missing skills + seniority gap (quickstart US1).

### Backend
- [x] T004 [US1] Làm giàu adapter `match_employee_to_jobs` trong `backend/apps/employees/matching.py`: truyền `missing_skills` từ kết quả pipeline (`MatchResult` đã có sẵn field này) bên cạnh `matched_skills`/`score`
- [x] T005 [US1] Tính `seniority_gap = job_required_seniority − employee.seniority` (null nếu thiếu dữ liệu) trong `backend/apps/employees/matching.py`; xác định nguồn cấp bậc yêu cầu của job (field trên `Job`)
- [x] T006 [US1] Khi tạo/rescore match (nơi `EmployeeJobMatch` được ghi — `matching.py`/`tasks.py`), lưu `missing_skills` và `seniority_gap` vào record
- [x] T007 [US1] Expose `missing_skills` và `seniority_gap` trong `EmployeeJobMatchSerializer` (`backend/apps/employees/serializers.py`), đặt read-only
- [x] T008 [P] [US1] Test backend: match mới/rescore có `missing_skills` và `seniority_gap` đúng; job khớp đủ → `missing_skills` rỗng (`backend/apps/employees/tests.py`)

### Frontend
- [x] T009 [P] [US1] Thêm `missing_skills: string[]` và `seniority_gap: number | null` vào interface `EmployeeJobMatch` trong `admin/src/types/match.types.ts`
- [x] T010 [US1] Panel "Vì sao khớp" trong `admin/src/pages/admin/employees/detail.tsx`: chip xanh cho matched skills, chip đỏ cho missing skills, dòng diễn giải seniority_gap (vd "job cần Senior, nhân viên Mid"); xử lý null = "chưa đủ dữ liệu"

**Checkpoint**: US1 demo được độc lập.

---

## Phase 4: User Story 2 — Badge "Y job mới" (Priority: P1)

**Goal**: Danh sách nhân viên hiện số job match mới (`suggested`) chưa xử lý.

**Independent Test**: `/admin/employees` hiện badge "N job mới"; chuyển 1 match khỏi `suggested` → badge giảm (quickstart US2).

- [x] T011 [US2] Xác nhận `match_count` (annotate `Count(matches, status="suggested")`) vẫn đúng trong `backend/apps/employees/views.py` `get_queryset` và được expose ở `EmployeeListSerializer` (`backend/apps/employees/serializers.py`) — đã có sẵn, kiểm tra không thoái lui
- [x] T012 [US2] Render badge "N job mới" trên mỗi dòng nhân viên trong `admin/src/pages/admin/employees/index.tsx` dùng `match_count`; ẩn badge khi = 0
- [x] T013 [P] [US2] Đảm bảo type `Employee` (list) trong `admin/src/types/employee.types.ts` có `match_count: number`

**Checkpoint**: US2 demo được độc lập.

---

## Phase 5: User Story 3 — Chặn apply trùng (Priority: P1)

**Goal**: Cảnh báo khi apply một job đã có frontman khác.

**Independent Test**: NV1 apply job A → ok; NV2 apply cùng job A → cảnh báo nêu frontman (quickstart US3).

### Backend
- [x] T014 [US3] Trong `perform_update`/`update` của match view (`backend/apps/employees/views.py`), khi `status → applied`: tìm match khác cùng `job` có status ∈ {applied, won} và employee khác; nếu có và chưa `confirm_duplicate` → trả `409 DUPLICATE_APPLY` kèm thông tin frontman (theo `contracts/api-changes.md`)
- [x] T015 [US3] Hỗ trợ tham số `confirm_duplicate` (body) để bỏ qua cảnh báo và apply bình thường; set `applied_at` như cũ
- [x] T016 [P] [US3] Test backend: apply trùng trả 409 + frontman đúng; apply với `confirm_duplicate=true` thành công; apply job chưa ai apply thành công (`backend/apps/employees/tests.py`)

### Frontend
- [x] T017 [US3] Trong `admin/src/services/match.service.ts` + `detail.tsx`: bắt lỗi 409 `DUPLICATE_APPLY`, hiện modal cảnh báo nêu frontman hiện tại, nút "Vẫn apply" → gửi lại kèm `confirm_duplicate: true`

**Checkpoint**: US3 demo được độc lập.

---

## Phase 6: User Story 4 — Bỏ auto-placed (Priority: P1)

**Goal**: Thắng job KHÔNG tự đổi trạng thái nhân viên; cho phép đổi thủ công.

**Independent Test**: Job → won, NV vẫn `bench`; đổi `placed` thủ công vẫn được (quickstart US4).

- [x] T018 [US4] Gỡ nhánh `if new_status == "won": employee.status = PLACED` (`backend/apps/employees/views.py` ~dòng 132–138); giữ set `won_at`
- [x] T019 [US4] Đảm bảo `EmployeeSerializer` cho phép HR/recruiter PATCH `status` thủ công (kiểm tra writable + phân quyền) trong `backend/apps/employees/serializers.py` + `views.py`
- [x] T020 [P] [US4] Test backend: chuyển match sang won → `Employee.status` không đổi; PATCH status thủ công sang `placed` thành công (`backend/apps/employees/tests.py`)

**Checkpoint**: US4 demo được độc lập.

---

## Phase 7: Polish & Cross-Cutting

- [x] T021 [P] Chạy toàn bộ test backend `cd backend && python manage.py test apps.employees` — pass
- [x] T022 [P] Verify regression #012 theo `quickstart.md` (upload, parse, digest, global pipeline) — không thoái lui
- [ ] T023 [P] (Tùy chọn) Backfill `missing_skills`/`seniority_gap` cho match cũ qua rescore hoặc data migration nhẹ
- [x] T024 Cập nhật `roadmap/business-functions-hr-staffing.md` + `roadmap/workflow-and-screens.md`: đánh dấu các mục P1 đã chuyển 🔴→✅

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational, chặn US1)** → các user story.
- **US1** phụ thuộc Phase 2 (migration). **US2, US3, US4** độc lập với US1 và với nhau (đều sửa file khác nhau hoặc cùng `views.py` ở nhánh khác).
- **US4** nhỏ nhất & gốc rễ — có thể làm trước tiên để sửa mâu thuẫn ngay (chỉ cần Setup).
- **US3 & US4** cùng đụng `views.py` → làm tuần tự để tránh xung đột merge, không song song.

### Thứ tự khuyến nghị
T001 → T002–T003 → **US4** (T018–T020) → **US1** (T004–T010) → **US2** (T011–T013) → **US3** (T014–T017) → Polish (T021–T024).

### Song song được ([P])
- T008, T009 (US1 test + type) song song nhau.
- T013 (US2 type) song song với backend US2.
- T016 (US3 test) song song với frontend US3.
- T021–T023 (polish) song song nhau.

## Implementation Strategy

- **MVP tối thiểu**: US4 + US1 (sửa mâu thuẫn + explainability) — đã đủ giá trị cho luồng "xem CV → quyết apply".
- **Tăng dần**: thêm US2 (badge) đóng vòng luồng sáng, rồi US3 (guard) chốt an toàn nghiệp vụ shadow.
- Mỗi user story là một lát cắt demo được độc lập.

**Tổng: 24 task** — US1: 7 · US2: 3 · US3: 4 · US4: 3 · Setup/Foundational: 3 · Polish: 4.
