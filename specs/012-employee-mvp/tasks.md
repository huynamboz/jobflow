---
description: "Task list for feature 012 — Employee MVP (internal HR tool)"
---

# Tasks: Employee MVP

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: minimal — pytest authorization + auto-transition for backend; smoke UI.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 0: Re-setup infra (carry-over from candidate-mvp)

- [ ] T001 Verify Redis service in docker-compose.yml (carried from rolled-back commit).
- [ ] T002 Verify requirements.txt has celery[redis], django-celery-beat, django-anymail, redis, pytest-django.
- [ ] T003 Verify backend/config/celery.py + __init__.py exists.
- [ ] T004 Verify settings.py has CELERY_*, EMAIL_BACKEND, FRONTEND_BASE_URL.

---

## Phase 1: Backend foundation — Employee + Match models (US2 + US3 foundation)

- [ ] T005 Tạo Django app: `python manage.py startapp employees apps/employees`.
- [ ] T006 Register apps.employees vào INSTALLED_APPS.
- [ ] T007 Write `apps/employees/models.py`:
  - Employee model theo data-model §E1
  - EmployeeJobMatch model theo data-model §E2
- [ ] T008 Write `apps/employees/permissions.py` — `IsHRStaff` (role IN admin, recruiter).
- [ ] T009 Write `apps/employees/serializers.py` — EmployeeListSerializer, EmployeeDetailSerializer, EmployeeJobMatchSerializer.
- [ ] T010 Write `apps/employees/views.py` — EmployeeViewSet, EmployeeJobMatchViewSet, PipelineKpiView (auto-transition logic in perform_update).
- [ ] T011 Write `apps/employees/urls.py` — DefaultRouter for Employee + Match + Kpi.
- [ ] T012 Write `apps/employees/admin.py` — Django admin registration.
- [ ] T013 Update `backend/config/urls.py` thêm `path("api/admin/", include("apps.employees.urls"))`.
- [ ] T014 Extend `apps/users/models.py` — User model thêm `notify_daily_digest=BooleanField(default=True)` + `unsubscribe_token=UUIDField(default=uuid.uuid4, unique=True, editable=False)`.
- [ ] T015 Generate migrations: `python manage.py makemigrations users employees`.
- [ ] T016 Write `apps/employees/tests.py` — authorization tests:
  - anonymous → 401
  - candidate role → 403
  - recruiter CRUD OK (except DELETE Employee)
  - admin DELETE OK
  - bulk_upload 51 files → 413
  - Match status=won → Employee.status=placed auto-transition

---

## Phase 2: Backend bulk upload + matching adapter (US1)

- [ ] T017 Write `apps/employees/parsers.py` — `parse_cv_file(file)` adapter:
  - Soft import from existing `apps.cvs.parser_service` hoặc `apps.cvs.services`
  - Return dict {skills, seniority, experience_years}
  - Fallback to empty dict + flag is_parse_failed
- [ ] T018 Write `apps/employees/matching.py` — `match_employee_to_jobs(employee, top_k)`:
  - Soft import from existing `apps.matching.services` hoặc construct CV text and call matching API internally
  - Return list of dicts {job_id, score, matched_skills}
- [ ] T019 Write `apps/employees/tasks.py` — Celery task `parse_and_match_employee(employee_id)` theo data-model §E7.
- [ ] T020 Update `EmployeeViewSet.bulk_upload` action: accept multipart files (max 50), create Employee stubs, enqueue tasks.

---

## Phase 3: Admin UI inside existing admin/ SPA (US1 + US2 + US3)

### Types + services

- [ ] T021 Write `admin/src/types/employee.types.ts` theo data-model §E9.
- [ ] T022 Write `admin/src/types/match.types.ts` theo data-model §E9.
- [ ] T023 Write `admin/src/services/employee.service.ts` — list, get, create, bulk_upload (multipart), update, delete, rescore.
- [ ] T024 Write `admin/src/services/match.service.ts` — list (filter), updateStatus, kpi.

### Shared components

