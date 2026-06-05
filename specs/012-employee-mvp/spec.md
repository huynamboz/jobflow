---
description: "Internal HR tool — upload employee CVs, find matching jobs, track placement pipeline"
---

# Feature Specification: Employee MVP (internal HR tool)

**Feature Branch**: `012-employee-mvp`
**Created**: 2026-05-22
**Status**: Draft

## Mục đích chung

JobFlow là internal tool cho **một công ty** sử dụng để tìm việc/dự án cho **nhân viên của mình**. Workflow chính:
1. HR/admin upload CV của nhân viên (1 hoặc bulk)
2. Hệ thống parse skills/seniority, match với job catalog (đã crawl)
3. HR thấy top jobs cho từng nhân viên, đánh dấu pursuing/applied
4. HR theo dõi pipeline (bao nhiêu employee đang bench / pursuing / placed)
5. Email digest hằng sáng gửi cho HR/manager: "Hôm nay có X job mới cho Y employees"

**Nhân viên không login vào hệ thống** — họ chỉ là data record do company quản lý.

Auto-decided clarifications (best-practice defaults):
1. **Quy mô**: 1 company, không multi-tenant. Tất cả Employee record thuộc về company duy nhất. (Multi-tenancy defer.)
2. **Roles**: chỉ admin/HR/manager — tất cả thuộc nhóm "internal staff". Re-use existing `User.role` (admin/recruiter/candidate); ánh xạ **recruiter = HR/manager**, admin = quyền cao nhất. Bỏ candidate role registration flow.
3. **CV format**: PDF + DOCX (đã có parser).
4. **CV per employee**: 1 active CV (replace khi upload mới). CV versioning defer.
5. **Match status enum**: `suggested` (auto từ matching) | `pursuing` (HR đánh dấu sẽ apply) | `applied` (đã apply cho khách hàng/employer) | `won` (placed) | `lost` (bị reject).
6. **Employee status**: `bench` (sẵn sàng tìm việc) | `pursuing` (đang trong pipeline 1 job) | `placed` (đã có job) | `inactive` (nghỉ).
7. **Authorization**: tất cả internal user xem được mọi Employee; chỉ admin xóa được; HR/recruiter sửa được.
8. **Email digest recipient**: tất cả user có role admin/recruiter có notification_enabled=true.
9. **Email cadence**: daily 08:00 (Asia/Ho_Chi_Minh).
10. **Bulk upload**: zip file chứa nhiều PDF/DOCX, hoặc multi-file picker (max 50 files / batch).
11. **Match score display**: percentage 0-100 + colored badge (green ≥80, yellow 60-79, gray <60).

---

## User Scenarios & Testing

### US1 (P1): Bulk upload employee CVs + see initial matches

**Persona**: HR Manager — Lê Thị B, phụ trách tìm việc cho 20 software engineers công ty Acme đang trên bench.

**Primary flow**:
1. B đăng nhập với admin/HR account (existing auth)
2. Vào `/admin/employees` → thấy list employees (banner empty nếu chưa có)
3. Click "Add employees" → multi-file picker chọn 10 CV PDF
4. System parse từng CV → tạo 10 Employee records với skills + seniority
5. B thấy list 10 employees mới, mỗi row có badge số match jobs (ví dụ "23 matches")
6. Click vào employee → page chi tiết hiện top 20 jobs với match score
7. B click "Mark as pursuing" trên 5 jobs cho 1 employee → status pipeline cập nhật

**Edge cases**:
- Upload không phải PDF/DOCX → skip + show error per file
- Parse fail cho 1 CV → Employee record vẫn tạo (manual fix sau), flag is_parse_failed
- Duplicate (same name + email) → prompt "merge or create new"
- 0 matches cho employee (skills không match job nào) → empty state, suggest "Add more jobs to catalog or review skills"

**Independent test**: Có thể demo US1 standalone — chỉ cần backend Employee model + matching wired + UI list page.

### US2 (P1): Employee detail + match pipeline tracking

**Persona**: Recruiter — Trần C, theo dõi tiến độ apply jobs cho 1 employee cụ thể.

**Primary flow**:
1. C vào `/admin/employees/[id]` → thấy employee profile + skill list + current status (bench/pursuing/placed)
2. Tab "Matches" → top 30 jobs với match score, filter by status (suggested/pursuing/applied/won/lost)
3. C click "Pursue" trên 1 job → status đổi suggested → pursuing
4. C click "Mark applied" → status đổi pursuing → applied, có thể add notes
5. Sau khi khách hàng phản hồi → C click "Won" hoặc "Lost"
6. Khi 1 employee có job won → status employee auto switch sang "placed", remove khỏi bench list
7. Quay lại `/admin/employees` → status counter cập nhật ("19 on bench, 1 placed")

