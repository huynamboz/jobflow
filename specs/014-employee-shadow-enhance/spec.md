# Feature Specification: Employee Shadow Enhance

**Feature Branch**: `014-employee-shadow-enhance`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: nâng cấp Employee MVP (#012) cho đúng mô hình outsourcing/shadow — bổ sung khả năng ra quyết định cho HR vào luồng hằng ngày.

## Bối cảnh & Mục đích

Công ty IT outsourcing có nhân viên trên "bench" (đang rảnh). HR dùng **CV của chính nhân viên** để đi tìm job/dự án ngoài thị trường mang về cho công ty làm. Mô hình **"shadow"**: một CV mạnh (gọi là **frontman**) đứng ra đại diện apply một job; khi thắng, **cả team trong công ty thực thi** — người đứng apply KHÔNG đi làm thật và vẫn rảnh để apply job khác.

Feature này **nâng cấp trên nền #012** (đã có: danh sách + chi tiết nhân viên, bảng job match, trạng thái pursuing/applied/won/lost, email digest sáng). Mục tiêu: làm cho luồng hằng ngày của HR — *"sáng mở dashboard → thấy CV X có Y job mới phù hợp → bấm vào xem danh sách job → quyết định apply"* — đủ thông tin để **ra quyết định nhanh và an toàn**, đồng thời **sửa một mâu thuẫn ngữ nghĩa** trong #012 vốn không đúng với mô hình shadow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - HR quyết định apply dựa trên lý do khớp (Priority: P1)

HR mở chi tiết một nhân viên, xem danh sách job phù hợp. Với mỗi job, ngoài điểm khớp, HR thấy **vì sao khớp**: những kỹ năng đã khớp, những kỹ năng còn thiếu so với yêu cầu job, và chênh lệch cấp bậc (seniority). Nhờ đó HR quyết định nhanh nên dùng nhân viên này apply job đó hay bỏ qua.

**Why this priority**: Đây là giá trị cốt lõi của đợt nâng cấp — biến bảng "điểm số" thành "công cụ ra quyết định". Không có nó, HR phải tự đọc JD và CV để đoán, mất thời gian và dễ apply sai.

**Independent Test**: Mở chi tiết 1 nhân viên có sẵn match → mỗi dòng job hiển thị danh sách kỹ năng khớp/thiếu và chênh seniority → HR phân biệt được job "đáng apply" với job "thiếu nhiều kỹ năng".

**Acceptance Scenarios**:

1. **Given** một nhân viên có ≥1 job match, **When** HR mở chi tiết nhân viên và xem một job, **Then** hệ thống hiển thị kỹ năng đã khớp, kỹ năng còn thiếu, và chênh lệch cấp bậc giữa nhân viên và job.
2. **Given** một job mà nhân viên đáp ứng đủ kỹ năng yêu cầu, **When** HR xem lý do khớp, **Then** danh sách "kỹ năng thiếu" rỗng và được thể hiện rõ là khớp tốt.
3. **Given** một job yêu cầu cấp bậc cao hơn nhân viên, **When** HR xem lý do khớp, **Then** chênh lệch cấp bậc được hiển thị rõ ràng (ví dụ "job cần Senior, nhân viên là Mid").

---

### User Story 2 - Quét bench buổi sáng qua badge job mới (Priority: P1)

Mỗi sáng HR mở danh sách nhân viên và thấy ngay, với từng nhân viên, **số job mới phù hợp** chưa được xử lý (badge "Y job mới"). HR ưu tiên xử lý những nhân viên có nhiều job mới, mở vào xem và quyết định apply. Khi HR đã xem/xử lý, badge phản ánh đúng số còn lại.

**Why this priority**: Đóng trọn luồng "sáng vào thấy ngay ai cần xử lý". Không có badge, HR phải mở từng nhân viên để biết có job mới không — không khả thi khi bench đông.

**Independent Test**: Trên danh sách nhân viên, mỗi dòng hiển thị badge số job mới (status "gợi ý" chưa xử lý); nhân viên không có job mới thì không hiện badge hoặc hiện 0.

**Acceptance Scenarios**:

1. **Given** một nhân viên có 5 job match ở trạng thái "gợi ý" chưa được HR động tới, **When** HR mở danh sách nhân viên, **Then** dòng nhân viên đó hiển thị badge "5 job mới".
2. **Given** HR đã chuyển 2 job sang "sẽ apply/đã apply", **When** HR quay lại danh sách, **Then** badge giảm tương ứng (còn 3).
3. **Given** một nhân viên không có job mới nào, **When** HR mở danh sách, **Then** không hiển thị badge job mới (hoặc hiển thị 0 một cách trung tính).

---

### User Story 3 - Chặn apply trùng một job (Priority: P1)

Khi HR đánh dấu một job là "đã apply" bằng một nhân viên (frontman), nếu job đó **đã có một nhân viên khác** ở trạng thái "đã apply" hoặc "đã thắng", hệ thống **cảnh báo** để tránh hai người cùng đại diện apply một job — điều có thể làm lộ mô hình shadow và mất uy tín với khách hàng. Hệ thống ghi nhận rõ nhân viên nào là frontman của job đó.

**Why this priority**: Rủi ro nghiệp vụ đặc thù của mô hình shadow. Một lần lộ có thể mất khách. Đây là rào chắn an toàn bắt buộc.

**Independent Test**: Đánh dấu "đã apply" cho job A bằng nhân viên 1 → thành công. Sau đó thử đánh dấu "đã apply" cho cùng job A bằng nhân viên 2 → nhận cảnh báo trùng.

**Acceptance Scenarios**:

1. **Given** job A chưa có ai apply, **When** HR đánh dấu nhân viên 1 "đã apply" job A, **Then** thao tác thành công và job A được ghi nhận frontman là nhân viên 1.
2. **Given** job A đã có nhân viên 1 ở trạng thái "đã apply", **When** HR cố đánh dấu nhân viên 2 "đã apply" job A, **Then** hệ thống cảnh báo trùng và nêu rõ ai đang là frontman.
3. **Given** job A đã có nhân viên 1 ở trạng thái "đã thắng", **When** HR cố đánh dấu nhân viên 2 "đã apply" job A, **Then** hệ thống cảnh báo trùng.

---

### User Story 4 - Frontman thắng job vẫn ở lại bench (Priority: P1)

Khi một job match chuyển sang "đã thắng", trạng thái của nhân viên (frontman) **không tự động đổi** sang "đã có việc / placed". Frontman vẫn ở "bench" và tiếp tục được gợi ý + đại diện apply các job khác, vì trên thực tế người đó không đi làm dự án — team trong công ty làm.

**Why this priority**: Đây là **sửa mâu thuẫn gốc rễ** của #012 (FR-008 cũ tự động chuyển nhân viên sang "placed" khi thắng). Logic cũ sai hoàn toàn với mô hình shadow, làm số liệu bench và gợi ý sai lệch.

**Independent Test**: Đưa một job match của nhân viên đang "bench" sang "đã thắng" → kiểm tra trạng thái nhân viên vẫn là "bench" và nhân viên vẫn xuất hiện trong danh sách bench + vẫn nhận gợi ý job mới.

**Acceptance Scenarios**:

1. **Given** nhân viên 1 đang "bench" với một job ở trạng thái "đã apply", **When** HR đổi job đó sang "đã thắng", **Then** trạng thái nhân viên 1 vẫn là "bench".
2. **Given** nhân viên 1 vừa thắng một job, **When** HR xem danh sách bench, **Then** nhân viên 1 vẫn nằm trong danh sách và vẫn có thể nhận/đại diện job mới.
3. **Given** HR muốn đánh dấu một nhân viên đang bận dự án, **When** HR đổi trạng thái nhân viên thủ công, **Then** hệ thống cho phép đổi thủ công (không phải do thắng job tự động).

---

### Edge Cases

- **Job thiếu dữ liệu kỹ năng/cấp bậc**: nếu job chưa được trích xuất đủ kỹ năng yêu cầu hoặc cấp bậc, phần "vì sao khớp" hiển thị phần có dữ liệu và ghi rõ phần thiếu thông tin thay vì báo lỗi.
- **Nhân viên parse lỗi (không có kỹ năng)**: danh sách job vẫn hiển thị nhưng phần khớp kỹ năng trống; HR được nhắc kiểm tra/sửa hồ sơ.
- **Badge job mới khi chưa có match nào**: hiển thị trung tính (không badge), không gây hiểu nhầm "0 nghĩa là lỗi".
- **Cảnh báo trùng nhưng HR vẫn muốn tiếp tục**: hệ thống cảnh báo rõ ràng; quyết định cuối thuộc về HR (cảnh báo, không nhất thiết chặn cứng) — cách xử lý cụ thể nêu trong Assumptions.
- **Đổi một job từ "đã thắng" về trạng thái khác**: không gây thay đổi ngược trạng thái nhân viên (vì nhân viên chưa từng bị đổi tự động).
- **Job đã thắng/đang apply bị gỡ hoặc hết hạn**: trạng thái match được giữ để phục vụ theo dõi/báo cáo.

## Requirements *(mandatory)*

### Functional Requirements

**Explainability (US1)**
- **FR-001**: Với mỗi cặp (nhân viên, job) đã match, hệ thống MUST cung cấp danh sách **kỹ năng đã khớp** giữa nhân viên và yêu cầu job.
- **FR-002**: Hệ thống MUST cung cấp danh sách **kỹ năng còn thiếu** (job yêu cầu nhưng nhân viên không có).
- **FR-003**: Hệ thống MUST cung cấp **chênh lệch cấp bậc** giữa nhân viên và job (nhân viên thấp hơn / bằng / cao hơn).
- **FR-004**: Màn chi tiết nhân viên MUST hiển thị thông tin "vì sao khớp" (kỹ năng khớp, kỹ năng thiếu, chênh cấp bậc) cho từng job, cùng với điểm khớp đã có.

**Badge job mới (US2)**
- **FR-005**: Danh sách nhân viên MUST hiển thị, cho mỗi nhân viên, **số job match mới chưa xử lý** (trạng thái "gợi ý").
- **FR-006**: Số job mới MUST cập nhật khi HR chuyển một match khỏi trạng thái "gợi ý" (sang sẽ apply/đã apply/bỏ qua...).

**Chặn apply trùng (US3)**
- **FR-007**: Khi HR đánh dấu một match là "đã apply", hệ thống MUST kiểm tra xem job đó đã có nhân viên khác ở trạng thái "đã apply" hoặc "đã thắng" hay chưa.
- **FR-008**: Nếu phát hiện trùng, hệ thống MUST cảnh báo HR và nêu rõ **nhân viên nào đang là frontman** của job đó.
- **FR-009**: Hệ thống MUST ghi nhận, cho mỗi job đang được theo đuổi, nhân viên (frontman) đại diện apply.

**Sửa mâu thuẫn won→placed (US4)**
- **FR-010**: Khi một match chuyển sang "đã thắng", hệ thống MUST KHÔNG tự động đổi trạng thái nhân viên (frontman) sang "đã có việc/placed". Frontman giữ nguyên "bench".
- **FR-011**: Hệ thống MUST cho phép HR đổi trạng thái nhân viên **thủ công** (ví dụ đánh dấu đang bận dự án), độc lập với kết quả thắng/thua của job.
- **FR-012**: Nhân viên ở "bench" MUST tiếp tục nhận gợi ý job mới và có thể đại diện apply nhiều job, kể cả sau khi đã thắng một job.

**Phạm vi giữ nguyên từ #012**
- **FR-013**: Các chức năng đã có của #012 (upload CV, parse, bảng match, trạng thái pursuing/applied/won/lost, digest sáng, global pipeline) MUST tiếp tục hoạt động không thoái lui.

### Key Entities *(include if feature involves data)*

- **Nhân viên (Employee)**: người trên bench do HR quản lý; có kỹ năng, cấp bậc, kinh nghiệm, trạng thái (bench / đang bận thủ công / nghỉ). Không tự động đổi trạng thái khi thắng job.
- **Match (Nhân viên–Job)**: liên kết một nhân viên với một job; mang điểm khớp, **kỹ năng khớp**, **kỹ năng thiếu**, **chênh cấp bậc**, và trạng thái (gợi ý / sẽ apply / đã apply / đã thắng / đã thua). Nhân viên trong match đóng vai trò frontman khi job được apply.
- **Job**: tin tuyển dụng / cơ hội dự án từ catalog; có kỹ năng yêu cầu và cấp bậc yêu cầu dùng để tính lý do khớp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với mọi job hiển thị trên màn chi tiết nhân viên, HR thấy được kỹ năng khớp, kỹ năng thiếu và chênh cấp bậc mà không cần mở JD gốc hay đọc lại CV.
- **SC-002**: HR xác định được "nhân viên nào cần xử lý sáng nay" chỉ bằng cách nhìn danh sách nhân viên (qua badge job mới), không cần mở từng hồ sơ.
- **SC-003**: 100% trường hợp hai nhân viên cùng được đánh dấu "đã apply" cho cùng một job đều phát sinh cảnh báo trùng trước khi hoàn tất.
- **SC-004**: Sau khi một job chuyển sang "đã thắng", nhân viên frontman vẫn xuất hiện trong danh sách bench trong 100% trường hợp (không bị tự động loại).
- **SC-005**: Không có thoái lui chức năng: toàn bộ luồng #012 hiện có vẫn hoạt động sau khi triển khai.

## Assumptions

- **Mức explainability**: chọn mức **cơ bản** — kỹ năng khớp/thiếu + chênh cấp bậc. Không bao gồm breakdown phần trăm đóng góp của từng thành phần vào điểm tổng (defer).
- **Cảnh báo trùng là "cảnh báo", không chặn cứng**: hệ thống hiển thị cảnh báo rõ ràng và yêu cầu HR xác nhận; quyết định cuối thuộc về HR. (Có thể siết thành chặn cứng ở đợt sau nếu cần.)
- **"Job mới" = match ở trạng thái "gợi ý" chưa được HR chuyển trạng thái.** Không gắn với mốc thời gian đăng nhập của HR ở đợt này.
- **Trạng thái nhân viên**: giữ "bench" làm mặc định; bỏ cơ chế tự động chuyển sang "placed" khi thắng. Việc đánh dấu nhân viên bận dự án là thao tác thủ công của HR.
- **Tái sử dụng hạ tầng #012**: model Employee/Match, matching pipeline, auth & role (admin/HR/recruiter), digest — đều dùng lại, chỉ mở rộng.
- **Ngoài phạm vi đợt này (cố tình defer)**: model Hợp đồng/giao hàng, gán team thực thi, nhập job thủ công, reverse match (job→nhân viên), báo cáo KPI nâng cao (bench utilization, win-rate), trạng thái "phỏng vấn", auto-sinh & gửi email ứng tuyển, multi-tenant.
- **Người dùng**: HR/recruiter/admin của một công ty duy nhất; nhân viên không đăng nhập.
