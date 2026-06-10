# Implementation Plan: Domain-Aware Match Scoring & Role-Aware Weight Tuning

**Branch**: `020-domain-aware-ranking` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-domain-aware-ranking/spec.md`

## Summary

A 20-CV evaluation exposed domain-mismatched top results (a Python backend CV ranked against VFX jobs that merely list "python"; `skill_fit≈1.0`, `domain_fit=0.0`). Two compounding causes: the score omits the domain signal, and the feature-019 weights were tuned on label-AUC, which doesn't see domain mismatch. Fix both:

- **A. Four-term score**: `score = α·GNN + β·skill + γ·seniority + δ·domain` (`α+β+γ+δ=1`), with `domain` = the transparent `domain_fit` (role match) already computed in feature 019. Soft term — down-weights field mismatches, never a hard filter.
- **B. Role-aware tuner**: extend `tune_hybrid_weights` to sweep the 4-weight simplex and select on a **role-aware ranking metric** (precision@k / NDCG@k where relevant = same field), reporting a **dual ablation table** (label-AUC vs role-aware) — restoring a meaningful GNN weight.
- **C. Evaluation harness**: a repeatable `eval_matching` command running a fixed diverse CV set, reporting per-CV top-K + an on-domain rate — to verify the fix and as a thesis artifact.

No model retraining; the learned GNN + reranker are untouched. Weights stay single-source (metadata.json, feature 019), now four numbers.

## Technical Context

**Language/Version**: Python 3.11 (backend `.venv`)

**Primary Dependencies**: PyTorch + PyTorch-Geometric, scikit-learn (`roc_auc_score`, `ndcg_score`) or small in-house metrics, Django 5.2 / DRF

**Storage**: GNN checkpoint `metadata.json` `hybrid_weights` (now `{alpha, beta, gamma, delta}`); labels = `match`/`no_match` graph edges; role labels = `JobData.role_category` + `infer_role(cv)`

**Testing**: Django `manage.py test apps.matching`; `eval_matching` produces the qualitative quality report; ranking-metric helpers unit-tested

**Target Platform**: offline tuning + evaluation commands + the live inference engine

**Project Type**: ML inference library (`backend/ml_service/`) + Django backend

**Performance Goals**: tuning extracts per-pair components once (incl. the new `domain` term) then sweeps the 4-simplex (0.05 grid ≈ 1771 combos) in memory; per-query latency unchanged (one extra multiply + an `infer_role` call already used).

**Constraints**: `α+β+γ+δ=1`, each ≥0; domain is SOFT (no removal); `infer_role` must be identical in the scoring path and the role-aware metric; single-source weight config preserved.

**Scale/Scope**: ~13.5k labeled pairs; 1771 weight combos; fixed 20-CV eval set.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is an unfilled template → **PASS**. Guardrails: no retraining; soft domain signal (no hard filter); tune on a goal-aligned metric; report the independent label-AUC + qualitative eval for honesty (mitigates circularity); single-source config preserved.

## Project Structure

### Documentation (this feature)

```text
specs/020-domain-aware-ranking/
├── plan.md
├── research.md          # domain term, role-aware metric, circularity mitigation, eval CV set
├── data-model.md        # 4-weight record, per-pair domain component, eval entities
├── quickstart.md        # tune (dual ablation) → adopt → eval before/after → verify
├── contracts/
│   └── cli.md           # tune_hybrid_weights (4-weight, dual metric) + eval_matching contracts
├── ablation.md          # GENERATED: dual-metric table (thesis artifact)
└── tasks.md             # /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
backend/
├── ml_service/inference/
│   └── engine.py        # __init__ +delta; from_checkpoint reads delta; _score_pair_fast (738) +
│                        #   _gnn_score_fast (920) add δ·domain; labeled_pair_components +domain +roles;
│                        #   _dimension_scores (role match) already exists — reused for the domain term
└── apps/matching/management/commands/
    ├── tune_hybrid_weights.py   # 4-weight simplex + role-aware metric + dual ablation
    └── eval_matching.py         # NEW: fixed 20-CV harness → per-CV top-K + on-domain rate
```

**Structure Decision**: Backend/ML only — **no frontend change** (the UI already shows the four dimension bars; domain just additionally enters the score). New code = the δ term at the two blend sites, the tuner extension, and the eval command. No DB migration (weights live in metadata.json).

## Complexity Tracking

The one genuine subtlety is **circularity**: `domain` is both a score term and part of the tuning/eval metric, so a naive read could call the win self-fulfilling. Mitigations (designed in, not bolted on): (1) also report the **independent label-AUC** in the dual table; (2) judge success primarily by the **qualitative 20-CV eval** (does a backend CV stop matching VFX jobs?), which is about face-validity, not the optimized number; (3) `infer_role` is the SAME function in scoring and metric, so the domain signal is internally consistent. These are documented in research.md (FR-009).
