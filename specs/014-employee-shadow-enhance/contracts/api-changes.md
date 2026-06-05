# Phase 1 Contract: API Changes

Chỉ mô tả **thay đổi** so với #012. Endpoint, auth, phân quyền giữ nguyên (admin/HR/recruiter).

## 1. GET danh sách match của nhân viên — thêm field giải thích (US1)

`GET /api/employees/matches/?employee={id}` (và list match nói chung)

Response item — **thêm** so với hiện tại:
```jsonc
{
  "id": 123,
  "employee": 7,
  "employee_name": "Nguyen Van A",
  "job": { "id": 999, "title": "Senior Backend Engineer", "...": "..." },
  "status": "suggested",
  "match_score": 0.87,
  "matched_skills": ["python", "django", "postgresql"],
  "missing_skills": ["kubernetes", "graphql"],   // MỚI
  "seniority_gap": 1,                              // MỚI: job cao hơn nhân viên 1 bậc (null nếu thiếu data)
  "assigned_to": null,
  "notes": "",
  "applied_at": null, "won_at": null, "lost_at": null,
  "created_at": "...", "updated_at": "..."
}
```
- `missing_skills`: list, có thể rỗng (khớp đủ).
- `seniority_gap`: int hoặc `null`. Dương = job cần cao hơn; 0 = bằng; âm = nhân viên cao hơn yêu cầu.

## 2. PATCH cập nhật trạng thái match — guard apply trùng (US3, US4)

`PATCH /api/employees/matches/{id}/`  body ví dụ `{ "status": "applied" }`

**Hành vi mới khi `status = "applied"`**:
- Nếu job đó đã có match khác ở `applied`/`won` với nhân viên khác **và** request chưa xác nhận:
  - Trả `409 Conflict`:
    ```jsonc
    {
      "success": false,
      "error": {
        "code": "DUPLICATE_APPLY",
        "message": "Job này đã được apply bởi nhân viên khác.",
        "frontman": { "employee_id": 4, "employee_name": "Tran C", "match_id": 88, "status": "applied" }
      }
    }
    ```
  - UI hiển thị cảnh báo + nút xác nhận. Khi HR xác nhận, gửi lại kèm `{"status":"applied","confirm_duplicate": true}` → thực hiện bình thường.
- Nếu không trùng (hoặc đã `confirm_duplicate`) → cập nhật như cũ, set `applied_at`.

**Hành vi mới khi `status = "won"` (US4)**:
- Set `won_at` như cũ.
- **KHÔNG** đổi `Employee.status` sang `placed`. Nhân viên giữ nguyên trạng thái hiện tại.

## 3. GET danh sách nhân viên — badge job mới (US2)

`GET /api/employees/`

- `match_count` (đã có sẵn trong response) = số match `suggested` chưa xử lý của nhân viên → frontend render badge "Y job mới".
- Không đổi contract; chỉ đảm bảo frontend dùng field này.

## 4. Đổi trạng thái nhân viên thủ công (US4)

`PATCH /api/employees/{id}/` body `{ "status": "placed" }`
- Cho phép HR/recruiter đổi thủ công (đánh dấu bận dự án). Không có tác động tự động từ match.

## Tương thích ngược
- Client cũ bỏ qua field mới (`missing_skills`, `seniority_gap`) vẫn chạy.
- Luồng `applied` không trùng và `won` vẫn hoạt động như trước (chỉ bỏ tác dụng phụ auto-placed).
