# Phase 0 Research: Inductive Live-Catalog Job Ranking

All items below were resolved against the current source — there are no open NEEDS CLARIFICATION.

## R1. How to embed new jobs without retraining

**Decision**: Mirror the existing inductive **CV** path for **jobs**, batched. Add all live jobs as `job` nodes onto a copy of the checkpoint graph (with `requires_skill` + `requires_seniority` edges), run one `model.encode()`, take `z_dict["job"]`.

**Rationale**: `_inductive_gnn_encode_cv` ([engine.py:523](../../backend/ml_service/inference/engine.py)) already proves GraphSAGE generalises to unseen nodes here — it appends a node + edges to a graph copy and re-encodes. GraphSAGE is inductive by construction; only the engine lacked a job path. One batched encode for all jobs is far cheaper than per-job or per-query encoding.

**Alternatives considered**:
- *Per-query inductive job encode*: rejected — one full graph forward pass per job per query is intractable for thousands of jobs.
- *Retrain / rebuild checkpoint*: rejected — heavy, defeats "no retraining", and unnecessary (weights generalise).
- *Incremental add only new jobs*: rejected by the user in favour of full rebuild (one `Job.id` space, no JDExtractionRecord↔Job overlap/dup bookkeeping).

## R2. Job-node feature recipe (must match build time)

**Decision**: Reproduce `builder.py` job features exactly: `concat( sentence_embed(text)[384], minmax(salary_min), minmax(salary_max), role_onehot[11] )` = **397 dims**, with `_ROLE_CATEGORIES` order from [builder.py:63](../../backend/ml_service/graph/builder.py). Factor this recipe into a shared helper used by both `builder.build()` and the new inductive path.

**Rationale**: The GNN's `job` projection layer expects 397-dim input in that exact column order. Any drift → silent quality loss. A shared helper removes the duplication risk.

**Alternatives considered**: Duplicate the recipe in the engine — rejected (drift risk).

## R3. Salary min-max normalization for new jobs

**Decision**: With **full rebuild**, recompute `minmax` over the **new live pool itself** (exactly as `builder.py` does over its job set). Self-consistent; no stored params needed.

**Rationale**: `_minmax(arr)` uses `arr.min()/max()` over the current job set. Since we replace the whole pool, the new pool *is* the normalization basis — identical semantics to build time. (Note: the existing inductive-CV path uses fixed divisors `exp/20, edu/4` instead of build-time minmax — an accepted approximation; the full-rebuild job path avoids that mismatch entirely.)

**Alternatives considered**: Persist salary ranges in the checkpoint — unnecessary under full rebuild. Recover ranges from the old frozen pool — only needed for incremental add (rejected path).

## R4. Reranker / Stage-2 impact

**Decision**: **No reranker change.** Extending `self._jobs`, `self._job_embeddings`, `self._job_text_vecs` is sufficient.

**Rationale**: `FeatureExtractor` ([reranker/features.py](../../backend/ml_service/reranker/features.py)) builds features purely from **JobData fields** (skills, importances, seniority, experience_min, role_category, text) + Stage-1 signals keyed by **`job.job_id`** (not array index) + a `gnn_score` passed in by the engine. It re-encodes job text itself in `extract_batch`. Nothing indexes the precomputed arrays. So once a new job is in `self._jobs` with a correct `gnn_score` (from the extended embeddings), reranking works unchanged.

**Risk carried**: the reranker + probability calibration were **trained on the old job distribution**. Generalisation is expected but unproven → see R7 (sanity-check gate).

## R5. Shared, realtime job pool (cross-process)

**Decision**: Persist the rebuilt pool to an on-disk **snapshot** `checkpoints/job_pool/` = `jobs.json` (JobData) + `job_embeddings.pt` (tensor) + `job_text_vecs.npy` + `meta.json` (count, built_at, source="live", model fingerprint). `InferenceEngine.from_checkpoint` loads the pool from the snapshot if present (overriding the checkpoint's frozen jobs). `_get_engine()` checks snapshot mtime and triggers an in-place pool reload when it changes.

**Rationale**: The engine is a per-process singleton; `morning_refresh` runs in its own process. A shared disk artifact is the simplest single-source-of-truth that both the live server and the maintenance job read. mtime check gives realtime reflection on the live server without a restart (FR-004) and without IPC.

**Atomicity**: write to `checkpoints/job_pool.tmp/` then `os.replace` the directory (or write files to a temp path + atomic rename) so a crash mid-rebuild never exposes a partial pool (FR-009). Reload reads under the engine's existing lock.

**Alternatives considered**: Recompute per process (inconsistent, wasteful); store embeddings in Postgres (heavier, no win); a reload HTTP endpoint (still needs the shared artifact; mtime is simpler — can add an explicit "reload engine" admin action later).

## R6. Identifier space + match persistence cleanup

**Decision**: New pool uses `JobData.job_id = Job.id`. `_persist_matches` ([apps/employees/tasks.py](../../backend/apps/employees/tasks.py)) resolves the engine `job_id` directly to `Job` by primary key; the `source_url` fallback becomes dead and is removed. `_enrich` ([matching_service.py](../../backend/apps/matching/services/matching_service.py)) reads metadata from `Job` instead of JDExtractionRecord/LabelingJob.

**Rationale**: Eliminates the "skipped" gap (FR-005, SC-002) and the documented `JDExtractionRecord.id ≠ Job.id` hazard. One id space end-to-end.

**Migration note**: Existing `EmployeeJobMatch` rows reference real `Job` rows already (matches were persisted via the source_url resolution), so no data migration is needed; the cutover is forward-only (next rebuild + re-match populates against `Job.id`).

## R7. Regression guard (reranker on new distribution)

**Decision**: After the first rebuild, run a **ranking sanity-check** on a fixed sample of CVs (via the `test-ranking` skill / a small scripted harness): compare top-K for the previously-covered jobs against the current engine; require top-K overlap ≥ an agreed tolerance (SC-004) before trusting the snapshot in production. Gate `morning_refresh` adoption on a successful first manual run.

**Rationale**: R4 carries an unproven-generalisation risk; a cheap empirical check converts it from "hope" to "verified".

**Alternatives considered**: Re-fit calibration on new jobs — heavier; defer unless the sanity-check shows drift.

## R8. Skills outside the checkpoint skill catalog

**Decision**: Skip the `requires_skill` edge for any job skill not in the checkpoint's `skill_to_idx` (graceful); the skill still contributes via the job **text** embedding. Log the per-rebuild count of skipped-skill edges for observability.

**Rationale**: Adding new skill *nodes* would change the skill graph + projection and edge toward retraining (out of scope). Text coverage keeps such jobs rankable, just with weaker graph signal. (After the 601-job cleanup, current coverage is 100%; this guards future crawls.)

## R9. Trigger + ordering

**Decision**: `morning_refresh` order becomes: (crawl + skill-extract upstream) → **rebuild_job_pool** (build JobData from DB → `engine.rebuild_job_pool` → save snapshot) → **re-match all employees** → **digest**. The live server picks up the new snapshot via R5 mtime reload.

**Rationale**: Re-match must run against the refreshed pool to surface new jobs that morning (US1). Digest already keys "new" off `created_at ≥ 24h`, so newly-created matches flow through unchanged.
