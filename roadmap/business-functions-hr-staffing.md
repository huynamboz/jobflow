# JobFlow — Chức năng Business (Mô hình HR Staffing / Outsourcing)

> **Mô hình:** Công ty outsourcing/IT services có đội ngũ nhân viên (bench). HR/sales dùng **CV của chính nhân viên** để đi tìm **job/dự án ngoài thị trường mang về cho công ty làm**.
> **Kiểu "shadow":** 1 CV mạnh đứng ra apply/đại diện → thắng dự án → cả team trong công ty thực thi.
> **Phạm vi:** 1 công ty (không multi-tenant). Nhân viên không login — chỉ là data record do HR quản lý.
> **Giá trị cốt lõi:** Tối đa hóa **billable utilization** (giảm số ngày nhân viên rảnh = giảm đốt tiền).

**Ký hiệu trạng thái:** ✅ Đã có · 🟡 Có một phần · 🔴 Chưa có
**Ưu tiên:** P1 (cốt lõi, làm ngay) · P2 (vận hành) · P3 (tối ưu/về sau)

> **Cập nhật 2026-06-05 (feature 014 — Employee Shadow Enhance):** đã triển khai các mục P1:
> 3.3 Explainability (kỹ năng khớp/thiếu + chênh cấp bậc) 🔴→✅ ·
> 4.2 Badge "job mới"/nhân viên 🟡→✅ ·
> 5.2 Ghi nhận frontman + 5.3 Chặn apply trùng 🔴→✅ ·
> Mục 6: bỏ logic sai "won→placed" của #012 (trạng thái nhân viên giờ hoàn toàn thủ công).
> Còn lại P1: 2.2 Nhập job thủ công (chưa làm). Chi tiết: [specs/014-employee-shadow-enhance/](../specs/014-employee-shadow-enhance/plan.md).

---

## 1. Quản lý nguồn lực — Nhân viên & CV

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 1.1 | Upload CV đơn lẻ + hàng loạt (zip / multi-file) | Đưa nhân viên vào hệ thống nhanh | ✅ | P1 |
| 1.2 | Tự parse CV → skills, seniority, kinh nghiệm, học vấn | Có dữ liệu để match, khỏi nhập tay | ✅ | P1 |
| 1.3 | Sửa tay khi parse sai (flag is_parse_failed) | CV thật hay sai định dạng → HR fix | 🟡 | P1 |
| 1.4 | Hồ sơ nhân viên: trạng thái (bench / đang theo job / đã có việc / nghỉ) | Biết ai đang rảnh để đi kiếm job | ✅ | P1 |
| 1.5 | Cập nhật / thay CV mới (versioning) | Nhân viên nâng cấp skill → CV mới | 🟡 | P2 |
| 1.6 | Trường "rảnh từ ngày" (available_from) | Lọc ai sắp rảnh để chủ động kiếm job trước | 🔴 | P2 |
| 1.7 | Gộp trùng (cùng tên + email) | Tránh 1 người 2 record | ✅ | P2 |

---

## 2. Nguồn job — Thu thập & quản lý catalog

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 2.1 | Crawl job tự động đa nguồn (Indeed/LinkedIn/Adzuna/Remotive) | Có nguồn job liên tục để match | ✅ | P1 |
| 2.2 | **Nhập job thủ công** (HR/sếp gửi link job ngon) | Job thật thường đến từ client/quan hệ, không chỉ crawl | 🔴 | P1 |
| 2.3 | Verify job còn sống / hết hạn (verifier lifecycle) | Tránh apply job đã đóng → mất uy tín | ✅ | P1 |
| 2.4 | Trích xuất job (skill, seniority, lương, role) bằng LLM | Chuẩn hóa job để so khớp chính xác | ✅ | P1 |
| 2.5 | Lọc/tìm job theo role, seniority, lương, nền tảng | HR khoanh vùng job đáng apply | ✅ | P2 |
| 2.6 | Theo dõi độ tươi (unverified / stale / expired) | Catalog không bị cũ | ✅ | P2 |

---

## 3. Matching & Gợi ý — Trái tim hệ thống

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 3.1 | **Forward: CV → danh sách job phù hợp (xếp hạng)** | Luồng chính: mỗi nhân viên hợp job nào để đi apply | ✅ | P1 |
| 3.2 | Điểm khớp 0–100 + badge màu (xanh/vàng/xám) | HR nhìn phát biết job nào đáng | ✅ | P1 |
| 3.3 | **Explainability: vì sao khớp** (skill khớp / thiếu, gap seniority) | HR tự tin quyết định apply hay bỏ qua | 🔴 | P1 |
| 3.4 | Reverse (phụ): 1 job → top CV nên đứng ra apply | Khi bắt đầu từ 1 job hot, tìm frontman mạnh nhất | 🔴 | P2 |
| 3.5 | Lọc/sắp xếp job match theo trạng thái apply, điểm, lương | HR ưu tiên việc | 🟡 | P2 |
| 3.6 | Ngưỡng chất lượng (chỉ hiện job ≥ X điểm) | Giảm nhiễu, khỏi xem job rác | 🟡 | P2 |

---

