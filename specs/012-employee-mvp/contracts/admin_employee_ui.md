# Contract: Admin UI for Employees & Pipeline

**Date**: 2026-05-22

## Routes (inside existing admin SPA)

| Path | Auth | Description |
|---|---|---|
| `/admin/employees` | admin/recruiter | List employees + bulk upload modal |
| `/admin/employees/:id` | admin/recruiter | Employee detail + matches tabs |
| `/admin/pipeline` | admin/recruiter | Global match pipeline table |

## `/admin/employees` (List page)

**Layout**: Existing `AdminLayout` shell.

**Sections**:
1. Header: title "Employees" + button **[+ Add employees]** (opens modal)
2. Filter bar: search input, status select (bench/pursuing/placed/inactive), seniority select
3. Table:
   - Columns: Name | Position | Seniority | Skills (truncated) | Status badge | Matches | Actions
   - Pagination 20/page
   - Row click → `/admin/employees/:id`
4. Upload modal:
   - Multi-file dropzone (PDF/DOCX up to 50)
   - Progress per-file (queued → uploading → parsing → done)
   - Polling GET /api/admin/employees/?status=parsing để update progress

**HeroUI components**: Table, Modal, Input, Select, Button, Chip.

## `/admin/employees/:id` (Detail page)

**Sections**:
1. Header: full name + status chip + actions (Edit, Delete, Re-score)
2. Profile card: position, seniority, experience, email, phone, parsed skills (chips)
3. Tabs:
   - **All matches**: top 30 jobs sorted by score desc
   - **Suggested**, **Pursuing**, **Applied**, **Won**, **Lost**: filtered tabs
4. Match table:
   - Columns: Job title | Company | Location | Score badge | Status dropdown | Notes | Updated
   - Action: change status inline; notes inline edit
5. CV preview: download link to original PDF/DOCX

## `/admin/pipeline` (Global pipeline)

**Sections**:
1. Header + filter bar: employee select, status select, date range, search
2. Table:
   - Columns: Employee | Job | Score | Status | Assigned to | Applied at | Updated
   - Sort: by score, by updated
   - Pagination 50/page
3. KPI cards at top:
   - Total bench, total pursuing, placed this week, lost this week

## Dashboard widget (existing `/admin`)

Add new card: "Pipeline this week"
- 4 mini stats: bench / pursuing / applied / won
- Link "View all" → `/admin/pipeline`

## Nav additions (in `admin-layout.tsx`)

Add menu items (under existing groups):
- "Employees" → `/admin/employees` (icon: Users)
- "Pipeline" → `/admin/pipeline` (icon: GitBranch)

## Component patterns (reuse existing)

- `ChipStatus` for color-coded status badges (use HeroUI Chip)
- `MatchScoreBadge` new component: percentage + green/yellow/gray
- Reuse existing `JobDetailDrawer` if exists (or simple modal)
- `BulkUploadDropzone` new component

## Loading + errors

- Skeleton on initial load (HeroUI Skeleton hoặc shimmer divs)
- Toast (HeroUI ToastProvider — đã có) cho mutations
- Error boundary cho route-level failures

## Acceptance per page

- `/admin/employees`: list 100 employees renders < 1s server-side pagination
- Bulk upload: pick 10 files → toast "Queued 10 employees" → list refresh polling
- `/admin/employees/:id`: load detail + matches < 2s
- `/admin/pipeline`: filter changes update table < 500ms
- Dashboard widget updates after employee action
