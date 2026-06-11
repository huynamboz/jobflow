# Implementation Plan: Calibrated Probability Display

**Branch**: `025-calibrated-probability-display` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-calibrated-probability-display/spec.md`

## Summary

Replace the per-basket min-max display remap (A3 patch) with an absolute
calibrated probability: `display = PlattCalibrator.transform(rank_score)` where
`rank_score = reranker × penalty_gates` is the existing ordering signal.
Because the sigmoid is strictly monotonic, ordering and display can never
disagree — the remap block is deleted, scores become stable, comparable across
employees, and fully explained by the existing score-breakdown panel. The
dormant calibrator is repaired (sklearn fit instead of non-converging hand GD),
re-pointed at the right signal (rank_score instead of stage-1), and coupled to
the reranker version with an A14-style stamp+warn guard.

## Technical Context

**Language**: Python 3.11 (backend/.venv) + TypeScript (admin FE)
**Touched components** (all verified against source 2026-06-12):

| Component | File | Change |
|---|---|---|
| Calibrator fit | `ml_service/reranker/calibration.py` | GD → sklearn `LogisticRegression(lbfgs)`; same `a·s+b` sigmoid + `calibration.json` schema (+`trained_with` stamp, +fit-quality report) |
| Gate helper | `ml_service/inference/engine.py` | extract inline gate block from `match_cv` loop → `_penalty_product(cv, job) -> (penalty, flags)`; loop + fit-time both call it |
| Fit-time signal | `ml_service/inference/engine.py` + `train_reranker.py` | new `engine.rank_scores_for_pairs(cv_idx, job_idx)` (reranker×penalty on training-graph pairs, same feature context as training); train_reranker fits calibrator on it (replaces stage-1 fit) |
| Serving display | `engine._finalize_results` | delete min-max remap; `score = calibrator.transform_single(rank_score)`; eligible = `score >= ELIGIBLE_MIN_PROB` (absolute); no-calibrator → loud warn + raw rank_score |
| Stamp guard | `engine.__init__` | `_warn_if_calibration_stale()` mirroring `_warn_if_reranker_weights_stale` (compare `calibration.json.trained_with` vs sha256-16 of `reranker.pt`) |
| Breakdown | `engine.match_cv` | `score_breakdown += {"calibrated": <display prob>}` |
| FE | `admin/src/pages/admin/employees/detail.tsx`, `match.types.ts` | explainer note → absolute-probability semantics; breakdown box shows `rank_score → calibrated` step |
| Docs | docs/06, 07, CLAUDE.md | remove cross-employee caveat; add new semantics + selection-bias framing |

**Storage**: no migrations — `match_score` stays float (semantics change only);
`score_breakdown` is JSONField (new key free).

**Measured baseline** (input to threshold choice): 400 persisted matches,
rank_score min 0.250 · p10 0.386 · p50 0.787 · p90 0.940 · max 0.982; current
eligible = relative `≥ 0.65 × top` per basket.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (same as features
018–024) — no project-specific gates. Generic gates honored: tests-first for
the hot-loop refactor (parity test), no new dependencies (sklearn already in
venv), single source of truth preserved (one gate helper, one calibration
artifact), fail-loud over silent fallback (project convention from 024).
**PASS** (pre-design and post-design).

## Phase 0 — Research

→ [research.md](research.md). Resolved decisions:

1. **Fit method**: sklearn `LogisticRegression(solver="lbfgs", C=1e6)` on 1-D
   score (C large = no regularization, pure Platt). Keeps `{a,b}` schema.
2. **Stamp**: sha256 of `reranker.pt` bytes, first 16 hex — most direct
   coupling (calibrator is a function of the reranker's output distribution).
3. **Eligible threshold**: `ELIGIBLE_MIN_PROB = 0.50` — "more likely match than
   not"; validated against current eligible-rate on the 4 employees during
   rollout (adjust constant once, documented, if rate shifts drastically).
4. **Fit-time pair context**: training-graph engine (no live pool), reusing the
   val-pair compute path train_reranker already has; penalty via the SAME
   helper serving uses.
5. **Ties**: reranker saturation produces rank_score ties at the top → equal
   displayed probs; order among ties stays deterministic (stable sort over
   stage-1-ordered candidates). Order-invariance check compares engine output
   sequence, not DB re-sort.

## Phase 1 — Design

→ [data-model.md](data-model.md) (calibration artifact schema, breakdown key,
match_score semantics) · [contracts/calibration.md](contracts/calibration.md)
(artifact contract + guard behavior) · [quickstart.md](quickstart.md) (fit →
verify → rollout runbook).

### Order of implementation (informs tasks)

```
0. SNAPSHOT  pre-change ranked job_id sequence per employee (engine output,
             not DB) → specs/025-*/order_before.json           [rollout gate]
1. CALIB     fix PlattCalibrator.fit (sklearn) + reliability report + stamp
             field in save/load                                 [unit-testable alone]
2. HELPER    extract _penalty_product from match_cv loop (pure refactor,
             behavior-identical) + parity unit test
3. FIT PATH  engine.rank_scores_for_pairs + train_reranker fit on rank_score
             → run locally (CPU, ~2 min) → calibration.json v2 with stamp
4. SERVE     _finalize_results: remap → transform; ELIGIBLE_MIN_PROB;
             loud fallback; breakdown "calibrated"; stamp guard at boot
5. VERIFY    order-invariance vs step-0 snapshot · 4 eval suites 100% ·
             unit suite green
6. ROLLOUT   rematch all employees → restart server → curl API verify
             (match list of each employee: scores absolute, breakdown chain
             closes, eligible sane)
7. POLISH    FE note + types · docs 06/07/CLAUDE.md · commit
```

### Riskiest change & mitigation

`_penalty_product` extraction touches the hot serving loop. Mitigations:
parity unit test (helper vs hand-computed gate combos for all 5 gate cases),
plus the step-0/step-5 order-invariance gate which fails the rollout if ANY
employee's ranked sequence changed.

## Phase 2 — Tasks

Generated by `/speckit-tasks` → [tasks.md](tasks.md).
