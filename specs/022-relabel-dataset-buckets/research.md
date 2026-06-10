# Phase 0 Research: Targeted Relabeling Dataset

## R1. SelectionReason extension — migration?

**Decision**: Add 5 TextChoices members (`CROSS_DOMAIN_HARD_NEG, RELATED_SKILL_POSITIVE, SENIORITY_HARD_NEG, MISSING_MUST_HAVE, BOUNDARY_MEDIUM`) + REASON_PRIORITY entries. Run `makemigrations` — Django emits a cosmetic AlterField (choices are app-level validation, no DB constraint). Values fit `max_length=30` (longest = `related_skill_positive` = 22).

**Rationale**: Keeping the enum authoritative (vs loose strings) preserves admin display + audit groupings.

## R2. Bucket conditions (final)

Let `J` = direct Jaccard(cv_skills, job_skills); roles compatible = same or in RELATED_ROLES (existing map).

| Bucket | Condition | Quota (~3.8k) | Expected labels |
|---|---|---|---|
| cross_domain_hard_neg | J ≥ 0.15 AND NOT compatible | 32% (~1.2k) | ≥95% overall=0 |
| related_skill_positive | J < 0.15 AND expanded ≥ 0.5 AND same role AND \|Δsen\| ≤ 1 | 20% (~760) | đa số ≥1 |
| seniority_hard_neg | same role AND J ≥ 0.2 AND \|Δsen\| ≥ 2 | 13% (~500) | ≈0 |
| missing_must_have | same role AND 0.15 ≤ J < 0.5 AND missing ≥2 skills imp≥4 | 10% (~380) | 0/1 |
| boundary_medium | compatible AND 0.08 ≤ J < 0.2 | 15% (~570) | trộn |
| random + positive top-up (J ≥ 0.25, same role, Δsen ≤ 1) | — | 10% (~380) | ≈0 / ≥1 |

Controls: per-CV cap 30/bucket; role stratification (round-robin theo role của CV); dedup vs ALL PairQueue rows (unique_together + pre-check set); shortfalls logged, not relaxed.

**Expanded overlap** (related_skill): expand cv_skills via (a) SKILL_CLUSTERS co-members, (b) semantic skill edges (cosine ≥ 0.7, precomputed once per run from the embedding provider), then `expanded_jaccard = |expanded ∩ job_skills| / max(|job_skills|,1)`. Mirrors `PairLabeler._skill_overlap_effective` semantics (denominator = job side) — coverage of job requirements, not symmetric Jaccard.

## R3. Split assignment

**Decision**: 70/15/15 assigned WITHIN each bucket with a seeded RNG at generation. Guarantees every bucket in every split (FR-002, SC-005).

## R4. Export/import contracts (chi tiết ở contracts/cli.md)

- Export JSONL per pair: `{pair_id, bucket, cv:{role, seniority, experience_years, skills:[{name,proficiency}], text≤1200}, job:{title, role, seniority, experience_min, skills:[{name,importance}], text≤1200}}`. Chunked 22 pairs/file (`chunk_NNN.jsonl`) — sized so one agent call handles one chunk comfortably.
- `--pilot N`: stratified sample across buckets (proportional, min 15/bucket). `--pair-ids file`: bypass status filter (for re-label + double-label). `--reasons a,b`: filter buckets.
- Import: validate pair tồn tại + 5 score ∈ {0,1,2}; tạo 1 `LabelingBatch` cho mỗi lần import (workers=0, dùng làm container truy vết) + `HumanLabel(note='claude-labeled', labeled_by=None, batch=batch)`; set pair LABELED (trừ khi đã LABELED — re-label giữ nguyên). **Idempotent**: skip pair_id đã có label trong CHÍNH batch import này (chạy lại file an toàn); label mới ở batch mới luôn được phép (latest-wins).

## R5. Agent labeling protocol

**Decision**: one agent = one chunk (~22 pairs). Prompt = `agent-rubric.md` (rubric verbatim + 3 worked examples từ rubric-tests.md + output contract: JSON array `[{pair_id, skill_fit, seniority_fit, experience_fit, domain_fit, overall}]`, schema-enforced via Workflow structured output). Temperature not controllable → rubric rules là mechanical, worked examples khoá hành vi.

**Pilot gate (hard)**: 180 cặp stratified → import → `audit_labels --batch N` → so với cột Expected (R2). Cross_domain <95% overall=0 hoặc related_skill đa số =0 → DỪNG, sửa selection/prompt, re-pilot. Ghi `pilot-report.md`.

**Agreement**: sample 200 cặp đã label (random, seeded) → export qua `--pair-ids` → agents label độc lập (không thấy nhãn cũ) → so sánh: exact % (overall), exact % per-dim; cặp lệch ≥2 mức → judgment thứ 3. Ghi `agreement-report.md`. Target ≥80% exact overall.

## R6. Re-label old slices (1.5)

**Decision**: query 2 slice — (a) pairs có >1 distinct overall giữa các HumanLabel; (b) HumanLabel skill_fit=2 & domain_fit=0 (lấy pair_id) — dump ra file id, export `--pair-ids`, label như thường. KHÔNG reset status, KHÔNG xoá nhãn cũ (history + latest-wins).

## R7. Export verification (1.6)

**Decision**: `export_dataset.py --output data/processed/v4_relabel` (dedup 021 sẵn). Mở rộng export ghi kèm `bucket` (selection_reason của pair) vào labels.json → verify per-bucket per-split bằng script nhỏ. Graph guard check: load dataset → `GraphBuilder.build` (no train) → phải không raise. Positive rate kỳ vọng giảm nhẹ (buckets thiên negative) — chấp nhận trong 25-40%; lệch hơn → ghi nhận + cân nhắc subsample lúc TRAIN (Đợt 2), không sửa data.

## R8. Token/cost control

Batched: pilot (~8 calls) → scale (~165 calls qua Workflow 10-16 concurrent) → agreement (~10 calls) → re-label (~24 calls). Export skips already-labeled; import idempotent → đứt giữa chừng chạy lại không hại. Tổng ~210 agent calls.