**Authorization tests**:
- Anonymous request → 401
- Candidate role (nếu có) → 403 (chỉ admin/recruiter mới truy cập được Employee API)
- Recruiter can update status; chỉ admin delete được Employee

**Independent test**: Có thể test US2 sau US1 — cần data Employee + Match records đã có.

### US3 (P1): Global pipeline view + dashboard widget

**Persona**: Admin — Quản lý cấp cao Phạm D, cần overview tất cả pipeline.

**Primary flow**:
1. D vào `/admin/pipeline` → table tất cả EmployeeJobMatch, columns: Employee | Job | Status | Match score | Updated
2. Filter: by employee, by job, by status, by date range
3. Sort: by match score desc, by updated desc
4. D thấy KPI strip: "23 employees on bench | 8 pursuing | 5 applied | 2 won this week | 1 lost"
5. Click "Won this week" → drill down vào list
6. Dashboard chính cũng hiển thị widget mini: same KPI strip

**Independent test**: Cần data đã có từ US1/US2 để render. Có thể seed test data manually.

### US4 (P2): Daily HR email digest

**Persona**: HR team — receives morning brief với matches mới của ngày trước.

**Primary flow**:
1. Mỗi sáng 08:00 (Asia/Ho_Chi_Minh), Celery task tổng hợp:
   - Số job mới crawl được hôm qua
   - Top 10 matches mới (score cao nhất, employee đang bench)
   - Pipeline change: jobs vừa won/lost
2. Render HTML email với sections rõ ràng
3. Send tới tất cả user (admin + recruiter) có `notify_daily_digest = true`
4. Footer có link đi vào `/admin/pipeline` + unsubscribe link

**Edge cases**:
- 0 employees on bench → skip digest
- 0 new matches → vẫn gửi với "No new matches today" placeholder
- SMTP fail → retry 3 lần backoff
- Recipient unsubscribed → skip

**Independent test**: Management command `python manage.py send_hr_digest --user-id X` chạy synchronous, in ra console.

---

## Requirements

### Functional Requirements

**FR-001** Admin/HR có thể upload nhiều CV cùng lúc (PDF/DOCX, max 50 files/batch, mỗi file ≤ 5MB).

**FR-002** Hệ thống parse mỗi CV thành Employee record với fields: name (từ CV hoặc filename), email (optional), skills[], seniority, experience_years, cv_file_path, parsed_at.

**FR-003** Admin/HR có thể edit Employee fields manually (sửa typo từ parser).

**FR-004** Hệ thống tự động tạo EmployeeJobMatch records với status="suggested" cho top K jobs sau khi upload Employee mới.

**FR-005** Admin/HR có thể view list employees với filter (status, skill, seniority) + search by name.

**FR-006** Admin/HR có thể view employee detail với top matched jobs (sorted by score desc).

**FR-007** Admin/HR có thể update EmployeeJobMatch status (suggested → pursuing → applied → won/lost).

**FR-008** Khi Match status = "won", Employee.status auto switch sang "placed".

**FR-009** Admin/HR có thể view global pipeline (`/admin/pipeline`): list tất cả Match, filter + sort.

**FR-010** Dashboard có widget "Pipeline KPI" hiển thị: count by Employee.status + count by Match.status (this week).

**FR-011** API authorization: chỉ user role=admin/recruiter mới access được Employee/Match endpoints; candidate role → 403; anonymous → 401.

**FR-012** Chỉ admin role mới được DELETE Employee.

**FR-013** Hệ thống schedule daily HR email task chạy 08:00 (Asia/Ho_Chi_Minh).

**FR-014** Email digest gửi tới user có `notify_daily_digest=true`, không gửi cho user unsubscribe.

**FR-015** Email HTML responsive, có section: today's new matches, pipeline changes, KPI snapshot, footer với unsubscribe link.

**FR-016** Unsubscribe link → trang xác nhận → set `notify_daily_digest=false`, không cần login.

**FR-017** Existing admin dashboard + matching API + ML inference KHÔNG bị thay đổi behavior.

**FR-018** Existing Django apps (jobs, cvs, matching) KHÔNG bị break — chỉ thêm app mới `employees` + `notifications` + extend User để có notify field.

### Non-Functional Requirements

**NFR-001** Bulk upload 10 CVs xong trong < 60 giây (parse + match suggest, có spinner progress).

**NFR-002** Employee list page load < 2s với 1000 employees (server-side pagination).

**NFR-003** Pipeline page (`/admin/pipeline`) load < 3s với 10k Match records (server-side pagination + indexes).

**NFR-004** Email digest task complete trong 5 phút cho 1k employees + 50 HR recipients.

**NFR-005** Match API authorization tests cover cross-role denials.

**NFR-006** Backward compatible: existing ML production endpoints + admin SPA features KHÔNG bị regression.

---

## Success Criteria

**SC-001** HR upload 10 CVs xong → thấy initial matches trong ≤ 2 phút.

