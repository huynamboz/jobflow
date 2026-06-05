# JobFlow — Build Backlog (Tính năng & Màn hình)

> **Mô hình:** IT outsourcing / shadow. HR dùng CV nhân viên (bench) đi kiếm job ngoài → 1 CV (frontman) đứng ra apply → thắng → team trong công ty làm. 1 công ty, nhân viên không login.
> **Mục tiêu business:** tối đa hóa billable utilization (giảm ngày bench).
> **File này = backlog tổng**: mọi tính năng + màn hình, kèm trạng thái & ưu tiên. Cập nhật 2026-06-05.

**Trạng thái:** ✅ Xong · 🟡 Một phần · 🔴 Chưa làm
**Nguồn:** (012) Employee MVP · (014) Shadow Enhance · (—) chưa có spec
**Ưu tiên:** P1 cốt lõi · P2 vận hành · P3 tối ưu

---

## A. TÍNH NĂNG (Functions)

### 1. Nguồn lực — Nhân viên & CV
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 1.1 | Upload CV đơn + hàng loạt (zip/multi-file, ≤50) | ✅ | P1 | 012 |
| 1.2 | Parse CV → skills, seniority, kinh nghiệm | ✅ | P1 | 012 |
| 1.3 | Sửa tay khi parse lỗi (flag is_parse_failed) | ✅ | P1 | 012/015 |
| 1.4 | Trạng thái nhân viên (bench/placed/inactive) — **thủ công** | ✅ | P1 | 012/014 |
| 1.5 | Thay/cập nhật CV mới (versioning) | 🔴 | P2 | — |
| 1.6 | Trường "rảnh từ ngày" (available_from) | 🔴 | P2 | — |
| 1.7 | Gộp trùng (cùng tên + email) | ✅ | P2 | 012 |

### 2. Nguồn job — Catalog
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 2.1 | Crawl đa nguồn (Indeed/LinkedIn/Adzuna/Remotive) | ✅ | P1 | trước |
| 2.2 | **Nhập job thủ công** (job hot từ client/sếp) | 🔴 | **P1** | — |
| 2.3 | Verify job còn sống / lifecycle | ✅ | P1 | 001 |
| 2.4 | Trích xuất job (skill/seniority/lương) bằng LLM | ✅ | P1 | trước |
| 2.5 | Lọc/tìm job theo role/seniority/lương | ✅ | P2 | trước |
| 2.6 | Theo dõi độ tươi (unverified/stale/expired) | ✅ | P2 | trước |

### 3. Matching & Gợi ý
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 3.1 | Forward: CV nhân viên → danh sách job (xếp hạng) | 🟡 | P1 | 012 |
| 3.2 | Điểm khớp 0–100 + badge màu | ✅ | P1 | 012 |
| 3.3 | **Explainability** (kỹ năng khớp/thiếu + chênh cấp bậc) | ✅ | P1 | 014 |
| 3.4 | Reverse: 1 job → top CV nên apply | 🔴 | P2 | — |
| 3.5 | Lọc/sắp xếp match theo trạng thái/điểm/lương | 🟡 | P2 | 012 |
| 3.6 | Ngưỡng chất lượng (chỉ hiện job ≥ X điểm) | 🔴 | P2 | — |
| 3.7 | **Nối engine→employee live** (map JDExtractionRecord↔Job) | 🔴 | **P1** | spike 015 |

> ⚠️ **3.1 chỉ 🟡**: UI/logic xong nhưng matching nhân viên chưa chạy live do gap 3.7 (id-space engine≠Job). Cần spike 015 để có dữ liệu match thật.

### 4. Thông báo & Nhắc việc
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 4.1 | Email digest sáng "X job mới cho Y nhân viên" | ✅ | P1 | 012 |
| 4.2 | Badge "Y job mới"/nhân viên trên dashboard/list | ✅ | P1 | 014 |
| 4.3 | Cảnh báo job hot sắp hết hạn | 🟡 | P2 | 016 |
| 4.4 | Nhắc nhân viên sắp rảnh → kiếm job trước | 🔴 | P3 | — |

### 5. Pipeline ứng tuyển
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 5.1 | Trạng thái match: suggested→pursuing→applied→won/lost | ✅ | P1 | 012 |
| 5.2 | Ghi nhận frontman (CV nào apply job nào) | ✅ | P1 | 014 |
| 5.3 | Chặn/cảnh báo apply trùng 1 job | ✅ | P1 | 014 |
| 5.4 | Ghi chú per cơ hội (notes) | ✅ | P2 | 012 |
| 5.5 | Lịch sử thay đổi trạng thái (audit) | 🟡 | P3 | 012 |
| 5.6 | Trạng thái "interview" (applied→PV→won/lost) | 🔴 | P2 | — |

### 6. Hợp đồng & Giao hàng (sau khi thắng)
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 6.1 | Model Contract/dự án (applying→won→delivering→done) | 🔴 | P2 | — |
| 6.2 | Gán team thực thi cho hợp đồng thắng | 🔴 | P2 | — |
| 6.3 | Cảnh báo năng lực: thắng nhiều → đủ người làm? | 🔴 | P3 | — |

