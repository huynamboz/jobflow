# Research: Employee MVP

**Date**: 2026-05-22

## Decisions

### D1: Employee là model riêng, không phải User

**Decision**: New `Employee` model trong `apps.employees`, KHÔNG extend User

**Rationale**:
- Employee không có login → không cần `auth.User` overhead (password, sessions, perms)
- Company quản lý CV của employee như business data
- HR có thể CRUD Employee tự do mà không ảnh hưởng user auth flow

**Alternatives**:
- Use User với role=candidate, no login: confusing, lý do tại sao tạo User mà không login?
- OneToOne User+Profile: overkill, không cần auth

### D2: Reuse admin SPA, không tạo separate frontend

**Decision**: Add Employee/Pipeline pages vào existing `admin/` Vite SPA

**Rationale**:
- Tool internal, không cần SEO/SSR
- 1 maintainer → đỡ context-switch giữa 2 codebase
- HeroUI components đã có sẵn, không cần re-pick
- Auth state shared với admin SPA hiện tại

**Alternatives**: separate Next.js app (overkill cho internal tool — đã bị reject)

### D3: Match status enum — 5 trạng thái

**Decision**: `suggested | pursuing | applied | won | lost`

**Rationale**:
- `suggested`: auto generate từ matching (default sau khi upload CV)
- `pursuing`: HR đánh dấu sẽ apply, đang prep document/email
- `applied`: đã gửi cho employer
- `won` / `lost`: terminal — biết được kết quả từ employer
- 5 states phản ánh đúng pipeline B2B outsource/staffing

**Alternatives**:
- 3 states (saved/applied/closed): mất visibility into "pursuing" prep stage
- 7 states (+ interviewing, offered): premature granularity

### D4: Employee status enum

**Decision**: `bench | pursuing | placed | inactive`

**Rationale**:
- `bench`: sẵn sàng tìm job (default)
- `pursuing`: đang trong pipeline ít nhất 1 job (auto khi có Match.status=pursuing)
- `placed`: đã có job (auto khi Match.status=won)
- `inactive`: nghỉ việc/không còn quản lý

**Rule**: Auto-transition `bench → placed` khi 1 Match thành won; `pursuing → bench` không tự động (HR decide).

### D5: Bulk upload — multi-file picker vs zip

**Decision**: Multi-file picker (HTML5 `<input type=file multiple>`)

**Rationale**:
- Đơn giản UX (chọn file trong Finder/Explorer)
- Browser native, không cần unzip server-side
- Limit 50 files / batch

**Alternatives**:
- ZIP upload: thêm 1 bước extract, error handling cho corrupt zip phức tạp

### D6: CV parsing — sync vs async (Celery)

**Decision**: Async qua Celery task `parse_and_match_employee(employee_id)`

**Rationale**:
- Mỗi CV parse + matching ~30s; 10 files = 5 phút sync block UI
- Async: HR upload xong → record stub tạo ngay → UI hiển thị progress polling
- Status field `is_parse_failed` track failures

**Implementation**: POST `/api/admin/employees/bulk_upload/` → tạo Employee stubs → enqueue tasks → return ids; UI poll GET `/api/admin/employees/?status=parsing` để check tiến độ

### D7: Match score storage

**Decision**: Snapshot `match_score` + `matched_skills` vào EmployeeJobMatch tại thời điểm create

**Rationale**:
- Audit trail (score thay đổi khi retrain model — vẫn giữ snapshot lịch sử)
- Performance: không phải gọi matching API mỗi khi list
- Tradeoff: snapshot có thể outdated → có endpoint "re-score" manual

### D8: Notification opt-in — extend User vs separate model

**Decision**: Add 2 fields trực tiếp vào User (`notify_daily_digest`, `unsubscribe_token`)

**Rationale**:
- Chỉ 2 fields, OneToOne UserProfile overkill
- Migration đơn giản (forward-only)
- Reuse `User.objects.filter(notify_daily_digest=True)` trong task

**Alternatives**: UserProfile OneToOne — đã rejected trong feature trước, lý do tương tự (overkill)

### D9: Digest recipient role

**Decision**: Tất cả User có `role IN (admin, recruiter)` AND `notify_daily_digest=True`

**Rationale**:
- Admin + recruiter đều là "internal staff" trong company
- Filter qua User.role tránh gửi nhầm
- Có thể tinh chỉnh qua admin UI sau

### D10: Unique constraint Employee

**Decision**: Unique on email (nullable, partial index khi email NOT NULL)

**Rationale**:
- Email là natural key cho employee (nếu có)
- Cho phép NULL khi CV không có email
- Partial index: PostgreSQL `WHERE email IS NOT NULL`

**Note**: Bồ thấp hơn ưu tiên: `full_name + cv_file_hash` cũng có thể là idea — defer.

### D11: Authorization model

**Decision**: Custom permission `IsHRStaff` check `role IN (admin, recruiter)`

**Rationale**:
- Existing `IsAdminUser` chỉ accept superuser (Django built-in)
- HR role không phải superuser nhưng cần full access
- Custom permission class trong `apps.employees.permissions`

## Open questions (deferred)

- CV version history (defer to v2)
- Employee photo / avatar (defer)
- Auto re-score khi crawl job mới (defer — manual button đủ MVP)
- Per-employee match notifications (defer — chỉ HR daily digest)
- Multi-tenant (defer — 1 install = 1 company)
