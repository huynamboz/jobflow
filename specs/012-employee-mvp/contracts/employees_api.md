# Contract: Employees & Matches API

**Date**: 2026-05-22

Base path: `/api/admin/employees/`, `/api/admin/matches/`
Auth: JWT, role `admin` or `recruiter` only (custom `IsHRStaff` permission).

## Employee endpoints

### `GET /api/admin/employees/`
Query: `?status=bench&seniority=3&search=python&page=1`
Response 200:
```json
{
  "success": true, "count": 42,
  "results": [{"id": 1, "full_name": "...", "status": "bench", "match_count": 18, ...}]
}
```

### `POST /api/admin/employees/`
Single Employee create (body JSON), no CV file.

### `POST /api/admin/employees/bulk_upload/`
Multipart, field `files[]` (up to 50). Async parse + match.
Response 201:
```json
{
  "success": true,
  "data": [{"id": 1, "full_name": "alice.pdf", "status": "bench"}, ...]
}
```

### `GET /api/admin/employees/{id}/`
Full detail + nested match counts.

### `PATCH /api/admin/employees/{id}/`
Update editable fields.

### `DELETE /api/admin/employees/{id}/`
Admin role only.

### `POST /api/admin/employees/{id}/rescore/`
Re-enqueue parse + match generation. Useful after CV file replaced.

## Match endpoints

### `GET /api/admin/matches/?employee_id=&status=&assigned_to=`
Filter, sort by match_score desc default.

### `PATCH /api/admin/matches/{id}/`
Body `{"status": "pursuing", "notes": "..."}`. Auto-set timestamps + auto-transition Employee.

### `DELETE /api/admin/matches/{id}/`
Admin only.

## Pipeline KPI

### `GET /api/admin/pipeline/kpi/`
Response: counts by status (employees + matches this week) + top 10 pursuing employees.

## Errors

| Code | When |
|---|---|
| 400 | invalid body |
| 401 | no JWT |
| 403 | role not in (admin, recruiter); or recruiter trying DELETE |
| 404 | not found |
| 413 | bulk_upload > 50 files |

## Test scenarios

- Anonymous → 401 all endpoints
- Candidate role → 403
- Recruiter can CRUD Employee + Match (except DELETE)
- Admin can DELETE
- bulk_upload 51 files → 413
- Update Match → applied: sets applied_at
- Update Match → won: sets won_at + Employee.status = placed
