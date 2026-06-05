# Implementation Plan: Employee Shadow Enhance

**Branch**: `014-employee-shadow-enhance` | **Date**: 2026-06-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-employee-shadow-enhance/spec.md`

## Summary

Nâng cấp Employee MVP (#012) cho đúng mô hình outsourcing/shadow, gồm 4 hạng mục: (US1) hiển thị lý do khớp — kỹ năng khớp/thiếu + chênh cấp bậc; (US2) badge "Y job mới" trên danh sách nhân viên; (US3) cảnh báo apply trùng một job; (US4) bỏ logic tự động chuyển nhân viên sang "placed" khi thắng job (sửa mâu thuẫn gốc rễ của #012).

**Phát hiện then chốt khi khảo sát code hiện có** → khối lượng nhỏ hơn dự kiến:
- `MatchResult` (pipeline matching) **đã có sẵn `missing_skills`** — chỉ cần truyền qua adapter của employee.
- `EmployeeListSerializer` **đã expose `match_count`** (đếm match status `suggested`) — badge gần như đã sẵn ở backend, chủ yếu cần render ở frontend.
- Logic won→placed nằm gọn tại `apps/employees/views.py` `perform_update` — chỉ cần gỡ bỏ vài dòng.

Cách tiếp cận: mở rộng nhẹ trên hạ tầng #012, không tạo model/luồng mới lớn. Thêm 1 field `missing_skills` (+ tuỳ chọn `seniority_gap`) vào `EmployeeJobMatch`, làm giàu adapter matching, thêm 1 guard chống trùng, gỡ logic auto-placed, và bồi UI ở 2 màn (list + detail).

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (admin frontend)

**Primary Dependencies**: Django + Django REST Framework, Celery (async parse/match); React + Vite + HeroUI (admin SPA)

**Storage**: Django ORM (SQLite dev / PostgreSQL prod) — reuse models `Employee`, `EmployeeJobMatch` (apps.employees), `MatchResult`/`Job` (apps.matching, apps.jobs)

**Testing**: Django test / pytest (backend `apps/employees/tests.py`); thủ công + smoke cho admin UI

**Target Platform**: Linux server (backend API) + trình duyệt (admin dashboard)

**Project Type**: Web — backend API + admin frontend (đã tồn tại)

**Performance Goals**: Thao tác HR tương tác thời gian thực (danh sách + chi tiết tải dưới ~1s với quy mô bench thực tế ≤ vài trăm nhân viên). Không có yêu cầu throughput đặc biệt.

**Constraints**: Không thoái lui luồng #012 hiện có; không thêm migration phá vỡ dữ liệu cũ (field mới có default an toàn); explainability mức cơ bản (không breakdown %).

**Scale/Scope**: 1 công ty, ~vài chục–vài trăm nhân viên trên bench; 2 màn hình admin được nâng cấp + 4 nhóm thay đổi backend.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` hiện là template chưa được phê chuẩn (toàn placeholder) → **không có nguyên tắc ràng buộc cụ thể nào để kiểm tra**. Áp dụng các mặc định hợp lý: tái sử dụng hạ tầng có sẵn, thay đổi tối thiểu, không phá vỡ tương thích, có test cho logic nghiệp vụ mới (guard trùng, bỏ auto-placed, làm giàu explainability).

**Kết quả**: PASS (không có gate vi phạm).

## Project Structure

### Documentation (this feature)

```text
specs/014-employee-shadow-enhance/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contract changes)
│   └── api-changes.md
└── checklists/
    └── requirements.md  # Spec quality checklist (from /speckit-specify)
```

### Source Code (repository root)

```text
backend/
├── apps/
│   ├── employees/
│   │   ├── models.py          # + EmployeeJobMatch.missing_skills (US1); ghi chú frontman = match.employee (US3)
│   │   ├── matching.py         # làm giàu: trả missing_skills + seniority_gap (US1)
│   │   ├── serializers.py      # expose missing_skills/seniority_gap (US1); match_count đã có (US2)
│   │   ├── views.py            # gỡ auto-placed (US4); guard apply trùng (US3)
│   │   ├── migrations/         # + migration field mới
│   │   └── tests.py            # test cho US1/US3/US4
│   └── matching/
│       └── services.py|models  # nguồn missing_skills đã có (reuse, có thể không sửa)
└── ...

admin/
└── src/
    ├── pages/admin/employees/
    │   ├── index.tsx           # render badge "Y job mới" (US2)
    │   └── detail.tsx          # panel "Vì sao khớp" + cảnh báo trùng khi apply (US1, US3)
    ├── types/match.types.ts    # + missing_skills, seniority_gap (US1)
    └── services/match.service.ts # truyền cảnh báo trùng nếu API trả (US3)
```

**Structure Decision**: Web app sẵn có (backend Django + admin React). Toàn bộ thay đổi nằm trong `apps/employees` (chính), tái dùng `apps/matching` (nguồn missing_skills), và 2 trang admin `employees/`. Không tạo app/model/màn mới.

## Phases

### Phase 0 — Research
Xem [research.md](research.md): xác nhận nguồn dữ liệu explainability sẵn có, cơ chế seniority_gap, vị trí logic auto-placed, và quyết định guard "cảnh báo vs chặn cứng".

### Phase 1 — Design & Contracts
- [data-model.md](data-model.md): thay đổi field trên `EmployeeJobMatch`, ngữ nghĩa `Employee.status` sau khi bỏ auto-placed.
- [contracts/api-changes.md](contracts/api-changes.md): thay đổi response của list match (thêm field), hành vi update status (guard trùng), và list employee (badge).
- [quickstart.md](quickstart.md): cách verify từng user story.

### Phase 2 — Tasks
Tạo bởi `/speckit-tasks` (không thuộc lệnh plan).

## Complexity Tracking

> Không có vi phạm Constitution. Không cần mục này.
