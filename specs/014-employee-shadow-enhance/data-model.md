# Phase 1 Data Model: Employee Shadow Enhance

Tái sử dụng model #012. Thay đổi tối thiểu, có default an toàn để không phá dữ liệu cũ.

## Employee (apps.employees) — không đổi schema, đổi ngữ nghĩa

| Field | Trạng thái | Ghi chú |
|---|---|---|
| `status` (bench / pursuing / placed) | Giữ nguyên enum | **Đổi ngữ nghĩa**: không còn tự động set `placed` khi thắng job (US4). `placed` trở thành nhãn HR set **thủ công** (đang bận dự án). Mặc định nhân viên ở `bench` kể cả sau khi frontman thắng job. |

State transition sau thay đổi:
- `bench → placed`: chỉ khi HR đổi **thủ công**.
- Thắng một match: **không** tác động `Employee.status`.

## EmployeeJobMatch (apps.employees) — thêm field

| Field | Kiểu | Mặc định | Mục đích |
|---|---|---|---|
| `matched_skills` | JSON list | `[]` | (đã có) kỹ năng khớp |
| **`missing_skills`** | JSON list | `[]` | (MỚI, US1) kỹ năng job yêu cầu mà nhân viên thiếu |
| **`seniority_gap`** | Integer, nullable | `null` | (MỚI, US1) job_seniority − employee_seniority; `null` nếu thiếu dữ liệu |
| `match_score` | Float | — | (đã có) điểm khớp |
| `status` | enum suggested/pursuing/applied/won/lost | `suggested` | (đã có) |
| `applied_at` / `won_at` / `lost_at` | DateTime nullable | `null` | (đã có) mốc thời gian |
| `employee` (FK) | — | — | (đã có) **đóng vai frontman** khi match được apply (US3) |

**Migration**: thêm `missing_skills` (default `[]`) và `seniority_gap` (default `null`) — backward-compatible, không cần backfill bắt buộc (giá trị sẽ được điền khi rescore/ tạo match mới; có thể backfill tuỳ chọn).

**Quy tắc dẫn xuất (khi tạo/rescore match)**:
- `matched_skills`, `missing_skills` lấy từ kết quả pipeline matching (`MatchResult`).
- `seniority_gap = job_required_seniority − employee.seniority` nếu cả hai có giá trị, ngược lại `null`.

## Frontman & guard apply trùng (US3) — không thêm model

- "Frontman của một job" = nhân viên (`employee`) của match đang ở `applied` hoặc `won` cho job đó.
- Guard: khi một match chuyển sang `applied`, tìm match khác cùng `job` có status ∈ {`applied`, `won`} và `employee` khác → đó là trùng; trả thông tin frontman hiện tại để cảnh báo.
- Không cần bảng riêng; truy vấn trên `EmployeeJobMatch` theo `job` + `status`.

## Quan hệ
```
Employee 1 ──< EmployeeJobMatch >── 1 Job
                     │
                     ├─ matched_skills / missing_skills / seniority_gap  (giải thích khớp)
                     └─ status (suggested→pursuing→applied→won/lost)
```
Không tạo entity Contract/Delivery (ngoài phạm vi đợt này).
