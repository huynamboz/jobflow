# Quickstart: Verify Employee Shadow Enhance

Cách kiểm chứng nhanh từng user story sau khi triển khai. Giả định backend + admin đang chạy với dữ liệu #012 (có nhân viên + match).

## Chuẩn bị
1. Chạy migration mới (thêm `missing_skills`, `seniority_gap` cho `EmployeeJobMatch`).
2. Rescore ít nhất 1 nhân viên để các match có dữ liệu giải thích mới (hoặc backfill).
3. Đăng nhập admin với tài khoản HR/admin.

## US1 — Lý do khớp (explainability)
1. Vào `/admin/employees/{id}` của một nhân viên có match.
2. Mở một job trong bảng match.
3. **Kỳ vọng**: thấy kỹ năng khớp (chip xanh), kỹ năng thiếu (chip đỏ), và chênh cấp bậc (ví dụ "job cần Senior, nhân viên Mid"); job khớp đủ thì danh sách thiếu rỗng.

## US2 — Badge job mới
1. Vào `/admin/employees`.
2. **Kỳ vọng**: nhân viên có N match `suggested` chưa xử lý hiển thị badge "N job mới"; nhân viên không có thì không hiện badge.
3. Vào chi tiết, chuyển 1 match khỏi `suggested` (pursuing/applied) → quay lại list → badge giảm 1.

## US3 — Chặn apply trùng
1. Ở nhân viên 1, đánh dấu job A là `applied` → thành công.
2. Ở nhân viên 2, đánh dấu **cùng job A** là `applied`.
3. **Kỳ vọng**: nhận cảnh báo trùng nêu rõ frontman hiện tại là nhân viên 1; HR có thể xác nhận để tiếp tục hoặc huỷ.

## US4 — Frontman thắng vẫn ở bench
1. Nhân viên 1 đang `bench`, có job A ở `applied`.
2. Đổi job A sang `won`.
3. **Kỳ vọng**: trạng thái nhân viên 1 **vẫn là `bench`**; nhân viên 1 vẫn xuất hiện trong danh sách bench và vẫn nhận gợi ý job mới.
4. Thử đổi trạng thái nhân viên 1 sang `placed` **thủ công** → thành công (đánh dấu bận dự án).

## Không thoái lui (regression)
- Upload CV, parse, bảng match, digest sáng, global pipeline (#012) vẫn hoạt động bình thường.
