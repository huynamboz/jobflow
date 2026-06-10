---
description: "Task list — Inductive Live-Catalog Job Ranking"
---

# Tasks: Inductive Live-Catalog Job Ranking

**Input**: Design documents from `specs/018-inductive-job-pool/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: Included (R7 sanity-check is a hard gate; a few unit tests guard the mapping + snapshot). Not full TDD.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: US1 / US2 / US3 (from spec.md). Setup/Foundational/Polish have no story label.
- All paths are repo-relative; backend root = `backend/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture a regression baseline before touching the engine.

- [x] T001 Capture ranking baseline: script in `backend/` that runs `match_cv_data` for ~3 fixed employees against the CURRENT engine and saves their top-10 `(job_id, score)` to `specs/018-inductive-job-pool/baseline.json` (used by the SC-004 sanity-check in T011).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The job-pool rebuild mechanism + snapshot + DB→JobData. Every user story depends on these.

⚠️ No user story can be completed until this phase is done.

- [x] T002 [P] Factor the 397-dim job-node feature recipe into a shared helper `build_job_node_features(jobs, embed)` in `backend/ml_service/graph/builder.py` (text emb[384] + minmax(salary_min)+minmax(salary_max) + role_onehot[11], `_ROLE_CATEGORIES` order preserved) and call it from `JobGraphBuilder.build()` — single source of truth.
- [x] T003 Add `_inductive_gnn_encode_jobs(jobs)` to `backend/ml_service/inference/engine.py` (mirror `_inductive_gnn_encode_cv`, batched): copy graph via `_strip_label_edges`, append job nodes using T002 helper, add `requires_skill` (attr=importance, skills in `skill_to_idx` only) + `requires_seniority` edges, `prepare_data_for_gnn` → one `model.encode()` → return new-job slice of `z_dict["job"]` + skipped-skill-edge count.
- [x] T004 Add `InferenceEngine.rebuild_job_pool(jobs)` to `backend/ml_service/inference/engine.py`: call T003, compute `job_text_vecs = self._embed.encode([j.text for j in jobs])`, then under `self._inductive_lock` atomically swap `self._jobs`, `self._job_embeddings`, `self._job_text_vecs`; return `RebuildReport{num_jobs, skill_skipped_edges, encode_seconds}`; raise on dim mismatch.
- [x] T005 [P] Create `backend/ml_service/inference/job_pool_snapshot.py` with `save(dir, jobs, embeddings, text_vecs, model_sig, skipped)` (atomic: write temp sibling dir → `os.replace`) and `load(dir, model_sig) -> (jobs, embeddings, text_vecs) | None` (validate length invariant + `model_sig`); files `jobs.json` (reuse `checkpoint._job_to_dict`), `job_embeddings.pt`, `job_text_vecs.npy`, `meta.json`.
- [x] T006 Add `build_jobdata_from_db()` to `backend/apps/matching/services/matching_service.py`: `Job` + `JobSkill` → `JobData` per `data-model.md` (job_id=`Job.id`, normalized skills + importances, seniority, salary_min/max, text=title+description, role_category); exclude jobs with no catalog-mappable skill.
- [x] T007 Create management command `backend/apps/matching/management/commands/rebuild_job_pool.py`: `build_jobdata_from_db()` → `_get_engine().rebuild_job_pool(jobs)` → `job_pool_snapshot.save(...)`; flags `--limit`, `--dry-run`, `--no-save`; print `built N, S skipped-edges, encode T s, snapshot=path`; non-zero exit on empty set / dim mismatch.

**Checkpoint**: `python manage.py rebuild_job_pool --limit 50 --dry-run` runs and reports counts.

---

## Phase 3: User Story 1 — Newly-crawled jobs matched the same day (P1) 🎯 MVP

**Goal**: After the daily refresh, jobs crawled post-training are ranked and surface in employees' matches + the morning digest.

**Independent test**: Insert a post-checkpoint `Job` (with skills) → `rebuild_job_pool` → `rematch_employees --employee X` → the new job appears in X's matches with **0 skipped**.

- [x] T008 [US1] Update `_enrich` in `backend/apps/matching/services/matching_service.py` to read job metadata from `Job` by `Job.id` (title/company/location/salary/source_url) instead of `JDExtractionRecord`/`LabelingJob`.
- [x] T009 [US1] Update `_persist_matches` in `backend/apps/employees/tasks.py` to resolve the engine `job_id` directly to `Job` by primary key (new pool = `Job.id`); keep `update_or_create` idempotency + pipeline-status preservation.
- [x] T010 [US1] Wire `rebuild_job_pool` as step `[0]` in `backend/apps/employees/management/commands/morning_refresh.py` (before the re-match step); update help text + per-step logging.
- [x] T011 [US1] Sanity-check harness (R7/SC-004): script that re-runs the T001 sample on the rebuilt pool, diffs top-K vs `baseline.json` for already-covered jobs, and asserts overlap ≥ tolerance (e.g. ≥0.6); document the result. **Gate**: do not enable T010 in production until this passes.
- [x] T012 [US1] Integration verification: insert a synthetic post-checkpoint `Job`+`JobSkill` fitting a known employee → `rebuild_job_pool` → `rematch_employees --employee <ID>` → assert the new `Job.id` is in the stored matches and `matches_skipped == 0`.