- [ ] T025 [P] Write `admin/src/components/match-score-badge.tsx` — green/yellow/gray theo score.
- [ ] T026 [P] Write `admin/src/components/employee-status-chip.tsx` — color chip for Employee.status.
- [ ] T027 [P] Write `admin/src/components/match-status-chip.tsx` — color chip for Match.status.

### Pages

- [ ] T028 Write `admin/src/pages/admin/employees/index.tsx` — list + bulk upload modal + filter bar.
- [ ] T029 Write `admin/src/pages/admin/employees/detail.tsx` — profile + tabs (All/Suggested/Pursuing/Applied/Won/Lost) + match table với inline status change.
- [ ] T030 Write `admin/src/pages/admin/pipeline/index.tsx` — global match table với filter (employee, status, date) + KPI cards.
- [ ] T031 Update `admin/src/App.tsx` thêm 3 routes: `/admin/employees`, `/admin/employees/:id`, `/admin/pipeline`.
- [ ] T032 Update `admin/src/layouts/admin-layout.tsx` thêm 2 nav items (Employees, Pipeline) với icons Users + GitBranch.
- [ ] T033 Update `admin/src/pages/admin/dashboard/` thêm widget "Pipeline this week" (call kpi endpoint, render 4 mini stats + link).

---

## Phase 4: Backend HR daily digest (US4 — P2 scaffold)

- [ ] T034 Tạo Django app: `python manage.py startapp notifications apps/notifications`.
- [ ] T035 Register apps.notifications vào INSTALLED_APPS.
- [ ] T036 Write `apps/notifications/tasks.py` — `send_hr_daily_digest_task`, `schedule_hr_digests` theo data-model §E8.
- [ ] T037 Write `apps/notifications/templates/emails/hr_daily_digest.html` — responsive HTML với sections (new matches, pipeline changes, KPI, unsubscribe footer).
- [ ] T038 Write `apps/notifications/management/commands/send_hr_digest.py` — `--user-id X` cho dev.
- [ ] T039 Write `apps/notifications/views.py` + `urls.py` — POST `/api/notifications/unsubscribe/<uuid:token>/` set notify_daily_digest=False.
- [ ] T040 Update `backend/config/urls.py` thêm notifications routes.

---

## Phase 5: Verification (zero regression)

- [ ] T041 `python manage.py check` clean.
- [ ] T042 `pytest backend/apps/employees/ -q` PASS (authorization tests).
- [ ] T043 `pytest backend/apps/matching/ backend/apps/jobs/ -q` PASS (no regression existing).
- [ ] T044 Admin SPA build OK: `cd admin && pnpm build`.
- [ ] T045 ML regression smoke: `python scripts/smoke_test_movielens.py`, `smoke_test_careerbuilder.py`.

---

## Phase 6: Commit

- [ ] T046 Stage feature 012 artifacts only:
  ```
  git add backend/apps/employees/ backend/apps/notifications/ backend/apps/users/models.py \
          backend/apps/users/migrations/0002_*.py backend/config/ backend/docker-compose.yml \
          backend/requirements.txt admin/src/ \
          specs/012-employee-mvp/ CLAUDE.md .specify/feature.json
  ```
  TUYỆT ĐỐI KHÔNG add backend/ml_service/.
- [ ] T047 Verify clean: `git diff --cached --stat | grep ml_service` empty.
- [ ] T048 Commit với heredoc message describing 4 user stories + pivot rationale + zero regression.

---

## Dependencies

- Phase 0 → Phase 1, 2, 4 (parallel after setup)
- Phase 1 → Phase 2 + Phase 3 + Phase 4
- Phase 3 frontend depends on Phase 1+2 backend endpoints
- Phase 5 verify after all
- Phase 6 commit cuối

## MVP scope

T001-T033 → backend + UI ready demo. T034-T040 = digest scaffold. T041-T048 = verify + commit.

## Notes

- Pivot từ candidate-mvp (B2C public) → employee-mvp (B2B internal). Bỏ register/landing/candidate role flow.
- Reuse admin/ Vite + HeroUI + React Router + Zustand SPA → KHÔNG tạo separate Next.js app.
- Autonomous session implement Phase 0-4 + verify + commit (~1.5-2h).
- Production polish (Celery beat, SMTP, E2E tests) defer.
