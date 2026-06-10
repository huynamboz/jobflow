# Implementation Plan: Targeted Relabeling Dataset (Đợt 1)

**Branch**: `022-relabel-dataset-buckets` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/022-relabel-dataset-buckets/spec.md`

## Summary

Create the missing decision-boundary supervision and label it in-session with Claude agents, gated by quality checks (master plan 1.1-1.6):

1. **Buckets** — extend `generate_pairs.py` with 5 new selection buckets (~3.8k pairs, dedup vs existing queue, per-CV cap, role-stratified, split stratified by bucket).
2. **Commands** — `export_pending_pairs` (JSONL work chunks ~22 pairs/agent) + `import_labels` (validated, idempotent, batch-tracked, note='claude-labeled') + `audit_labels` (per-bucket distribution report).
3. **Pilot gate** — 180 pairs across buckets → per-bucket distribution audit vs expectations → recorded go/no-go (`pilot-report.md`).
4. **Scale + agreement** — Workflow with parallel agents over the remaining chunks; 200-pair double-label → inter-rater agreement (`agreement-report.md`); ≥2-level disagreements re-labeled.
5. **Re-label bad old slices** — the conflicting pairs + the skill2/domain0 slice via `--pair-ids` export (latest-wins makes new judgments authoritative).
6. **Export** — `data/processed/v4_relabel`, graph conflict-guard verification, composition metadata; master plan ticked.

No retraining here (Đợt 2). Rubric frozen (021).

## Technical Context

**Language/Version**: Python 3.11, Django 5.2 (backend/)

**Primary Dependencies**: existing labeling app (PairQueue/LabelingBatch/HumanLabel), ml_service skill-relations (PMI + semantic edges, SKILL_CLUSTERS) for expanded overlap; no new packages

**Storage**: PostgreSQL (new PairQueue rows + HumanLabel rows; one cosmetic migration for SelectionReason choices); JSONL work files under `/tmp/labeling-022/` (gitignored)

**Testing**: unit tests for bucket conditions, export/import validation + idempotency, audit math; pilot/agreement are RUN artifacts (reports in specs/022/)

**Target Platform**: offline management commands + in-session agent orchestration (me); server untouched

**Project Type**: Django backend tooling + data production

**Performance Goals**: generation is O(CV×job) pairwise loops over 365 CV × 6.2k labeling jobs with cheap set ops (same as today's generate_pairs — fine); labeling ~190 agent calls total (batched, resumable)

**Constraints**: rubric frozen; import idempotent per (pair, batch); never mutate old HumanLabel rows (latest-wins supersedes); pilot MUST pass before scale (hard gate); quotas ±20% with logged shortfalls

**Scale/Scope**: ~3.8k new pairs + ~516 re-labeled + 200 double-labels ≈ ~4.5k agent judgments ≈ ~190-210 chunks/agent calls

## Constitution Check

Constitution is an unfilled template → **PASS**. Guardrails: pilot gate before scale (cost + quality), idempotent import (resumable), traceability (batch + note), no destructive ops (old labels kept; latest-wins), quotas audited not silently relaxed.

## Project Structure

### Documentation (this feature)

```text
specs/022-relabel-dataset-buckets/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/cli.md          # generate/export/import/audit command contracts + JSONL schemas
├── agent-rubric.md           # the exact labeling prompt given to every agent (rubric + 3 worked examples)
├── pilot-report.md           # GENERATED at 1.3 — per-bucket distributions + gate decision
├── agreement-report.md       # GENERATED at 1.4 — inter-rater agreement
└── tasks.md                  # /speckit-tasks
```

### Source Code (repository root)

```text
backend/apps/labeling/
├── models.py                                  # SelectionReason +5 values, REASON_PRIORITY (cosmetic migration)
├── management/commands/generate_pairs.py      # bucket conditions + quotas + stratified split + dedup
├── management/commands/export_pending_pairs.py# NEW — JSONL chunks (--reasons --pilot --pair-ids --limit)
├── management/commands/import_labels.py       # NEW — validate + HumanLabel + batch + idempotent (--dry-run)
└── management/commands/audit_labels.py        # NEW — per-bucket label distribution (pilot gate + final)
backend/apps/labeling/tests.py (or apps/matching/tests.py)  # unit tests
```

**Structure Decision**: All inside the existing labeling app (the machinery it extends). Work files in /tmp (not committed); reports in specs/022 (committed evidence). SelectionReason gets 5 new TextChoices members — Django choices are app-level validation only, so the migration is a no-op AlterField (safe).

## Key Design Decisions (full rationale in research.md)

1. **Expanded overlap for related_skill bucket**: reuse the relates_to expansion approach (PMI co-occurrence + semantic ≥0.7 + SKILL_CLUSTERS) — expand the CV skill set once per CV, then `expanded_jaccard = |expanded ∩ job| / |job|`; bucket condition `direct < 0.15 AND expanded ≥ 0.5 AND same role AND |Δsen| ≤ 1`.
2. **Split stratified by bucket**: assign 70/15/15 within each bucket at generation (seeded), so test can measure each capability.
3. **Re-label without resetting status**: `export_pending_pairs --pair-ids file` bypasses the pending filter; new HumanLabel rows supersede via 021 latest-wins; PairQueue status untouched.
4. **Agent prompt** (`agent-rubric.md`): patched rubric verbatim + the 3 rubric test cases as worked examples + strict JSON-array output contract; each chunk ≤ ~25 pairs with truncated texts (≤1200 chars) to keep agent context tight.
5. **Agreement metric**: exact-match % on overall + per-dimension exact-match %; disagreement ≥2 levels → third independent judgment (latest-wins).

## Complexity Tracking

No violations. Main risk is bucket underfill (related_skill depends on relations quality) — handled by logged shortfall + pilot audit doubling as a relations-quality check.