## 4. Thông báo & Nhắc việc

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 4.1 | **Email digest sáng** "Hôm nay X job mới cho Y nhân viên" | HR mở dashboard là biết việc cần làm | ✅ | P1 |
| 4.2 | **Badge số job mới phù hợp / mỗi nhân viên** trên dashboard | "CV X có Y job phù hợp — xem ngay!" | 🟡 | P1 |
| 4.3 | Cảnh báo job hot sắp hết hạn (apply gấp) | Không bỏ lỡ cơ hội tốt | 🔴 | P2 |
| 4.4 | Nhắc nhân viên sắp rảnh → chủ động kiếm job trước | Giảm khoảng trống bench | 🔴 | P3 |

---

## 5. Pipeline Ứng tuyển (theo dõi tiến độ)

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 5.1 | Trạng thái match: gợi ý → sẽ apply → đã apply → phỏng vấn → thắng/thua | Theo dõi từng cơ hội tới đâu | 🟡 | P1 |
| 5.2 | **Ghi nhận CV nào apply job nào (frontman)** | Mô hình shadow: biết ai đứng tên apply | 🔴 | P1 |
| 5.3 | Chặn apply trùng (cùng job 2 người) | Tránh lộ "shadow", mất uy tín với client | 🔴 | P1 |
| 5.4 | Ghi chú per cơ hội (notes) | Lưu ngữ cảnh trao đổi với client | ✅ | P2 |
| 5.5 | Lịch sử thay đổi trạng thái (audit) | Truy vết, báo cáo | 🟡 | P3 |

---

## 6. Quản lý Hợp đồng & Giao hàng (sau khi thắng)

> ⚠️ **Sửa giả định sai của MVP #012:** trong mô hình shadow, người *apply* không đi làm — họ vẫn rảnh apply tiếp. Trạng thái phải track ở **cấp job/hợp đồng**, KHÔNG phải "nhân viên đã được đặt chỗ". Logic "won → employee placed → xóa khỏi bench" cần bỏ/đổi.

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 6.1 | Pipeline hợp đồng: đang apply → PV → thắng → đang làm → xong | Quản lý dự án thắng được, không lẫn với người apply | 🔴 | P2 |
| 6.2 | Gán team thực thi cho hợp đồng thắng | Frontman apply, nhưng ai làm thật? | 🔴 | P2 |
| 6.3 | Cảnh báo năng lực: thắng nhiều dự án → đủ người làm không? | Tránh nhận quá sức → giao hàng trễ | 🔴 | P3 |

---

## 7. Báo cáo & KPI (chứng minh giá trị cho sếp)

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 7.1 | **Tỷ lệ bench utilization** (% nhân viên có việc) | KPI số 1: tool có giúp giảm bench không | 🔴 | P2 |
| 7.2 | Win-rate theo frontman / theo loại job | "CV của A thắng 40% job backend" → dùng đúng người | 🔴 | P2 |
| 7.3 | Thời gian trung bình từ gợi ý → thắng job | Đo tốc độ kiếm việc | 🔴 | P2 |
| 7.4 | Phễu pipeline (gợi ý → apply → PV → thắng) | Thấy rớt ở khâu nào | 🔴 | P2 |
| 7.5 | KPI cơ bản: số job/CV/match/label | Sức khỏe hệ thống | ✅ | P3 |

---

## 8. Quản trị & Vận hành

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 8.1 | Auth + phân quyền (admin / HR / manager) | Kiểm soát truy cập, chỉ admin xóa | ✅ | P1 |
| 8.2 | Lập lịch tự động crawl + verify (schedule daemon) | Catalog tự cập nhật, không thao tác tay | ✅ | P2 |
| 8.3 | Quản lý & retrain model qua dashboard | Cải thiện chất lượng match theo thời gian | ✅ | P3 |
| 8.4 | Log LLM / verifier / lỗi | Vận hành, debug | ✅ | P3 |

---

## 9. Vòng phản hồi — Cải thiện model (Data moat)

| # | Chức năng | Mục đích business | Trạng thái | Ưu tiên |
|---|---|---|---|---|
| 9.1 | HR đánh dấu match tốt/tệ | Tín hiệu thật để dạy model (không chỉ LLM label) | 🔴 | P3 |
| 9.2 | Dùng kết quả thắng/thua làm nhãn retrain | Model học từ thực tế → match ngày càng đúng | 🔴 | P3 |

---

## Tóm tắt ưu tiên — Nên làm ngay (P1)

Bám đúng luồng bạn mô tả ("sáng vào thấy CV X có Y job → bấm xem list → quyết apply"):

1. **Badge số job mới / nhân viên** trên dashboard (4.2) — quick win, dữ liệu đã có
2. **Explainability "vì sao khớp"** (3.3) — engine đã tính 23 feature, chỉ cần expose
3. **Ghi nhận CV nào apply job nào + chặn trùng** (5.2, 5.3) — đặc thù mô hình shadow
4. **Nhập job thủ công** (2.2) — job thật thường từ client, không chỉ crawl
5. **Sửa logic status sai của #012** (mục 6) — track ở cấp job, không phải cấp người

> Những thứ này đứng trên nền tảng đã có (upload, parse, forward matching, digest, verifier) — chủ yếu là **bổ sung & sửa**, không build lại từ đầu.

---

## Việc cố tình KHÔNG làm (sai mô hình hiện tại)
- ❌ Auto-sinh & tự gửi email ứng tuyển (tầm nhìn đề cương cũ — nhưng mô hình shadow HR apply thủ công, cần kiểm soát)
- ❌ Multi-tenant / billing (chỉ 1 công ty)
- ❌ Portal cho nhân viên login (nhân viên chỉ là data record)
- ❌ Team-level matching (mỗi job 1 người đại diện apply)
