# Phase 0 Research: Employee Shadow Enhance

Mục tiêu: giải tỏa các điểm chưa chắc chắn trước khi thiết kế. Tất cả đều dựa trên khảo sát code #012 thực tế.

## R1 — Nguồn dữ liệu "kỹ năng thiếu" (missing_skills)

**Decision**: Tái dùng `missing_skills` đã có sẵn trong pipeline matching; truyền qua adapter `apps/employees/matching.py` và lưu vào `EmployeeJobMatch`.

**Rationale**: `apps/matching/models.py` (`MatchResult`) đã khai báo `matched_skills` **và** `missing_skills` (dòng 9–10), nghĩa là pipeline đã tính phần thiếu. Adapter employee hiện chỉ lấy `{job_id, score, matched_skills}` nên thông tin thiếu bị bỏ. Không cần tính lại từ đầu.

**Alternatives considered**: Tự diff `job.required_skills − employee.skills` ở tầng employee — bị loại vì trùng lặp logic chuẩn hoá kỹ năng đã có trong matching, dễ lệch kết quả.

## R2 — Chênh lệch cấp bậc (seniority_gap)

**Decision**: Tính `seniority_gap = job_seniority − employee_seniority` (số nguyên) tại adapter matching và lưu kèm match; UI diễn giải thành chữ ("job cần Senior, nhân viên Mid"). Nếu job hoặc nhân viên thiếu cấp bậc → `null`, UI hiển thị "chưa đủ dữ liệu".

**Rationale**: `Employee.seniority` là IntegerField; Job có cấp bậc yêu cầu từ bước trích xuất. Phép trừ đơn giản, đủ cho mức "cơ bản" mà spec chốt. Lưu sẵn để tránh tính lại mỗi lần render.

**Alternatives considered**: Chỉ hiển thị nhãn cấp bậc 2 bên, không tính gap — bị loại vì HR vẫn phải tự so sánh. Breakdown % đóng góp seniority vào điểm — defer (ngoài phạm vi).

## R3 — Vị trí & cách gỡ logic auto-placed (FR cũ #012)

**Decision**: Gỡ nhánh đặt `Employee.status = PLACED` trong `apps/employees/views.py` `perform_update` (khi `new_status == "won"`). Giữ nguyên việc set `won_at`. Không xoá enum `placed` ngay; chuyển nó thành trạng thái HR set **thủ công** (đánh dấu đang bận dự án).

**Rationale**: Logic nằm gọn một chỗ (views.py, nhánh won). Gỡ tối thiểu, không đụng model. Giữ enum `placed` để HR vẫn có thể đánh dấu thủ công, tránh migration dữ liệu cũ.

**Alternatives considered**: Xoá hẳn `placed` khỏi enum — bị loại vì cần migration + có thể có dữ liệu cũ đang ở trạng thái này; rủi ro không tương xứng lợi ích.

## R4 — Guard chống apply trùng: cảnh báo hay chặn cứng?

**Decision**: **Cảnh báo mềm** — khi HR chuyển một match sang `applied`, nếu job đó đã có match khác ở `applied`/`won`, API trả về thông tin trùng (nhân viên frontman hiện tại) để UI hiển thị xác nhận; HR có thể vẫn tiếp tục. Mặc định API thực hiện kiểm tra qua một tham số xác nhận (ví dụ `confirm_duplicate`) để không chặn cứng.

**Rationale**: Spec & stakeholder chốt "cảnh báo, không chặn cứng" — thực tế có lúc HR cố ý đổi frontman. Vẫn đảm bảo HR không vô tình apply trùng.

**Alternatives considered**: Chặn cứng bằng ràng buộc DB unique (job + applied) — bị loại vì kém linh hoạt, khó xử lý đổi frontman hợp lệ; có thể siết sau nếu cần.

## R5 — Badge "Y job mới" lấy từ đâu

**Decision**: Tái dùng annotate `match_count` đã có (`EmployeeViewSet.get_queryset` đếm match status `suggested`) và `EmployeeListSerializer.match_count` đã expose. Việc còn lại chủ yếu ở frontend: render badge trên danh sách.

**Rationale**: Backend đã sẵn sàng. "Job mới" = match `suggested` chưa xử lý, đúng định nghĩa trong spec. Tránh thêm endpoint.

**Alternatives considered**: Định nghĩa "mới" theo mốc thời gian đăng nhập HR — defer (phức tạp, cần lưu last-seen); dùng `suggested` là đủ cho đợt này.

## Tổng hợp
Cả 5 điểm đều có giải pháp dựa trên hạ tầng sẵn có. Không còn NEEDS CLARIFICATION. Sẵn sàng sang Phase 1.
