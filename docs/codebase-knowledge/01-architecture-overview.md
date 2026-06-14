# Architecture Overview

JobFlow = hệ matching CV↔job cho HR "shadow staffing": HR upload CV nhân viên → LLM parse → GNN match với job crawl về → HR theo dõi apply. Monorepo: `backend/` (Django) + `admin/` (React SPA) + `specs/` (spec-kit) + `docs/codebase-knowledge/` (bộ doc này).

## Sơ đồ luồng dữ liệu chính

```
Crawlers (LinkedIn/Indeed/Adzuna/Remotive)          HR upload CV nhân viên
        │                                                  │
        ▼                                                  ▼
   Job + JobSkill  ◄─ LLM JD extraction            Employee (+cv_file)
   (role_category, seniority, exp, salary)          │ LLM CV parse (skills, seniority...)
        │                                                  │
        │   rebuild_job_pool (inductive encode, 018; incremental 027)  │
        ▼                                                  ▼
   pgvector job_pool_vec STORE ──────► InferenceEngine.match_cv ◄── match_cv_data (no-LLM)
   (027; snapshot file = fallback)      │  Stage1 retrieve (vector recall, 027) → Stage2 reranker
                                       ▼
                                  EmployeeJobMatch (top-100, dim_scores, prune)
                                       │
                              Admin SPA: employee detail browser, Job Tracking,
                              apply-by-email (LLM stream), morning digest
```

## Luồng ML (training — offline)

```
generate_pairs (role-aware selection) → PairQueue
→ LabelingBatch: LLM chấm (pair_scoring.md prompt) → HumanLabel (overall + 4 dims)
→ export_dataset.py → data/processed/b89_full
→ run_train_save.py (BPR + hard-neg curriculum) → checkpoints/latest (GNN + reranker + calibration)
→ tune_hybrid_weights (grid 4-weight, dual metric) → metadata.json hybrid_weights
```

## Backend apps (backend/apps/)

| App | Vai trò | Model chính |
|---|---|---|
| `jobs` | catalog + crawl + verify + JD extraction | **Job** (lifecycle, role_category, fingerprint), JobSkill, Platform, Company, JDExtractionBatch/Record, VerifierRunLog |
| `employees` | bề mặt nghiệp vụ chính | **Employee**, **EmployeeJobMatch** (pipeline status + dim_scores), apply-by-email streaming |
| `matching` | engine wrapper + train runs | MatchResult, Feedback, TrainRun (versioning + activate); services: matching_service (engine singleton), train_service |
| `cvs` | dataset CV + LLM extractor | CV (+CVSkill), CVExtractionBatch/Record; llm_cv_extractor |
| `labeling` | ground truth (LLM label) | LabelingCV/Job, PairQueue, LabelingBatch, **HumanLabel** |
| `skills` | taxonomy | Skill (canonical_name, category, aliases) |
| `llm` | LLM provider-agnostic | LLMProvider (openai/messages client), **LLMCallLog** (audit mọi call) |
| `schedule` | cron verify/extract/morning_refresh | VerifierSchedule (PID tracking, log tail) |
| `admin_dashboard` | KPI tổng hợp | services compute_kpi/catalog/freshness/ops/labeling/model |
| `users`, `notifications` | JWT auth, digest email | User (role, notify_daily_digest) |

## ML service (backend/ml_service/)

| Module | Nội dung | Doc chi tiết |
|---|---|---|
| `graph/` | schema (CVData/JobData), builder (HeteroData, node features) | [02](02-graph-features.md) |
| `models/` | HeteroGraphSAGE (proj→SAGE×3→MLPDecoder), HeteroRGCN | [05](05-training-pipeline.md) |
| `training/` | Trainer (BPR, hard-neg curriculum) | [05](05-training-pipeline.md) |
| `reranker/` | MLP 23-feature + 4 aux heads, Platt calibration | [05](05-training-pipeline.md) |
| `inference/` | engine (2-stage), checkpoint, job_pool_snapshot, **retrieval/ (exact\|vector seam, 027)**, **pgvector_store + pool_diff (027)**, role_classifier | [06](06-inference-pipeline.md) |
| `data/` | SkillNormalizer (145 skills), skill_graph (PMI/semantic), labeler (synthetic — unused prod) | [02](02-graph-features.md) |
| `embedding/` | MiniLM-L6-v2 384-dim (factory, BGE thay được) | [02](02-graph-features.md) |

## Frontend admin (admin/src/)

- React 18 + Vite + TS, HeroUI + Tailwind v4, theme teal Howard (#167a7a).
- Nav (`config/admin.ts`): **Staffing** = dashboard, employees (+detail job browser), jobs, job-tracking, morning-refresh, recommend · **System** = system, models, labeling, cvs, llm-providers, llm-logs, jd/cv/label-batch, schedule verify/extract.
- services/*.ts (axios `/api`), types/*.ts.

## Hạ tầng dev

- Postgres 16 docker **:5434** · Redis **:6380** (Celery optional — fallback thread pool).
- `config/settings.py`: ML_CHECKPOINT_DIR=checkpoints/latest, ML_SKILL_ALIAS_PATH; JWT 1h/7d; DRF Spectacular `/api/docs/`.
- Chạy: `docker compose up -d db` → `manage.py runserver 8000` → `npm run dev` (:5173).

## Bộ docs này

| File | Nội dung |
|---|---|
| [01-architecture-overview.md](01-architecture-overview.md) | (file này) bản đồ tổng |
| [02-graph-features.md](02-graph-features.md) | đồ thị, node features, role taxonomy, skill layer |
| [03-labeling-pipeline.md](03-labeling-pipeline.md) | pipeline LLM label (chọn cặp, prompt, batch, export) |
| [04-label-data-analysis.md](04-label-data-analysis.md) | phân tích định lượng 11.6k nhãn (crosstab, gap cross-domain) |
| [05-training-pipeline.md](05-training-pipeline.md) | train GNN (BPR/hard-neg) + reranker + checkpoint |
| [06-inference-pipeline.md](06-inference-pipeline.md) | engine 2-stage, hybrid score, job pool live, persist |
| [07-evaluation-tuning.md](07-evaluation-tuning.md) | tune weights (dual metric), eval harness, lịch sử 019/020 |
| [08-improvement-opportunities.md](08-improvement-opportunities.md) | gap đã xác định + hướng cải thiện ưu tiên |
