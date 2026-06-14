# Implementation Plan: Scalable Job-Pool Retrieval

**Branch**: `027-job-retrieval-scaling` | **Date**: 2026-06-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/027-job-retrieval-scaling/spec.md`

## Summary

Split the matcher's fused retrieve+score into a cheap **recall** step and an exact **scoring** step behind a single `Retriever` seam, then make recall progressively cheaper to compute, store, and update — without retraining and without moving the 4-term hybrid score, reranker, or Platt calibration. Three independently shippable stages: **A** in-memory vectorized recall (the big win), **B** pgvector ANN (when N is huge), **C** incremental pool refresh (ops). `eval_matching` (on-domain@k + calibrated-P tolerance) is the merge gate for every stage; `RETRIEVAL_MODE=exact` stays a permanent A/B baseline and rollback. See [research.md](research.md) for decisions D1–D5.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: Django 5.2 + DRF, PyTorch + PyTorch-Geometric (HeteroGraphSAGE, frozen), sentence-transformers (multilingual MiniLM-L12), NumPy; Stage B adds `pgvector` (Postgres extension) + Django/Python bindings.

**Storage**: PostgreSQL 16 (existing). On-disk job-pool snapshot under `backend/checkpoints/job_pool/` (existing, gitignored). Stage B adds table `job_pool_vec`.

**Testing**: Django test runner (`manage.py test apps.matching`); `eval_matching` (fixed 20-CV → on-domain@k) as the quality gate; parity/latency micro-benchmarks.

**Target Platform**: Linux/macOS single-process Django server + management commands.

**Project Type**: Web service (Django backend) — ML serving subsystem. No frontend change.

**Performance Goals**: Retrieval sub-second at 100k jobs (Stage A) and at 200k+ jobs (Stage B); match latency flat (not linear) in catalog size. Refresh time O(new+changed), not O(catalog) (Stage C).

**Constraints**: Frozen model weights (no retraining). Do not change the 4-term hybrid formula, reranker, Platt calibration, or the ≥2-skill eligibility rule. Each stage behind `RETRIEVAL_MODE` and independently rollback-able. on-domain@k must not regress; calibrated P within tolerance (±0.005 proposed) on the 20-CV set.

**Scale/Scope**: Catalog 8k → 100k (Stage A target) → 200k+ (Stage B). Single serving process; no sharding.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unfilled template (placeholder principles), so there are no ratified gates to evaluate. Applying the project's de-facto engineering norms instead:

- **No silent quality regression** — every stage gated on `eval_matching` + calibration tolerance. ✅ designed in (FR-004, SC-001/002).
- **Reversibility** — `RETRIEVAL_MODE` flag, `exact` permanent baseline. ✅
- **Frozen-model discipline** — no retraining; inductive encode only. ✅
- **Single source of truth for weights/calibration** — untouched; only retrieval changes. ✅

No violations → Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/027-job-retrieval-scaling/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions D1–D5
├── data-model.md        # Phase 1 — entities (job_pool_vec, content_hash, shortlist)
├── quickstart.md        # Phase 1 — how to enable/validate each stage
├── contracts/
│   └── retriever.md     # Phase 1 — the Retriever interface contract
└── tasks.md             # Phase 2 — /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
backend/
├── ml_service/inference/
│   ├── engine.py                 # match_cv: call retriever.shortlist() then exact-score the shortlist;
│   │                             #   precompute unit-norm job matrices; wire RETRIEVAL_MODE
│   ├── retrieval/                # NEW — the Retriever seam (Stage A/B implementations)
│   │   ├── __init__.py           #   get_retriever(mode) factory
│   │   ├── base.py               #   Retriever protocol: shortlist(cv_text_vec, cv_gnn_emb, k)
│   │   ├── exact.py              #   ExactRetriever (wraps today's full composite loop) — A/B baseline
│   │   ├── vector.py             #   VectorRetriever (Stage A — in-memory matmul + argpartition)
│   │   └── pgvector.py           #   PgVectorRetriever (Stage B — SQL ANN)
│   ├── job_pool_snapshot.py      # Stage C — store/read content_hash map in snapshot meta
│   └── pool_diff.py              # NEW (Stage C) — diff live catalog vs stored hashes
├── apps/matching/
│   ├── migrations/               # Stage B — CREATE EXTENSION vector + job_pool_vec table/index
│   ├── models.py                 # Stage B — JobPoolVec model (or unmanaged + raw SQL)
│   └── management/commands/
│       ├── rebuild_job_pool.py   # Stage C — incremental diff + --full; Stage B — upsert job_pool_vec
│       └── eval_matching.py      # add recall@shortlist + calibrated-P-drift reporting (gate)
├── config/settings.py            # RETRIEVAL_MODE, RETRIEVE_K, W_GNN/W_TEXT, HNSW params (defaults)
└── tests (apps/matching/tests.py + ml_service tests)
```

**Structure Decision**: Web-service backend; all work is in `backend/ml_service/inference/` (serving) and `backend/apps/matching/` (commands, Stage B schema). New `ml_service/inference/retrieval/` package isolates the swappable retrievers behind one interface. No frontend, no API-contract change (matching result shape is unchanged).

## Implementation Phases (delivery order)

The three user stories ship in priority order; each is a mergeable increment gated by `eval_matching`.

### Stage A (US1, P1) — vectorized recall · **MVP**
1. Extract the `Retriever` protocol + `ExactRetriever` (refactor today's loop, behaviour-identical) behind `RETRIEVAL_MODE=exact`. Prove bit-for-bit parity vs pre-refactor on the 20-CV set.
2. Precompute unit-norm job matrices at pool load + snapshot reload.
3. `VectorRetriever`: two mat-vecs + `argpartition` top-`RETRIEVE_K`; engine scores only the shortlist.
4. Add `recall@shortlist` + calibrated-P-drift to `eval_matching`. Tune `RETRIEVE_K`/`W_*` to parity. Flip default to `vector`.
**Exit**: on-domain@k ≥ baseline, P within tol, latency flat to 100k (synthetic-inflation bench).

### Stage B (US2, P2) — pgvector  → **STORE kept, ANN retriever removed**
Outcome (measured): the per-request ANN **retriever** was built, validated, then **removed** — it needed a 2× shortlist (embedding-only ranking) so it ran more of the expensive decoder re-scores than `vector` for no win (research D3). What shipped:
1. Migration: `CREATE EXTENSION vector`; `job_pool_vec` table (`gnn_emb`/`text_vec`/`model_fingerprint`/`content_hash`); 0003 drops the ANN/role indexes.
2. pgvector as the pool **store**: `rebuild_job_pool` upserts embeddings; serving **loads the pool from pgvector at startup** + hot-reloads on version change (matching_service).
**Exit**: store-backed pool load + incremental upsert, validated on the warm server (load 8930 jobs, rematch correct). The real next scaling lever is **batching the decoder** (rerank), not ANN.

### Stage C (US3, P3) — incremental refresh
1. `content_hash` per JobData; persist prior hashes (snapshot meta / `job_pool_vec`).
2. `pool_diff` → encode only new/changed, reuse unchanged, evict removed/ineligible; `--full` flag.
3. Weekly full-rebuild safety net in `morning_refresh`.
**Exit**: refresh encodes only deltas; incremental == full on unchanged catalog (diff check).

## Complexity Tracking

> No constitution violations — section intentionally empty.
