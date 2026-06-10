<!-- SPECKIT START -->
Active feature plan: [specs/018-inductive-job-pool/plan.md](specs/018-inductive-job-pool/plan.md)

Related artifacts:
- [spec.md](specs/018-inductive-job-pool/spec.md)
- [research.md](specs/018-inductive-job-pool/research.md)
- [data-model.md](specs/018-inductive-job-pool/data-model.md)
- [contracts/engine-api.md](specs/018-inductive-job-pool/contracts/engine-api.md)
- [contracts/cli.md](specs/018-inductive-job-pool/contracts/cli.md)
- [quickstart.md](specs/018-inductive-job-pool/quickstart.md)
- [checklists/requirements.md](specs/018-inductive-job-pool/checklists/requirements.md)

Previous active plan: [specs/014-employee-shadow-enhance/plan.md](specs/014-employee-shadow-enhance/plan.md)

Previous features (still in this branch's history):
- [specs/013-thesis-report/plan.md](specs/013-thesis-report/plan.md) (Thesis report — Vietnamese academic doc)
- [specs/012-employee-mvp/plan.md](specs/012-employee-mvp/plan.md) (Employee MVP — internal HR tool, in-progress)
- [specs/011-thesis-defense-prep/plan.md](specs/011-thesis-defense-prep/plan.md) (Thesis defense — LSTM/BiLSTM)
- [specs/010-lightgcn-baseline/plan.md](specs/010-lightgcn-baseline/plan.md) (LightGCN GNN baseline)
- [specs/009-careerbuilder-benchmark/plan.md](specs/009-careerbuilder-benchmark/plan.md) (main standard benchmark — HeteroSAGE)
- [specs/008-movielens-benchmark/plan.md](specs/008-movielens-benchmark/plan.md) (validation cell)
- [specs/007-duplicate-ml-benchmark/plan.md](specs/007-duplicate-ml-benchmark/plan.md) (sandbox foundation)
- [specs/003-admin-dashboard-v2/plan.md](specs/003-admin-dashboard-v2/plan.md)
- [specs/002-job-date-posted-extraction/plan.md](specs/002-job-date-posted-extraction/plan.md)
- [specs/001-linkedin-job-verifier/plan.md](specs/001-linkedin-job-verifier/plan.md)
<!-- SPECKIT END -->

# JobFlow — Tech Stack & Project Map

AI-powered CV↔job matching for an internal HR / IT-outsourcing ("shadow staffing")
workflow: HR uploads employee CVs, the system parses them with an LLM, matches them
to crawled jobs with a GNN, and HR drives applications.

## Backend — `backend/` (Django REST API)

- **Language/runtime**: Python 3.11 (venv at `backend/.venv`).
- **Framework**: Django 5.2 + Django REST Framework. JWT auth (SimpleJWT).
- **DB**: PostgreSQL 16 (dev: docker `jobflow-db` on **:5434** — `cd backend && docker compose up -d db`). Env via `.env` (auto-loaded by `python-dotenv` in `config/settings.py`).
- **Async**: Celery + Redis broker (dev Redis **:6380**). Celery is **optional** — if no worker/broker, employee CV parse+match falls back to an in-process **thread pool** (`apps/employees/views.py::_process_employee`).
- **ML** (`backend/ml_service/`): PyTorch + PyTorch-Geometric **HeteroGraphSAGE** GNN, `sentence-transformers` (all-MiniLM-L6-v2) embeddings, an MLP reranker. Two-stage retrieve→rerank in `ml_service/inference/`.
- **LLM**: provider-agnostic `apps.llm.service.LLMService` (configurable providers in DB → admin "LLM Providers"; every call logged to `LLMCallLog` → admin "LLM Logs"). Used for **CV extraction** (`apps/cvs/services/llm_cv_extractor.py`, `LLMCVParser`) and JD extraction.
- **Parsing/crawling**: pdfplumber (PDF), python-docx (DOCX); crawlers for Indeed (JobSpy), LinkedIn (Playwright), Adzuna, Remotive; Playwright job verifier.
- **Key apps** (`backend/apps/`): `employees` (staff CVs + job matches, the active surface), `matching` (CV↔job engine + parse/match services), `jobs` (catalog + admin job CRUD), `cvs` (labeling dataset + LLM extractor), `skills`, `users`, `labeling`, `llm`, `schedule`, `notifications`, `admin_dashboard`.

## Frontend — `admin/` (React admin SPA)

- **Stack**: React 18 + **Vite 6** + TypeScript. Dev server on **:5173** (`cd admin && npm run dev`).
- **UI**: **HeroUI** component library + **Tailwind CSS v4**. Icons: `@tabler/icons-react` (+ some `lucide-react`). Router: React Router. HTTP: Axios (`src/lib/api-client.ts`, base `/api`, bearer token).
- **Theming** (howard-websites look): tokens in `src/styles/node-tokens.css` + a **Howard override** block in `src/styles/globals.css` (teal brand `#167a7a`, slate greys, Inter font, `--card-border`/`--card-radius`). HeroUI semantic colors set in `tailwind.config.js` (primary=teal, slate bg/fg). Shared card primitive: **`src/components/ui/card.tsx`** (`rounded-2xl border border-card-border`, optional hover lift). Prefer Tailwind utility classes + HeroUI semantic colors over ad-hoc inline styles for new UI.
- **Layout**: `src/layouts/admin-layout.tsx` + navy `admin-sidebar.tsx` (nav config in `src/config/admin.ts` — "Staffing" group = business pages, "System" = technical tooling). Pages in `src/pages/admin/`, services in `src/services/`, types in `src/types/`.

## Repo layout

- `backend/` Django API · `admin/` React SPA · `specs/` spec-kit features · `roadmap/` business docs (`build-backlog.md`, `business-functions-hr-staffing.md`, `workflow-and-screens.md`).

## Dev runbook

```bash
# DB + backend
cd backend && docker compose up -d db && .venv/bin/python manage.py runserver 8000
# admin (Vite — restart it after changing tailwind.config.js / theme)
cd admin && npm run dev
# tests / build
cd backend && .venv/bin/python manage.py test apps.employees
cd admin && npm run build && npx tsc --noEmit
```

## Notes / gotchas

- Employee CV parsing is **LLM-based** → needs a funded LLM provider active; failures surface in LLM Logs and as `is_parse_failed` on the employee.
- The GNN engine's `job_id` is a `JDExtractionRecord` id, not always a `Job` id — the employee adapter only persists matches whose `job_id` resolves to a real `Job` (others skipped). Live employee matching is therefore partial until that mapping is reconciled.
- After editing `tailwind.config.js` or the HeroUI theme, **restart Vite** (build-time, not HMR).
