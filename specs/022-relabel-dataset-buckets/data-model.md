# Phase 1 Data Model: Targeted Relabeling Dataset

## Entity 1 — SelectionReason (extended enum)

`apps/labeling/models.py` thêm 5 giá trị (cosmetic AlterField migration):
`cross_domain_hard_neg · related_skill_positive · seniority_hard_neg · missing_must_have · boundary_medium`
REASON_PRIORITY: bucket mới ưu tiên label trước RANDOM (5-9), giữ 4 giá trị cũ.

## Entity 2 — PairQueue row (new pairs)

Như hiện tại + `selection_reason` = bucket (audit key) · `split` gán stratified THEO BUCKET (seeded 70/15/15) · unique(cv, job) chống trùng với 10.5k cặp cũ.

## Entity 3 — Work chunk (JSONL, /tmp/labeling-022/)

```json
{"pair_id": 12345, "bucket": "cross_domain_hard_neg",
 "cv": {"role": "backend", "seniority": "SENIOR", "experience_years": 5.0,
         "skills": [{"name": "python", "proficiency": 4}], "text": "≤1200 chars"},
 "job": {"title": "Senior Compositor", "role": "design", "seniority": "SENIOR",
          "experience_min": 0.0, "skills": [{"name": "python", "importance": 4}],
          "text": "≤1200 chars"}}
```
File `chunk_NNN.jsonl`, 22 cặp/file. Một agent xử lý đúng 1 chunk.

## Entity 4 — Agent label (output contract)

```json
{"pair_id": 12345, "skill_fit": 1, "seniority_fit": 2, "experience_fit": 2,
 "domain_fit": 0, "overall": 0}
```
Import → `HumanLabel(pair, batch=<import batch>, note="claude-labeled", labeled_by=None, 5 scores)`; pair → LABELED. **Idempotent per (pair, import-batch)**. Nhãn cũ không bị sửa/xoá — latest-wins (021) quyết định bản dùng khi export.

## Entity 5 — LabelingBatch (agent batch)

1 batch / 1 lần import (container truy vết: tổng, lỗi). `workers=0` đánh dấu batch agent (không phải LLM-provider batch).

## Entity 6 — Pilot report (specs/022/pilot-report.md)

| Bucket | n | %overall=0 | %=1 | %=2 | Expected | Verdict |
|---|---|---|---|---|---|---|
→ gate decision (SCALE / STOP+FIX) + chữ ký thời điểm.

## Entity 7 — Agreement report (specs/022/agreement-report.md)

n cặp double-label · exact-match % overall · per-dim exact % · danh sách lệch ≥2 mức (+ kết quả judgment 3).

## Entity 8 — Dataset export v4_relabel

`labels.json` row += `"bucket"` (selection_reason). Metadata += per-bucket counts per split. Invariants: unique (cv_idx, job_idx) (dedup 021) · graph build 0 conflict (guard 021) · positive rate ghi nhận (kỳ vọng 25-40%).

## Flow

```
generate_pairs (buckets, dedup, stratified)
  → export_pending_pairs --pilot 180 → 8 agents → import_labels → audit_labels → PILOT GATE
  → export remaining → Workflow ~165 agents → import (batched)
  → double-label 200 (--pair-ids) → agreement report → re-label lệch ≥2
  → re-label old slices (--pair-ids: conflicting 284 + skill2/domain0 232)
  → export_dataset v4_relabel → graph-guard check → master plan tick 1.1-1.6
```
