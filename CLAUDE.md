<!-- SPECKIT START -->
Active feature plan: [specs/022-relabel-dataset-buckets/plan.md](specs/022-relabel-dataset-buckets/plan.md)

Related artifacts:
- [spec.md](specs/022-relabel-dataset-buckets/spec.md)
- [research.md](specs/022-relabel-dataset-buckets/research.md)
- [data-model.md](specs/022-relabel-dataset-buckets/data-model.md)
- [contracts/cli.md](specs/022-relabel-dataset-buckets/contracts/cli.md)
- [agent-rubric.md](specs/022-relabel-dataset-buckets/agent-rubric.md)
- [quickstart.md](specs/022-relabel-dataset-buckets/quickstart.md)
- Master plan: [docs/codebase-knowledge/10-master-plan.md](docs/codebase-knowledge/10-master-plan.md)

Previous active plan: [specs/021-pipeline-foundation-fixes/plan.md](specs/021-pipeline-foundation-fixes/plan.md)

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
- **Job pool (feature 018)**: the GNN engine ranks against a job pool **rebuilt from the live `Job` catalog** (`job_id == Job.id`), persisted to an on-disk snapshot (`backend/checkpoints/job_pool/`, gitignored) that the live server hot-reloads on change (mtime). Rebuild it with `python manage.py rebuild_job_pool` (also run as step 1 of `morning_refresh`). New crawled jobs become rankable after a rebuild — no GNN retraining. The model weights + CV/skill/seniority graph stay frozen from `checkpoints/latest/`; only job nodes are re-encoded inductively. Matches now resolve 1:1 to `Job` (no more "skipped" gap). If no snapshot exists the engine falls back to the frozen checkpoint job pool (older JDExtractionRecord-id space, partial coverage).
- After editing `tailwind.config.js` or the HeroUI theme, **restart Vite** (build-time, not HMR).
- **Match weights (features 019+020)**: the hybrid score is **four-term** — `α·GNN + β·skill + γ·seniority + δ·domain` (domain = role match `engine._role_domain_fit`, SOFT term, no hard filter) — tuned by `python manage.py tune_hybrid_weights` (4-weight grid; default **balanced** objective = max role-NDCG@10 s.t. label-AUC ≥ 0.85·max and δ ≤ 0.4 — a pure role-NDCG objective is degenerate at δ=1.0) and loaded from checkpoint `metadata.json` `hybrid_weights` (single source of truth; `settings.py` values are training-only). Current tuned: `0.10/0.25/0.25/0.40`, dual ablation at `specs/020-domain-aware-ranking/ablation.md`. Quality harness: `python manage.py eval_matching` (fixed 20-CV set → on-domain@k; 50%→90% after 020). The four per-dimension scores are **transparent formulas** in `engine._dimension_scores` — reproducible by hand. Re-match (`rematch_employees`/`morning_refresh`) to adopt new weights/dims; restart the server to load them. **Thứ tự bắt buộc khi tune (A14): chốt weights vào metadata TRƯỚC → retrain reranker SAU** — reranker_meta.json lưu `trained_with_weights`, engine WARN to khi lệch với serving weights.
