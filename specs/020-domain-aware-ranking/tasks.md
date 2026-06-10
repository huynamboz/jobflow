---
description: "Task list — Domain-Aware Match Scoring & Role-Aware Weight Tuning"
---

# Tasks: Domain-Aware Match Scoring & Role-Aware Weight Tuning

**Input**: Design documents from `specs/020-domain-aware-ranking/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: A few targeted unit tests (role-aware metric + 4-weight loading). Not full TDD.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable · **[Story]**: US1 (on-domain outcome) / US2 (role-aware tuning) / US3 (eval harness).
- Backend root = `backend/`. Continues feature 019.

---

## Phase 1: Setup

- [ ] T001 Capture the "before" qualitative state: confirm the feature-019 weights (δ=0) reproduce the cross-domain bug (a backend/devops/data CV surfaces VFX/animation/non-tech jobs at top); note it as the baseline for the on-domain comparison (the `eval_matching` from US3 will quantify it).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The four-term score mechanism + the per-pair domain component. All stories depend on these.

- [ ] T002 Add a `delta` param to `InferenceEngine.__init__` (default 0.0) in `backend/ml_service/inference/engine.py`; make `from_checkpoint` read `delta` from `metadata.json hybrid_weights` (defaults 0.0 if absent → feature-019 checkpoints unchanged).
- [ ] T003 Add the `δ·domain` term at BOTH blend sites in `backend/ml_service/inference/engine.py` (`_score_pair_fast` ~line 738 and `_gnn_score_fast` ~line 920): `score = α·gnn + β·skill + γ·seniority + δ·domain`, where `domain` = role match `infer_role(cv) vs job.role_category` (1.0/0.5/0.0, same as `_dimension_scores`); SOFT (no candidate removed).
- [ ] T004 Extend `InferenceEngine.labeled_pair_components()` in `backend/ml_service/inference/engine.py` to also return, per pair, `domain` (role match) and `(cv_role, job_role)` — for the 4-term score + the role-aware metric.

**Checkpoint**: engine loads a 4-weight config and applies δ·domain; components include domain + roles.

---

## Phase 3: User Story 2 — Role-aware weight tuning (P2)

**Goal**: Select the 4 weights on a role-aware ranking metric, with a dual-metric ablation.

**Independent test**: `tune_hybrid_weights` reports label-AUC AND role-aware NDCG/P@10 per combo; the chosen weights maximize role-NDCG and keep a non-trivial GNN weight.

- [ ] T005 [US2] Add role-aware ranking metric helpers (precision@k + NDCG@k grouped by CV, relevant = `cv_role == job_role`) to `backend/apps/matching/management/commands/tune_hybrid_weights.py` (or a shared util).
- [ ] T006 [US2] Extend `tune_hybrid_weights.py`: sweep the 4-weight simplex `α+β+γ+δ=1` on the grid; per combo compute label-AUC + role-NDCG@10 + role-P@10; add `--objective {role_ndcg|role_p|label_auc}` (default role_ndcg) + `--k`; write a DUAL ablation table to `specs/020-domain-aware-ranking/ablation.md` flagging chosen / label-AUC-max / legacy rows; `--write` persists the winner's 4 weights + metrics to `metadata.json`.
- [ ] T007 [US2] Run `tune_hybrid_weights` (dry → `--write`) → `specs/020-domain-aware-ranking/ablation.md`; assert the role-NDCG winner keeps α (GNN) meaningfully above the label-AUC-only ~0.20 (SC-003) and the two objectives favor different weights (SC-004).

---

## Phase 4: User Story 3 — Repeatable matching-quality evaluation (P3)

**Goal**: A reusable harness reporting per-CV top-K + an on-domain rate.

**Independent test**: `eval_matching` prints per-CV top-K + on-domain@k + a summary; re-running reproduces it.

- [ ] T008 [US3] Create `backend/apps/matching/management/commands/eval_matching.py`: a FIXED ~20 diverse IT CV set (frontend/backend/devops/data/ml/mobile/qa/java/dotnet/go/…, realistic catalog skills); run `match_cv_data(top_k=--k)` per CV against the live engine; print per-CV role + top-K (title, score, dim_scores) + `top1_on_domain` (domain_fit≥0.5); print SUMMARY `top1_on_domain` rate + mean `on_domain@k`. Reproducible.
- [ ] T009 [US3] Run `eval_matching` BEFORE (current weights, δ=0) to record the baseline on-domain rate, then AFTER (tuned 4 weights, server/engine reloaded) → record the improved rate for the thesis comparison.

---

## Phase 5: User Story 1 — On-domain matches at the top (P1) 🎯 outcome

**Goal**: IT CVs' top results are on-domain; cross-domain noise gone.

**Independent test**: After the tuned δ, `eval_matching` shows IT CVs with on-domain #1 matches and no VFX/animation/non-tech jobs ranked top.

- [ ] T010 [US1] Verify the outcome from the AFTER eval (T009): `top1_on_domain` ≥ 90% (SC-001); 0 IT CVs with an animation/VFX/non-tech #1 (SC-002); a fullstack CV still matches frontend/backend roles — domain stayed soft (SC-006). Document the before/after numbers.
- [ ] T011 [US1] Re-match employees (`rematch_employees` / `morning_refresh`) + restart the server so stored matches + the live app adopt the 4-term score; spot-check emp 20's top matches are on-domain.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T012 [P] Django test: role-aware metric helper (precision@k/NDCG@k by role) + 4-weight loading with `delta` fallback to 0.0, in `backend/apps/matching/tests.py`.
- [ ] T013 Docs: update `CLAUDE.md` (4-term score `α·GNN+β·skill+γ·seniority+δ·domain`; weights tuned on role-aware NDCG; dual ablation) + cross-link `specs/020/ablation.md` for the thesis; refresh `quickstart.md` numbers.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T004)** → **US2 (T005–T007)** → **US3 (T008–T009)** → **US1 verify (T010–T011)**.
- US3 "before" (T009 baseline) only needs Foundational (δ=0); US3 "after" needs US2's `--write`.
- **Polish (T012–T013)**: after.

### Parallel opportunities
- T012, T013 in parallel.
- T008 (eval harness) can be written in parallel with US2 (different file); it's only RUN after weights exist.

### MVP
The full chain is the deliverable (the visible US1 outcome requires the score term + tuned weights + the eval to prove it). Minimum to ship value: **T002–T009** (domain in score, role-aware tuning, eval showing on-domain ↑).

### Suggested order
1. T001 → T002–T004 (foundational) → engine applies δ·domain
2. T005–T007 (US2) → dual ablation + tuned 4 weights
3. T008–T009 (US3) → eval before/after
4. T010–T011 (US1 verify + adopt) → T012–T013 (polish)
