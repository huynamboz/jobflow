# Implementation Plan: Defense-Ready Match-Weight Calibration & Transparent Dimension Scores

**Branch**: `019-match-weight-calibration` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-match-weight-calibration/spec.md`

## Summary

Make every number in the matcher justifiable to a thesis committee, in three moves:

- **A. Tune** the hybrid weights `(α, β, γ)` that blend `score = α·GNN + β·skill + γ·seniority` — by grid-search on a held-out labeled validation set (the `match`/`no_match` graph edges), maximizing AUC, with an **ablation table** as the thesis artifact. Replaces the hand-set `0.55/0.30/0.15`.
- **B. Unify** the weight config: the engine loads the tuned weights from a single source (checkpoint `metadata.json`), removing the engine-default vs `settings.py` (`0.6/0.3/0.1`, currently ignored) contradiction.
- **C. Replace** the four per-dimension scores (currently learned reranker aux heads of unknown label provenance) with **transparent formulas** computed in the engine: skill fit = importance-weighted matched/required; experience fit = from experience gap; seniority fit = from seniority distance; domain fit = role match. Numeric `[0,1]`, already wired to the UI.

The learned GNN + reranker (main head, which sets ranking ORDER) are untouched. This feature only changes how their outputs are *combined* (tuned weights) and how dimensions are *displayed* (transparent diagnostics).

## Technical Context

**Language/Version**: Python 3.11 (backend `.venv`)

**Primary Dependencies**: PyTorch + PyTorch-Geometric (HeteroGraphSAGE), scikit-learn (`roc_auc_score`) or a small AUC implementation, Django 5.2 / DRF

**Storage**: GNN checkpoint `checkpoints/latest/` (`metadata.json` becomes the weight source of truth); labels live in `graph.pt` as `("cv","match","job")` / `("cv","no_match","job")` edges (no separate pairs file)

**Testing**: Django `manage.py test apps.matching`; the tune command is an offline run producing the ablation table; dimension formulas unit-tested directly

**Target Platform**: offline tuning (one-shot management command) + the live inference engine (`apps/matching/services/matching_service.py::_get_engine`)

**Project Type**: ML inference library (`backend/ml_service/`) + Django backend

**Performance Goals**: tuning is a one-shot offline job — extract labeled pairs once, compute (gnn, skill, seniority) per pair once, then sweep the weight grid in memory (cheap). Live matching latency unchanged (same blend formula, different constants; dimensions are O(1) arithmetic).

**Constraints**: No GNN/reranker retraining. Selected weights must satisfy `α+β+γ=1`. Dimension scores must stay numeric `[0,1]` to match the existing UI ScoreBar (feature-018 follow-up). Determinism: fixed validation split + tie-break.

**Scale/Scope**: ~labeled-pair count from the graph (thousands of match + no_match edges); 0.05 grid over the 2-simplex ≈ a few hundred weight combos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unfilled template — no ratified principles → **PASS** (trivially). Engineering guardrails adopted: no retraining; behaviour-preserving ranking ORDER (reranker untouched); evidence-backed + single-source weights; transparent, hand-reproducible diagnostics; deterministic/reproducible artifacts.

## Project Structure

### Documentation (this feature)

```text
specs/019-match-weight-calibration/
├── plan.md
├── research.md          # label source, metric choice, dimension formulas, config-source decision
├── data-model.md        # labeled-pair extraction, weight record, dimension formula definitions
├── quickstart.md        # run tuning → read ablation → adopt weights → verify dims
├── contracts/
│   └── cli.md           # `tune_hybrid_weights` command contract + weight-config schema
├── ablation.md          # GENERATED: the weight-combo → AUC table (thesis artifact)
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── ml_service/
│   ├── inference/
│   │   └── engine.py          # (B) from_checkpoint reads α/β/γ from metadata.json (single source);
│   │                          #     (C) build JobMatchResult.dim_scores from transparent formulas
│   │                          #     (replace dim_levels_map aux-head output ~engine.py:381)
│   ├── reranker/
│   │   └── ranker.py          # aux-head dim output no longer used for display (main head unchanged)
│   └── config/
│       └── settings.py        # (B) remove/realign stale hybrid_alpha/beta/gamma
└── apps/
    └── matching/
        ├── services/
        │   └── matching_service.py   # dimension formulas may live here or in engine; no weight dup
        └── management/commands/
            └── tune_hybrid_weights.py  # (A) NEW: grid-search → ablation table → write metadata.json
```

**Structure Decision**: Backend/ML only — **no frontend change** (the UI already renders numeric `[0,1]` dimension bars from feature 018's follow-up). New code = one offline tuning command + small edits to engine weight-loading + the dimension-score construction, plus a config cleanup.

## Complexity Tracking

No constitution violations. The only subtlety is keeping the **dimension formulas consistent with the FeatureExtractor's existing feature definitions** (so "skill fit" means the same thing the reranker already computed) — addressed by deriving the formulas directly from the documented features (weighted overlap, experience_gap, seniority distance, role_category match) rather than inventing new ones.