### 7. Báo cáo & KPI
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 7.1 | Bench utilization (% nhân viên có việc) | ✅ | P2 | 016 |
| 7.2 | Win-rate theo frontman / loại job | 🔴 | P2 | — |
| 7.3 | Time-to-win trung bình | 🔴 | P2 | — |
| 7.4 | Phễu pipeline (gợi ý→apply→PV→thắng) | ✅ | P2 | 016 |
| 7.5 | KPI cơ bản (số job/CV/match) + widget | ✅ | P3 | 012 |

### 8. Quản trị & Vận hành
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 8.1 | Auth + phân quyền (admin/HR/recruiter) | ✅ | P1 | 012 |
| 8.2 | Lập lịch tự động crawl + verify (daemon) | ✅ | P2 | 005 |
| 8.3 | Quản lý & retrain model qua dashboard | ✅ | P3 | trước |
| 8.4 | Log LLM / verifier / lỗi | ✅ | P3 | trước |

### 9. Vòng phản hồi — Cải thiện model
| # | Tính năng | TT | Ưu tiên | Nguồn |
|---|---|---|---|---|
| 9.1 | HR đánh dấu match tốt/tệ | 🔴 | P3 | — |
| 9.2 | Dùng won/lost làm nhãn retrain | 🔴 | P3 | — |

---

## B. MÀN HÌNH (Screens)

> 🔧 nâng cấp màn có sẵn · 🆕 làm mới · ✅ xong · 🔴 chưa

### Đã có & đã nâng cấp
| Màn | Mục đích | TT | Nguồn |
|---|---|---|---|
| **Đăng nhập / Auth** | JWT, role | ✅ | 012 |
| **Danh sách nhân viên** | Bench, filter, upload, **badge "N new"** | ✅ | 012/014 |
| **Chi tiết nhân viên + Job match** ⭐ | List job + điểm + **panel "Vì sao khớp"** + **cảnh báo apply trùng** | ✅ | 012/014 |
| **Global pipeline** | Bảng tất cả match, filter/sort | ✅ | 012 |
| **Dashboard staffing (KPI + action queue + funnel + alerts + recent)** | Luồng HR sáng | ✅ | 016 |
| **Job catalog** | Browse/filter, freshness, verifier stats | ✅ | trước |
| **Schedule daemon** | Cấu hình crawl/verify, log | ✅ | 005 |
| **LLM logs / providers / models** | Vận hành ML | ✅ | trước |
| **Recommend (CV→jobs demo)** | Test matching public | ✅ | trước |

### Cần làm mới / nâng cấp tiếp
| Màn | Mục đích | TT | Ưu tiên | Tính năng liên quan |
|---|---|---|---|---|
| **Dashboard "Cần xem sáng nay"** | Banner top nhân viên nhiều job mới + funnel + cảnh báo | ✅ | P1 | 016 |
| **Nhập job thủ công** 🆕 | Dán URL/nhập tay → extract → match | 🔴 | P1 | 2.2 |
| **Pipeline Kanban** 🆕 | Kéo-thả cơ hội theo cột trạng thái | 🔴 | P2 | 5.x |
| **Reverse match (Job→CV)** 🆕 | Từ 1 job tìm frontman mạnh nhất | 🔴 | P2 | 3.4 |
| **Hợp đồng & giao hàng** 🆕 | Quản dự án thắng, gán team | 🔴 | P2 | 6.x |
| **Báo cáo & KPI** 🆕 | Bench utilization, win-rate, funnel | 🔴 | P2 | 7.x |
| **Skill gap / đào tạo** 🆕 | Nhân viên thiếu skill gì cho job mục tiêu | 🔴 | P3 | 3.3+ |

---

## C. THỨ TỰ ƯU TIÊN ĐỀ XUẤT (việc còn lại)

1. ✅ ~~Dashboard "Cần xem sáng nay"~~ — đã làm (016).
2. **Spike — Nối engine→employee live** (3.7) → để matching nhân viên có dữ liệu thật. *Chặn giá trị của 3.1/US1/US2.* (P1)
3. **Nhập job thủ công** (2.2 + màn 🆕) → job thật từ client, P1.
4. **Báo cáo KPI còn lại** (7.2 win-rate, 7.3 time-to-win) → số liệu cho sếp.
5. **Pipeline Kanban** → trải nghiệm quản cơ hội tốt hơn.
6. **Contract/giao hàng** (6.x) → quản dự án sau thắng.
7. **Reverse match, skill gap, feedback loop** → tối ưu về sau.

## D. CỐ TÌNH KHÔNG LÀM (sai mô hình hiện tại)
❌ Auto-sinh & gửi email ứng tuyển · ❌ Multi-tenant / billing · ❌ Portal nhân viên login · ❌ Team-level matching (mỗi job 1 frontman).
→ Mở lại khi đổi định hướng sang SaaS.

---

### Tham chiếu
- Phân tích business: [business-functions-hr-staffing.md](business-functions-hr-staffing.md)
- Sơ đồ luồng + màn: [workflow-and-screens.md](workflow-and-screens.md)
- Đã code: [specs/012-employee-mvp/](../specs/012-employee-mvp/plan.md), [specs/014-employee-shadow-enhance/](../specs/014-employee-shadow-enhance/plan.md)
