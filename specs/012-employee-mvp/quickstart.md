# Quickstart — Verify Employee MVP locally

**Date**: 2026-05-22

## Prerequisites

- Docker + docker-compose (postgres + redis)
- Backend venv + deps
- pnpm cho admin SPA
- Feature 011 đã merge

## Step 1 — Start infra

```bash
cd backend
docker compose up -d db redis
```

## Step 2 — Backend migrate + run

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser  # role admin
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

## Step 3 — Verify Employee API (curl)

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"adminpass"}' | jq -r .access)

# Create employee
curl -X POST http://localhost:8000/api/admin/employees/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Alice", "email": "alice@acme.com", "seniority": 3}'

# Bulk upload (multipart)
curl -X POST http://localhost:8000/api/admin/employees/bulk_upload/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@cv1.pdf" -F "files=@cv2.pdf"

# List
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/employees/

# Pipeline KPI
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/pipeline/kpi/
```

## Step 4 — Admin SPA dev

```bash
cd admin
pnpm install
pnpm dev   # http://localhost:5173
```

Navigate to `/admin/employees` after login.

## Step 5 — Smoke flow (UI)

1. Login với admin user
2. Sidebar có 2 menu mới: Employees + Pipeline
3. Vào `/admin/employees` → click "Add employees" → chọn 2-3 CV PDF → upload
4. Sau ~30s, list refresh → thấy employees mới với match count
5. Click vào employee → tab "All matches" có top jobs
6. Đổi status 1 match: suggested → pursuing → applied → won → verify employee status = placed
7. Vào `/admin/pipeline` → bảng tất cả match
8. Dashboard `/admin` có widget KPI Pipeline

## Step 6 — HR daily digest (dev console)

```bash
cd backend
.venv/bin/python manage.py send_hr_digest --user-id 1
```

Expect: HTML email printed to console.

## Step 7 — Regression

```bash
cd backend
pytest backend/apps/matching/ backend/apps/jobs/ -q
.venv/bin/python scripts/smoke_test_movielens.py
.venv/bin/python scripts/smoke_test_careerbuilder.py
```

Cả PASS.

## PASS table

| Step | Tiêu chí | |
|---|---|---|
| 1 | infra up | ☐ |
| 2 | migrate clean | ☐ |
| 3 | API CRUD work | ☐ |
| 4 | admin SPA serves | ☐ |
| 5 | UI flow end-to-end | ☐ |
| 6 | digest prints HTML | ☐ |
| 7 | zero regression | ☐ |
