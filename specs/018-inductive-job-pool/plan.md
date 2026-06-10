# Implementation Plan: Inductive Live-Catalog Job Ranking

**Branch**: `018-inductive-job-pool` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-inductive-job-pool/spec.md`

## Summary

Make newly-crawled jobs rankable by the existing GNN matcher **without retraining**. Today `InferenceEngine` ranks a CV only against `self._jobs` — a frozen pool baked into the training checkpoint (the JDExtractionRecord set) — with job embeddings precomputed once at load. New jobs in the live `Job` table are never scored, and ~25% of returned candidates don't resolve to a real `Job` (the "skipped" gap).

Approach (decided): **rebuild the engine's job pool from the live `Job` catalog**. Job nodes are encoded **inductively** in one batched GNN forward pass onto a frozen copy of the checkpoint's CV/skill/seniority graph (model weights + non-job graph unchanged). The rebuilt pool (JobData + GNN embeddings + text vectors) is persisted to an on-disk **snapshot** shared by the live server and the `morning_refresh` process; the engine loads from the snapshot when present and hot-reloads on snapshot change. The match identifier becomes `Job.id`, collapsing the JDExtractionRecord↔Job indirection and the skipped gap. The reranker is unchanged (verified). A ranking sanity-check guards regression.

## Technical Context

**Language/Version**: Python 3.11 (backend `.venv`)

**Primary Dependencies**: PyTorch + PyTorch-Geometric (HeteroGraphSAGE), sentence-transformers (all-MiniLM-L6-v2, 384-dim), Django 5.2 / DRF, PostgreSQL 16

**Storage**: PostgreSQL (`Job`, `JobSkill`, `EmployeeJobMatch`); on-disk model checkpoint (`checkpoints/latest/`) + NEW on-disk job-pool snapshot (`checkpoints/job_pool/`)

**Testing**: Django `manage.py test` (apps.matching, apps.employees); ML sanity-check via the `test-ranking` skill on a fixed CV sample

**Target Platform**: Linux/macOS server (Django runserver / gunicorn); single in-process ML engine per worker (`apps/matching/services/matching_service.py::_get_engine`, module-level singleton + lock)

**Project Type**: Web service (Django backend) + ML inference library (`backend/ml_service/`)

**Performance Goals**: Full-catalog rebuild (~6.5k jobs) completes within the overnight→morning window (target ≤ a few minutes; dominated by 1 sentence-embed batch over job texts + 1 GNN forward pass). Per-query matching latency unchanged (still iterates `self._jobs` with precomputed vectors).

**Constraints**: No GNN retraining. Snapshot writes must be atomic (a failed/partial rebuild must leave the previous snapshot serving). Engine reload must be thread-safe with in-flight `match_cv` calls. Job feature recipe MUST byte-for-byte match `builder.py` (397-dim) or embeddings silently degrade.

**Scale/Scope**: ~6.5k live jobs (growing); ~7k CVs + skill/seniority nodes frozen from checkpoint; single tenant.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unfilled template (no ratified principles). No gates to enforce → **PASS** (trivially). General engineering guardrails adopted for this feature: reuse the existing inductive-encode mechanism rather than inventing a new path; no retraining; additive disk artifact (no schema migration required); behaviour-preserving for already-covered jobs (guarded by sanity-check).

## Project Structure

### Documentation (this feature)

```text
specs/018-inductive-job-pool/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions + rationale (salary norm, atomic write, reload, id space, sanity-check)
├── data-model.md        # Phase 1 — JobData-from-DB, snapshot format, entity mapping
├── quickstart.md        # Phase 1 — how to rebuild + verify + roll back
├── contracts/
│   ├── engine-api.md    # rebuild_job_pool / load-from-snapshot / reload contract
│   └── cli.md           # `rebuild_job_pool` management command contract
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── ml_service/
│   ├── inference/
│   │   ├── engine.py          # ADD rebuild_job_pool(jobs) + _inductive_gnn_encode_jobs(batch) +
│   │   │                      #   snapshot load in from_checkpoint; reuse _inductive_gnn_encode_cv pattern
│   │   ├── job_pool_snapshot.py  # NEW: save/load snapshot (jobs.json + job_embeddings.pt + job_text_vecs.npy), atomic
│   │   └── checkpoint.py      # unchanged (reference for serialization helpers)
│   └── graph/
│       └── builder.py         # SOURCE OF TRUTH for the 397-dim job-node recipe (lines 62-138) — factor a shared helper
├── apps/
│   ├── matching/
│   │   └── services/
│   │       └── matching_service.py   # _get_engine snapshot mtime reload; build_jobdata_from_db(); simplify _enrich (Job.id)
│   ├── jobs/
│   │   └── models.py          # Job + JobSkill (read-only source for JobData)
│   └── employees/
│       ├── tasks.py           # _persist_matches keyed on Job.id (drop source_url indirection); _do_rematch
│       └── management/commands/
│           ├── rebuild_job_pool.py   # NEW: build JobData from DB → engine.rebuild_job_pool → save snapshot
│           └── morning_refresh.py    # wire rebuild_job_pool before the re-match step
```

**Structure Decision**: Single Django backend + in-repo `ml_service` library (existing layout). The feature is backend/ML only — **no frontend changes** (the dashboard/digest/"Refresh jobs" surfaces already consume `EmployeeJobMatch`; they improve automatically once the pool covers live jobs). New code is one ML module (snapshot I/O), additive engine methods, one management command, and small edits to the matching adapter + morning_refresh. No DB migration.

## Complexity Tracking

No constitution violations. The one genuinely non-trivial area — keeping the inductive job-node feature recipe identical to build time — is mitigated by **factoring the 397-dim recipe out of `builder.py` into a shared helper** reused by both build and inductive paths (single source of truth), rather than duplicating it.
