# Implementation Plan: Employee MVP

**Branch**: `012-employee-mvp` | **Date**: 2026-05-22 | **Spec**: [spec.md](spec.md)

## Summary

Internal HR tool: upload employee CVs (bulk), find matching jobs, track pipeline (suggested → pursuing → applied → won/lost), daily email digest cho HR.

4 user stories bundled (US1+US2+US3 P1, US4 P2). Strategy: backend `apps.employees` + `apps.notifications` trước, sau đó admin UI inside existing admin/ Vite SPA (HeroUI + React Router + Zustand). KHÔNG tạo separate frontend.

## Technical Context

**Language/Version**: Python 3.11 (Django 5), TypeScript 5+ (admin SPA)

**Primary Dependencies (NEW)**:
- Backend: `celery[redis]`, `django-celery-beat`, `django-anymail`, `redis` (đã có sẵn trong commits trước, sẽ reuse)
- Frontend (admin/): không cần dep mới — đã có HeroUI, axios, React Router, Zustand, lucide-react

**Storage**: PostgreSQL 16 + Redis 7 (Celery broker)

**Testing**: pytest + pytest-django backend; smoke UI (no E2E this session)

**Target Platform**: Linux server (Docker)

**Project Type**: Django backend + admin SPA extension

**Performance Goals**: see NFR-001..NFR-004

**Constraints**:
- ZERO regression existing admin SPA (28 pages) + ml_service production
- Backward-compat migrations only
- Reuse existing matching API (no model retrain)

**Scale/Scope (MVP target)**:
- 1 company, 100-1000 employees
- 10k jobs (existing catalog)
- 5-10 HR users
- Daily digest email to 10 recipients

## Constitution Check

No `.specify/memory/constitution.md`. Implicit gates from CLAUDE.md + prior features:

- ✅ Reuse existing infra (matching, auth, ML)
- ✅ Don't touch ml_service
- ✅ Speckit workflow
- ✅ Backward compatible migrations

## Project Structure

```text
specs/012-employee-mvp/
├── spec.md
├── plan.md (this)
├── research.md
├── data-model.md
├── contracts/
│   ├── employees_api.md
│   └── admin_employee_ui.md
├── quickstart.md
└── checklists/
    └── requirements.md
```

### Source code

```text
backend/
├── apps/
│   ├── users/                   # EXTEND: add notify_daily_digest + unsubscribe_token fields
│   ├── employees/               # NEW
│   │   ├── models.py            # Employee, EmployeeJobMatch
│   │   ├── serializers.py
│   │   ├── views.py             # ViewSet for Employee + Match
│   │   ├── urls.py
│   │   ├── admin.py             # Django admin
│   │   ├── parsers.py           # Adapter to existing CV parser
│   │   ├── matching.py          # Adapter to existing matching API → create Match records
│   │   ├── tasks.py             # Celery: async bulk parse + match generation
│   │   ├── tests.py
│   │   └── migrations/
│   └── notifications/           # NEW
│       ├── tasks.py             # send_hr_daily_digest + fanout
│       ├── views.py             # unsubscribe endpoint
│       ├── urls.py
│       ├── management/commands/send_hr_digest.py
│       ├── templates/emails/hr_daily_digest.html
│       └── migrations/
├── config/
│   ├── settings.py              # EXTEND: re-add CELERY_*, EMAIL_BACKEND, INSTALLED_APPS
│   ├── urls.py                  # EXTEND: wire employees + notifications routes
│   ├── celery.py                # ALREADY in commit history (re-add)
│   └── __init__.py              # ALREADY in commit history (re-add)
├── docker-compose.yml           # ALREADY has redis (re-add)
└── requirements.txt             # ALREADY has celery/redis/anymail (re-add)

admin/                           # EXTEND (no new app)
├── src/
│   ├── App.tsx                  # EXTEND: add 3 new routes
│   ├── pages/admin/
│   │   ├── employees/           # NEW
│   │   │   ├── index.tsx        # List + bulk upload
│   │   │   ├── detail.tsx       # Single employee + matches
│   │   │   └── upload-modal.tsx
│   │   └── pipeline/            # NEW
│   │       └── index.tsx        # Global pipeline view
│   ├── services/
│   │   ├── employee.service.ts  # NEW
│   │   └── match.service.ts     # NEW
│   ├── types/
│   │   ├── employee.types.ts    # NEW
│   │   └── match.types.ts       # NEW
│   ├── layouts/admin-layout.tsx # EXTEND: add nav items
│   └── pages/admin/dashboard/   # EXTEND: add Pipeline KPI widget
```

## Phases

### Phase 0: Re-setup infra (re-add deps + Celery from candidate-mvp work)

- Add Redis service vào docker-compose (đã có code, đảm bảo hiện diện)
- Re-add backend deps celery/redis/anymail vào requirements.txt
- Re-add Celery config trong config/celery.py + __init__.py
- Re-add CELERY_* + EMAIL_BACKEND + FRONTEND_BASE_URL trong settings.py

### Phase 1: Backend US2 + US3 foundation

- Tạo app `apps.employees`
- Extend User model: notify_daily_digest + unsubscribe_token (migration mới)
- Employee model + EmployeeJobMatch model + admin
- Serializers + ViewSets + URLs
- Pytest authorization tests (cross-role denial)
- Migrations
- Dashboard KPI endpoint trong existing apps.admin_dashboard hoặc trong employees

### Phase 2: Backend US1 — bulk upload + matching

- `parsers.py` adapter wrap existing CV parser
- `matching.py` adapter gọi existing matching API → create EmployeeJobMatch records
- `tasks.py` Celery task `parse_and_match_employee(employee_id)` cho async bulk processing
- Endpoint `POST /api/admin/employees/bulk_upload/` chấp nhận multipart multi-file

### Phase 3: Admin UI

- `admin/src/types/employee.types.ts` + `match.types.ts`
- `admin/src/services/employee.service.ts` + `match.service.ts`
- Pages: `/admin/employees` (list + upload modal), `/admin/employees/[id]` (detail + matches tabs), `/admin/pipeline` (global table)
- Update `App.tsx` routing
- Update `admin-layout.tsx` navigation
- Dashboard widget KPI Pipeline

### Phase 4: Backend US4 — HR daily digest

- `apps.notifications` app
- `tasks.py` `send_hr_daily_digest_task` + `schedule_hr_digests` fanout
- Email template `hr_daily_digest.html`
- Management command `send_hr_digest --user-id X` cho dev
- Unsubscribe endpoint POST `/api/notifications/unsubscribe/<uuid>/`

### Phase 5: Verification + commit

- `python manage.py check` clean
- Existing matching + jobs tests PASS (zero regression)
- New employees tests PASS
- Admin SPA build OK
- Commit single (NO ml_service)

## Acceptance gates

- Phase 1 → CRUD Employee + Match work via curl/admin UI
- Phase 2 → bulk upload chạy, generate match records
- Phase 3 → UI demo-able end-to-end locally
- Phase 4 → `python manage.py send_hr_digest --user-id 1` prints HTML
- Phase 5 → zero regression