**Checkpoint**: US1 independently delivers value via `morning_refresh` (digest shows genuinely new jobs) even if US2/US3 are not done.

---

## Phase 4: User Story 2 — Live app reflects latest catalog without restart (P2)

**Goal**: The running server serves rankings against the newest snapshot, hot-reloading on change.

**Independent test**: With the server running, run `rebuild_job_pool` in another process → call match / "Refresh jobs" → the new pool is reflected without restarting the server.

- [x] T013 [US2] Modify `InferenceEngine.from_checkpoint` in `backend/ml_service/inference/engine.py` to load the job pool from the snapshot (override checkpoint jobs) when present and `model_sig` matches; else keep current frozen-checkpoint behaviour (backward compatible).
- [x] T014 [US2] Add snapshot mtime reload to `_get_engine()` in `backend/apps/matching/services/matching_service.py`: stat `checkpoints/job_pool/meta.json`; if newer than the loaded snapshot, reload the 3 pool structures into the existing engine under the engine lock (no full re-init).
- [x] T015 [US2] Verify realtime: start the server, `rebuild_job_pool` from a second shell, hit the match path (or employee "Refresh jobs"), assert the new pool size / a new job is served without restart.

---

## Phase 5: User Story 3 — Every ranked job maps to a real catalog job (P3)

**Goal**: Zero skipped/unresolvable results; one `Job.id` space end-to-end.

**Independent test**: Re-match sample employees → every returned candidate resolves to a real `Job` and `matches_skipped == 0`.

- [x] T016 [US3] Remove the now-dead `source_url` resolution fallback in `_persist_matches` (`backend/apps/employees/tasks.py`) and drop `source_url` from `_jobs_to_dicts`/adapter output if unused after T008/T009.
- [x] T017 [US3] Confirm SC-002 across a sample (`rematch_employees`): assert `matches_skipped == 0`; remove the "engine job_id ≠ Job.id / skipped" gotcha from `CLAUDE.md`.

---

## Phase 6: Polish & Cross-Cutting

- [x] T018 [P] Django test: `build_jobdata_from_db` mapping (skills+importances aligned, text=title+description, role_category, salary) in `backend/apps/matching/tests.py`.
- [x] T019 [P] Test: `job_pool_snapshot` save→load roundtrip + length invariant + `model_sig` mismatch → `None` + atomic temp cleanup, in `backend/ml_service/inference/` test module.
- [x] T020 [P] Test: `_persist_matches` resolves by `Job.id` + preserves applied/accepted status (mock engine), in `backend/apps/employees/tests.py`.
- [x] T021 Observability: surface `num_jobs`, `skill_skipped_edges`, `encode_seconds` in the `rebuild_job_pool` summary + a log line in `morning_refresh`.
- [x] T022 [P] Docs: update `CLAUDE.md` gotchas (engine pool = live catalog via snapshot; realtime reload) and cross-check `quickstart.md` commands.
- [x] T023 Performance check (SC-005): time a full rebuild (~6.5k jobs); assert it fits the maintenance window; record the number in `quickstart.md`.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T007)** → user stories.
- **US1 (T008–T012)**: needs T003/T004/T006/T007 (+ T002). T008/T009 unblock persistence; T010 wires the daily run; T011 is the prod gate.
- **US2 (T013–T015)**: needs T005 (snapshot) + T004. Independent of US1 (US1 works in-process without load/reload).
- **US3 (T016–T017)**: needs T008/T009.
- **Polish (T018–T023)**: after the stories they cover.

### Parallel opportunities
- T002 and T005 in parallel (different files).
- T018, T019, T020, T022 in parallel (separate test/doc files).

### MVP
**US1 only** (T001–T012) delivers the core outcome: newly-crawled jobs are matched the same day and surface in the digest. US2 (realtime live server) and US3 (id cleanup) are incremental enhancements.

### Suggested implementation order
1. T001 → T002–T007 (foundational) → **checkpoint: dry-run rebuild works**
2. T008–T012 (US1) → **run T011 sanity-check gate** → MVP shippable
3. T013–T015 (US2 realtime)
4. T016–T017 (US3 cleanup)
5. T018–T023 (polish)
