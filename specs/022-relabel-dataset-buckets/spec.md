# Feature Specification: Targeted Relabeling Dataset (Đợt 1)

**Feature Branch**: `022-relabel-dataset-buckets`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Generate decision-boundary pair buckets and label them with Claude agents, producing the clean training set for the Đợt-2 retrain (master plan 1.1-1.6)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The dataset finally teaches the domain boundary (Priority: P1)

The labeled training set gains thousands of targeted pairs covering exactly the patterns the current ground truth misses: strong-skill-but-wrong-field pairs (the bug pattern), related-skill matches (the model's intended advantage), seniority mismatches, and missing-must-have cases — each tagged with its bucket so coverage is auditable.

**Why this priority**: This is the root-cause fix. The current 8.6k clean labels contain only ~2% of the critical cross-domain slice and structurally zero related-skill positives. Without this supervision, the Đợt-2 retrain cannot teach the model anything new.

**Independent test**: After generation, the pair queue contains the planned bucket quotas (deduplicated against existing pairs, stratified across roles and splits), and each pair carries its bucket tag.

**Acceptance Scenarios**:

1. **Given** the existing pair queue, **When** generation runs, **Then** ~3.5-4k new pending pairs exist with bucket tags matching the planned quotas (±20%) and no duplicates against existing pairs.
2. **Given** the new pairs, **When** grouped by split, **Then** every bucket is represented in train, val, and test.

---

### User Story 2 - Labels produced in-session with verified quality (Priority: P1)

The labeling is performed by Claude agents (no external LLM provider cost) following the patched rubric, with quality demonstrated rather than assumed: a pilot batch is audited per-bucket against expected label distributions BEFORE scaling, and a double-labeled sample reports inter-rater agreement.

**Why this priority**: The original failure was a labeling process whose flaws went unnoticed for thousands of labels. The pilot gate + agreement measurement make labeling quality observable and stop a bad run before it pollutes the dataset.

**Independent test**: Pilot of 150-200 pairs produces a per-bucket distribution report compared against expectations; a 200-pair double-labeled sample yields an agreement number; all imported labels are traceable to the agent batch.

**Acceptance Scenarios**:

1. **Given** the pilot batch, **When** audited, **Then** each bucket's label distribution is compared to its expectation (e.g. cross-domain ≥95% not-suitable) and the gate decision (scale / stop-and-fix) is recorded.
2. **Given** the double-labeled sample, **When** compared, **Then** an inter-rater agreement report exists (overall + per-dimension), and pairs disagreeing by 2 levels are re-labeled.
3. **Given** any imported label, **When** inspected, **Then** it is marked as agent-labeled and linked to its labeling batch.

---

### User Story 3 - The poisoned old slices are corrected (Priority: P2)

The previously-identified bad labels — the ~284 contradictory pairs and the ~232 strong-skill/wrong-domain pairs (43% mislabeled under the old rubric) — are re-labeled under the patched rubric, and the newer judgments automatically supersede the old ones in any future export.

**Why this priority**: Even with new buckets added, these old wrong labels would keep injecting contradictory supervision into training. The latest-wins dedup (already shipped) makes re-labeling sufficient — no deletion needed.

**Independent test**: Re-export after re-labeling → the affected pairs carry the new judgments; the strong-skill/wrong-domain slice is now ~0% positive.

**Acceptance Scenarios**:

1. **Given** the old conflicting/mislabeled pairs, **When** re-labeled and re-exported, **Then** the export contains exactly one (new) judgment per pair and the skill-high/domain-zero slice has ≈0% suitable labels.

---

### User Story 4 - A clean, verified dataset ready for retraining (Priority: P2)

A new dataset export merges everything (old deduplicated labels + new bucket labels + corrected slices), passes the conflict guard, keeps a healthy class balance, and documents its composition — the direct input to the Đợt-2 retrain.

**Why this priority**: The deliverable of the whole effort. Without a verified export, Đợt 2 cannot start.

**Independent test**: Export runs; building the training graph raises no conflicts; metadata shows positive rate in the target band and per-bucket counts in each split.

**Acceptance Scenarios**:

1. **Given** all labeling complete, **When** the dataset is exported, **Then** the graph builds with zero conflicting pairs and metadata records bucket composition per split.
2. **Given** the export metadata, **When** reviewed, **Then** the positive rate is within ~30-40% (or the deviation is documented with a mitigation).

---

### Edge Cases

- **A bucket can't fill its quota** (not enough qualifying CV×job combinations): take what exists, log the shortfall — never relax the bucket condition silently.
- **Agent returns malformed/missing output for some pairs**: those pairs stay pending; import is idempotent per pair (safe to re-run/re-label).
- **Pilot audit fails for one bucket only**: fix that bucket's selection or rubric guidance, re-pilot that bucket; others may proceed.
- **Double-label disagreement is high (>2-level disagreements common)**: stop scaling, tighten rubric guidance, re-pilot.
- **Class balance drifts** (new buckets are negative-heavy): documented; mitigation = subsample negatives at export or top-up positive buckets.
- **A pair already labeled in an earlier batch reappears**: generation dedups against ALL existing pairs (any status), not just pending.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Pair generation MUST produce the six planned buckets (cross-domain hard-negatives, related-skill positives, seniority hard-negatives, missing-must-have, boundary-medium, random/top-up) with the planned quotas (±20%), deduplicated against all existing pairs.
- **FR-002**: Every generated pair MUST record its bucket, and splits (70/15/15) MUST be assigned stratified by bucket.
- **FR-003**: Generation MUST cap pairs per CV and cover all role categories present in the data.
- **FR-004**: There MUST be an export mechanism producing agent-consumable work chunks (compact pair context) and an import mechanism that validates agent outputs (known pending pair, all five scores in range) and records them as agent-labeled within a tracked batch; import MUST be idempotent per pair.
- **FR-005**: Labeling MUST follow the patched rubric; the labeling instructions given to agents MUST embed the rubric including its three validation cases as worked examples.
- **FR-006**: A pilot of 150-200 pairs spanning all buckets MUST be labeled and audited per-bucket against expected distributions BEFORE full-scale labeling; the gate outcome MUST be recorded.
- **FR-007**: A ~200-pair random sample MUST be independently double-labeled; inter-rater agreement (overall + per-dimension) MUST be reported; 2-level disagreements MUST be re-labeled.
- **FR-008**: The ~284 previously-conflicting pairs and the ~232 strong-skill/wrong-domain pairs MUST be re-labeled under the patched rubric.
- **FR-009**: The final export MUST pass the graph conflict guard (zero conflicting pairs) and document per-bucket counts per split and the positive rate.
- **FR-010**: All new labels MUST be traceable: marked as agent-labeled, linked to a batch, distinguishable from the legacy LLM labels.

### Key Entities *(include if feature involves data)*

- **Bucket**: a named selection condition targeting one decision-boundary lesson, with a quota and an expected label distribution (the audit contract).
- **Work chunk**: a batch of ~20-25 pairs with compact context, sized for one labeling agent.
- **Agent label**: one judgment (overall + 4 dimensions) produced by a Claude agent, traceable to its batch, superseding older judgments via latest-wins.
- **Pilot report / agreement report**: the recorded quality evidence (per-bucket distributions vs expectations; inter-rater agreement).
- **Dataset export**: the merged, deduplicated, conflict-free labeled dataset with composition metadata — input to Đợt 2.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ~3.5-4k new pairs exist with bucket tags; per-bucket counts within ±20% of quota (or shortfall logged); zero duplicates vs existing pairs.
- **SC-002**: Pilot report exists comparing every bucket's label distribution to its expectation, with an explicit gate decision; cross-domain bucket shows ≥95% not-suitable in the pilot (or the run was stopped and fixed).
- **SC-003**: Inter-rater agreement is measured on ≥200 double-labeled pairs and reported (target: ≥80% exact overall agreement; all 2-level disagreements resolved).
- **SC-004**: 100% of the identified bad old slices (~516 pairs) re-labeled under the new rubric; the skill-high/domain-zero slice ends ≈0% positive.
- **SC-005**: Final export: graph builds with 0 conflicts; positive rate 30-40% (or documented deviation); every bucket present in train/val/test.
- **SC-006**: Every new label is traceable to an agent batch and distinguishable from legacy labels.

## Assumptions

- The labeler is Claude (this assistant) orchestrating parallel in-session agents — no external LLM provider/budget needed; session token cost is accepted and runs are batched/resumable.
- The patched rubric (feature 021) is final for this effort; rubric changes mid-labeling would invalidate the pilot gate.
- The related-skill bucket relies on the existing skill-relations data (co-occurrence + semantic edges + clusters); its pilot audit doubles as a quality check of those relations.
- "Expected distributions" are directional audit contracts, not hard guarantees — material deviation triggers investigation, not automatic failure.
- The 70/15/15 split convention and the latest-wins dedup (021) are kept as-is.

## Dependencies

- Feature 021 (Đợt 0): patched rubric + rubric test cases, dedup export, graph conflict guard — all prerequisites for safe labeling/export.
- Existing labeling infrastructure (pair queue, batches, label records) and skill-relations data.
- Master plan Đợt 1 (docs/codebase-knowledge/10-master-plan.md items 1.1-1.6).
