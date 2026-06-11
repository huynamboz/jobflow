# Tasks: Calibrated Probability Display

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/calibration.md, quickstart.md
**Tests**: requested explicitly in spec (SC-001..007 are hard gates) → test tasks included.
All backend paths relative to `backend/`.

## Phase 1: Setup (rollout gate input — BEFORE any code change)

- [x] T001 Write `specs/025-calibrated-probability-display/capture_order.py` — captures engine-output ranked job_id sequence per employee via `rematch_employee(emp)` (NOT DB re-sort); `before` mode writes `order_before.json`, `after` mode diffs and exits 1 on any mismatch (per research.md R5)
- [x] T002 Run `capture_order.py before` → commit `order_before.json` snapshot

## Phase 2: Foundational (blocking — shared by all stories)

- [x] T003 Fix `PlattCalibrator.fit` in `backend/ml_service/reranker/calibration.py`: sklearn `LogisticRegression(solver="lbfgs", C=1e6, max_iter=1000)` on 1-D scores; extract a/b; REFUSE to mark fitted when `a <= 0` (loud log); add reliability report helper (per-decile n / mean predicted / observed rate) logged after fit; `save/load` gain `trained_with` passthrough (per research.md R1, contracts gates)
- [x] T004 [P] Unit tests `PlattFitTests` in `backend/apps/matching/tests.py`: synthetic sigmoid recovery (fit on sigmoid(5s−3) samples → a≈5, b≈−3 tolerance), transform strictly monotonic, predicted span over [0.2, 0.98] ≥ 0.5, a≤0 case refuses fitted
- [x] T005 Extract gate block from `match_cv` loop into `InferenceEngine._penalty_product(cv, job) -> tuple[float, dict]` in `backend/ml_service/inference/engine.py` (pure refactor — identical constants/flags `_exp_weak/_sen_weak/_domain_gated`); loop consumes the helper
- [x] T006 [P] Unit tests `PenaltyParityTests` in `backend/apps/matching/tests.py`: helper returns expected (penalty, flags) for all 5 gate cases (domain mismatch ×0.40, exp under ×0.40, exp overqual ×0.85, seniority gap ×0.70, cv-overqual ×0.75) + no-gate case ×1.0

## Phase 3: User Story 1 — One comparable scale (P1) 🎯 MVP

**Goal**: display = calibrated probability of rank_score; absolute, stable, explained.
**Independent test**: same pair → same score regardless of basket; cross-employee scores on one scale.

- [x] T007 [US1] Add `engine.rank_scores_for_pairs(cv_idx_list, job_idx_list) -> list[float]` in `backend/ml_service/inference/engine.py`: reranker score on training-graph pairs (same `set_stage1_context` compute path train_reranker uses) × `_penalty_product` — per research.md R2
- [x] T008 [US1] `backend/train_reranker.py`: replace stage-1 calibration fit with rank_score fit via T007; add `--calibrate-only` flag (load existing reranker, fit calibrator only); stamp `trained_with = sha256(reranker.pt)[:16]`; log reliability table (contracts gates: span ≥ 0.5, deciles ±0.15, a > 0)
- [x] T009 [US1] `engine._finalize_results` in `backend/ml_service/inference/engine.py`: DELETE min-max remap; `score = round(self._calibrator.transform_single(rank_score), 4)` when fitted, else raw rank_score + one-time WARNING (FR-008); add `"calibrated"` key to each result's `score_breakdown` (note: `_finalize_results` becomes instance method or receives calibrator)
- [x] T010 [US1] Boot guard `_warn_if_calibration_stale()` in `backend/ml_service/inference/engine.py`: sha256(serving reranker.pt)[:16] vs `calibration.json.trained_with` → WARNING on mismatch/missing (mirror `_warn_if_reranker_weights_stale`)
- [x] T011 [P] [US1] Unit tests `CalibStampTests` + `FallbackLoudTests` in `backend/apps/matching/tests.py`: stamp mismatch → warning; unfitted/missing calibration → warning + raw rank_score display (no remap anywhere)
- [x] T012 [US1] Refit calibrator locally: `python train_reranker.py --data data/processed/v4_relabel --checkpoint checkpoints/latest --calibrate-only` → verify log gates pass, `calibration.json` has trained_with

## Phase 4: User Story 2 — Order preserved exactly (P1)

**Goal**: prove only numbers changed, never order.

- [x] T013 [US2] Run `capture_order.py after` — MUST exit 0 (identical sequences for every employee vs T002 snapshot)
- [x] T014 [US2] Run all 4 eval suites (`manage.py eval_matching`, `/tmp/eval_holdout.py`, `/tmp/eval_30cv.py`, `/tmp/eval_realcv.py`) — all MUST stay 100% top-1 on-domain
- [x] T015 [US2] Full unit suite `python manage.py test apps.matching apps.employees apps.jobs apps.labeling` green

## Phase 5: User Story 3 — Absolute eligible cutoff (P2)

- [x] T016 [US3] Replace relative eligible (`>= 0.65 × top`) with `ELIGIBLE_MIN_PROB = 0.50` named constant + rationale comment in `backend/ml_service/inference/engine.py` (part of T009 edit site; listed separately for verification)
- [x] T017 [US3] Measure eligible-rate over the 4 employees' matches before vs after; if swing > ±25pp adjust constant once and record final value in research.md R4

## Phase 6: Rollout & Verification (per quickstart.md)

- [x] T018 Rematch all employees (`python manage.py rematch_employees`) + restart server; boot log MUST show no stale-calibration warning
- [x] T019 **curl verify** (FR-009/SC-004): authenticated `GET /api/employees/matches/?employee=<id>&page_size=5` for ≥2 employees — assert `match_score == score_breakdown.calibrated`, rows sorted by `score_breakdown.rank_score` desc, eligible consistent with ≥0.50, and cross-employee scores monotone in rank_score (one scale)

## Phase 7: Polish

- [x] T020 [P] FE: `admin/src/types/match.types.ts` score_breakdown +`calibrated`; `admin/src/pages/admin/employees/detail.tsx` — breakdown box adds final line `rank_score → calibrated (displayed)`, note text rewritten: absolute calibrated probability, comparable across employees, w.r.t. labeled ground truth; `npx tsc --noEmit` clean
- [x] T021 [P] Docs: `docs/codebase-knowledge/06` (remap section → calibration), `07` (score semantics + selection-bias framing), `CLAUDE.md` (REMOVE "KHÔNG so sánh số tuyệt đối giữa 2 employee" caveat; add calibrated semantics + ELIGIBLE_MIN_PROB + stamp guard)
- [x] T022 Commit with full verification evidence in message

## Dependencies

```
T001→T002 ──────────────────┐
T003→T004                   │
T005→T006                   ├─→ T013/T014/T015 (gates) → T016/T017 → T018 → T019 → T020/T021 → T022
T003+T005+T007→T008→T012    │
T005+T009+T010→T011 ────────┘
```

US1 is the MVP; US2 is its verification gate; US3 rides the same edit site.
Parallel: T004∥T006∥T011 (tests, separate classes), T020∥T021 (FE vs docs).

## Implementation Strategy

Strict order Setup→Foundational→US1, because the order-invariance gate (US2)
is only meaningful against the T002 snapshot taken before any engine edit.
The riskiest edit (T005 hot-loop refactor) lands behind two independent nets:
parity tests (T006) and the sequence diff (T013).