**SC-002** HR có thể track 100% lifecycle: suggested → pursuing → applied → won/lost (no data loss).

**SC-003** Daily digest gửi đúng schedule, open rate có thể đo sau 1 tuần.

**SC-004** Dashboard widget pipeline KPI update realtime (≤ 30s lag) sau khi action.

**SC-005** **ZERO regression** — existing admin SPA (28 pages) + ML matching API + production ml_service không bị broken.

**SC-006** Code coverage ≥ 70% cho new backend apps `employees` + `notifications` (model + view + serializer).

**SC-007** Admin SPA build không tăng > 100KB sau khi thêm Employee pages.

**SC-008** All NEW API endpoints có authorization tests (cross-role denied).

---

## Key Entities

### Employee (NEW, in `backend/apps/employees/`)

- `id`: pk
- `full_name`: str (≤ 200, required)
- `email`: email (optional, indexed)
- `phone`: str (≤ 50, optional)
- `position`: str (≤ 200) — vd "Senior Python Developer"
- `seniority`: int (FK choice từ existing Job.Seniority)
- `experience_years`: float (optional)
- `skills`: text[] hoặc JSON — list canonical skill names parsed từ CV
- `cv_file`: FileField — original PDF/DOCX
- `parsed_at`: datetime
- `is_parse_failed`: bool default False
- `status`: enum `bench | pursuing | placed | inactive`, default `bench`, indexed
- `notes`: text optional
- `created_by`: FK User (HR người upload)
- `created_at`, `updated_at`: auto

### EmployeeJobMatch (NEW)

- `id`: pk
- `employee`: FK Employee
- `job`: FK jobs.Job
- `status`: enum `suggested | pursuing | applied | won | lost`, default `suggested`, indexed
- `match_score`: float (0..1, indexed desc)
- `matched_skills`: text[] hoặc JSON (snapshot from matching)
- `assigned_to`: FK User nullable — HR đang theo dõi match này
- `notes`: text optional (≤ 500 chars)
- `applied_at`, `won_at`, `lost_at`: datetime nullable
- `created_at`, `updated_at`: auto
- **unique constraint**: (employee, job)
- **index**: (employee, status, -match_score)

### User notification preferences (extend existing User)

- `notify_daily_digest`: bool default True
- `unsubscribe_token`: uuid unique (cho one-click unsubscribe)

(Không cần extra UserProfile model — chỉ 2 fields, thêm trực tiếp vào User để đơn giản.)

---

## Out of scope

- Multi-tenant / multi-company (1 install = 1 company)
- Employee self-service portal (employee login, edit CV của mình)
- Recruiter ↔ employer messaging
- Auto-apply (system tự apply jobs)
- LinkedIn outreach automation
- CV version history (chỉ 1 active per employee)
- Skills tagging UI (parser quyết định)
- Recommendation feedback loop (defer)
- Advanced reporting / analytics export
- Multi-language email
- Mobile app
- SSO/SAML/OAuth (defer; basic username/password)

---

## Assumptions

- Existing Django auth + JWT đã work cho admin/HR login
- Existing matching API hỗ trợ batch matching multiple CVs
- CV parser handle PDF + DOCX OK
- Job catalog có ≥ 1k jobs đã crawl
- SMTP credentials sẽ được provide khi deploy
- Celery + Redis được add vào docker-compose
- 1 company duy nhất, không multi-tenant
- Admin SPA dùng Vite + HeroUI + Zustand + axios (đã có)

---

## Dependencies

- Feature 011 thesis-defense-prep đã merge
- Existing Django apps: users, jobs, cvs, matching
- Existing admin SPA infrastructure tại `admin/`
- Existing matching ML pipeline tại `backend/ml_service/`

---

## Risks

| Risk | Mitigation |
|---|---|
| Bulk CV upload chậm (10+ files × 30s parse mỗi cái) | Run async qua Celery task; UI show progress với polling |
| Match generation chậm khi có nhiều employees | Generate match lazy (lần đầu vào employee detail), cache 1h |
| Employee model duplicate (same person 2 CVs) | Unique constraint trên email + warn HR khi upload conflict |
| Celery/Redis chưa có | docker-compose service đã add (kế thừa từ feature trước) |
| Authorization bypass | Cross-role test suite |
| Email regulation | Unsubscribe link, không gửi nếu opt-out |

---

## Notes

- **Internal tool, không public** → bỏ landing page, register, candidate role flow đã làm trong feature trước
- Re-use admin SPA (HeroUI + React Router + Zustand) → không tạo Next.js app riêng
- Bundle: 4 user stories thành 1 feature (US1+US2+US3 P1, US4 P2)
- Autonomous session sẽ implement: backend full + admin UI scaffold + HR digest skeleton
- Polish (production SMTP, Celery beat, E2E) defer
