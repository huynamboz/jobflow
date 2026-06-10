---
description: "Task list — Defense-Ready Match-Weight Calibration"
---

# Tasks: Defense-Ready Match-Weight Calibration & Transparent Dimension Scores

**Input**: Design documents from `specs/019-match-weight-calibration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: A few targeted unit tests (dimension formulas + weight loading). Not full TDD.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: US1 (tune) / US2 (unify config) / US3 (transparent dims). Setup/Foundational/Polish unlabeled.
- Backend root = `backend/`.

---

## Phase 1: Setup

**Purpose**: Confirm the labeled data needed for tuning exists.

- [x] T001 Verify label availability: a script in `backend/` that loads the checkpoint graph and counts `("cv","match","job")` + `("cv","no_match","job")` edges; assert BOTH classes are present (AUC precondition, research R7); record the counts in `specs/019-match-weight-calibration/ablation.md` header.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Expose the per-pair score components the tuner consumes.

- [x] T002 Add `InferenceEngine.labeled_pair_components()` to `backend/ml_service/inference/engine.py`: extract labeled pairs from the graph's match/no_match edges and return `[(cv_idx, job_idx, label, gnn, skill, seniority)]`, computing `gnn` (in-graph decode, same as `_gnn_score_fast`), `skill` (`_semantic_skill_overlap`), `seniority` (`max(0,1-|Δsen|·0.4)`) ONCE per pair. Used by the tuner; read-only (no state change).

**Checkpoint**: the method returns a non-empty list with both labels.

---

## Phase 3: User Story 1 — Weights chosen by evidence (P1) 🎯 MVP

**Goal**: Select (α,β,γ) by grid-search on a held-out validation set, with an ablation table.

**Independent test**: `tune_hybrid_weights` prints/writes an ablation table; the chosen weights are the AUC-max entry and AUC ≥ the legacy `0.55/0.30/0.15` row.

- [x] T003 [US1] Create `backend/apps/matching/management/commands/tune_hybrid_weights.py`: call T002, seeded `--val-frac` split (`--seed` default 42), sweep `α+β+γ=1` on `--grid` (0.05) lattice, compute AUC per combo on the validation split, print + write the ablation table (`--out`, default `specs/019-match-weight-calibration/ablation.md`), mark winner + legacy row; `--write` persists the winner to checkpoint `metadata.json` (`hybrid_weights` + `hybrid_weights_meta`). Non-zero exit if a single class / no labeled edges.
- [x] T004 [US1] Metrics in the command: AUC via `sklearn.metrics.roc_auc_score` (fallback to a small rank-based AUC if sklearn absent), plus NDCG@10 + precision@10 grouped by CV as secondary ablation columns.
- [x] T005 [US1] Run `tune_hybrid_weights` (dry, then `--write`) → produce `specs/019-match-weight-calibration/ablation.md`; assert chosen AUC ≥ legacy `(0.55,0.30,0.15)` AUC (SC-004) and that re-running with the same seed reproduces the same winner (SC-005).

**Checkpoint**: ablation table exists; tuned weights written to metadata.json.

---

## Phase 4: User Story 2 — One consistent weight source (P2)

**Goal**: The engine loads the tuned weights from a single source; no contradictory definition remains.

**Independent test**: `from_checkpoint` yields `engine.alpha/beta/gamma` equal to `metadata.json hybrid_weights`; the codebase has exactly one weight definition.

- [x] T006 [US2] In `backend/ml_service/inference/engine.py` `from_checkpoint`, read `meta["hybrid_weights"]` and pass `alpha/beta/gamma` to `__init__`; if absent, keep documented defaults `(0.55,0.30,0.15)` and log a warning. (Engine `__init__` already accepts these params.)
- [x] T007 [US2] Remove the stale `hybrid_alpha/hybrid_beta/hybrid_gamma` from `backend/ml_service/config/settings.py` (or repoint to a comment referencing metadata.json) so no second, contradictory definition exists; grep-confirm nothing else reads them.
- [x] T008 [US2] Verify single-source (SC-002): after load, `engine` uses the metadata weights; `grep -rn "hybrid_alpha\|0.55, *0.30\|0.30, *0.15"` shows one authoritative definition path.

---

## Phase 5: User Story 3 — Explainable dimension scores (P3)

**Goal**: The four per-dimension scores come from transparent formulas, not the learned aux heads.

**Independent test**: For a sample match, applying the documented formulas by hand to its skills/experience/seniority/role reproduces the four displayed numbers.

- [x] T009 [US3] Add a transparent `dimension_scores(cv, job, matched, missing)` helper (in `backend/ml_service/inference/engine.py` or a small module) returning `{skill_fit, experience_fit, seniority_fit, domain_fit}` ∈ [0,1] per research R6: skill = `Σimp(matched)/Σimp(required)` (1.0 if no required); experience = from `cv.experience_years` vs `job.experience_min` (neutral 1.0 if unknown); seniority = `max(0,1-|Δ|·0.3)`; domain = role match `1/0.5/0`.
- [x] T010 [US3] Wire T009 into the engine where `JobMatchResult.dim_scores` is built (~engine.py:381), REPLACING the reranker `dim_levels_map` aux output; keep numeric [0,1]; the reranker MAIN head still sets ranking order (unchanged).
- [x] T011 [US3] Verify hand-reproducibility (SC-003): re-match a sample employee → assert each `dim_scores` value equals the formula applied to the match's displayed data (matched/required, seniority_gap, role).

---

## Phase 6: Polish & Cross-Cutting

- [x] T012 [P] Django test: dimension formulas + edge cases (no-skill job → skill_fit handled; unknown experience_min → neutral; role unknown → 0.5; seniority distance) in `backend/apps/matching/tests.py`.
- [x] T013 [P] Test: `from_checkpoint` reads `hybrid_weights` from metadata + falls back to defaults when absent (mock metadata), in `backend/ml_service/inference/` or `apps/matching/tests.py`.
- [x] T014 Docs: update `CLAUDE.md` notes (hybrid weights tuned + single-source in `metadata.json`; per-dimension scores = transparent formulas) and cross-link the ablation table for the thesis report.
- [x] T015 [P] Adopt across the app: re-match employees (`rematch_employees` / `morning_refresh`) so stored matches pick up the new dim formulas + tuned weights; note in quickstart that a re-match is required for existing rows.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** → **US1 (T003–T005)**.
- **US2 (T006–T008)**: the read-mechanism is independent; its VALUE comes from US1's `--write` (T008 verifies after T005 wrote the weights).
- **US3 (T009–T011)**: fully independent of US1/US2.
- **Polish (T012–T015)**: after the stories they cover.

### Parallel opportunities
- T012, T013, T015 in parallel (separate files).
- US3 (T009–T011) can proceed in parallel with US1/US2 (different code paths).

### MVP
**US1 (T001–T005)** — the ablation table + tuned weights — is the core defense deliverable. US2 makes them apply with one config source; US3 makes the dimension diagnostics transparent.

### Suggested order
1. T001 → T002 → T003–T005 (US1) → **ablation table ready**
2. T006–T008 (US2) — weights actually applied from one source
3. T009–T011 (US3) — transparent dims
4. T012–T015 (polish) → re-match to adopt
