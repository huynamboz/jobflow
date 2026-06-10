---
description: "Task list — Targeted Relabeling Dataset (Đợt 1)"
---

# Tasks: Targeted Relabeling Dataset (Đợt 1)

**Input**: Design documents from `specs/022-relabel-dataset-buckets/`
**Prerequisites**: plan.md, spec.md, research.md (R1-R8), data-model.md, contracts/cli.md, agent-rubric.md
**Tests**: unit tests cho bucket conditions + export/import + audit. Backend root = `backend/`.

## Format: `[ID] [P?] [Story] Description`
Story map: US1 = buckets (1.1) · US2 = labeling chất lượng (1.2-1.4) · US3 = re-label slice cũ (1.5) · US4 = export verified (1.6).

---

## Phase 1: Setup + Foundational

- [ ] T001 Mở rộng `backend/apps/labeling/models.py`: SelectionReason +5 giá trị (cross_domain_hard_neg, related_skill_positive, seniority_hard_neg, missing_must_have, boundary_medium) + REASON_PRIORITY; chạy makemigrations (cosmetic AlterField) + migrate.

---

## Phase 2: User Story 1 — Bucket pair generation (P1)

**Goal**: ~3.8k cặp mới đúng quota, dedup, stratified.

- [ ] T002 [US1] Sửa `backend/apps/labeling/management/commands/generate_pairs.py`: mode `--buckets` với 6 điều kiện bucket (R2: quotas 32/20/13/10/15/10%), expanded-overlap cho related_skill (SKILL_CLUSTERS + semantic edges, denominator = job side), per-CV cap (--per-cv-cap 30), role stratification, dedup vs ALL PairQueue, split 70/15/15 stratified THEO bucket (seeded), bảng output requested/created/shortfall; `--dry-run`.
- [ ] T003 [P] [US1] Unit tests bucket conditions trong `backend/apps/labeling/tests.py`: mỗi bucket 1 case khớp + 1 case không (cross_domain cần role incompatible; related_skill cần direct<0.15 & expanded≥0.5; seniority cần Δ≥2; must_have cần thiếu ≥2 imp≥4), dedup không tạo trùng, split stratified đủ bucket.
- [ ] T004 [US1] Chạy thật: `generate_pairs --buckets --n-pairs 3800 --dry-run` → review bảng → chạy thật → verify SC-001 (quota ±20%, shortfall logged, 0 trùng).

---

## Phase 3: User Story 2 — Labeling hạ tầng + pilot + scale (P1)

**Goal**: nhãn agent chất lượng đo được; pilot gate trước scale.

- [ ] T005 [US2] Tạo `backend/apps/labeling/management/commands/export_pending_pairs.py` (contract cli.md): pending mặc định, `--pilot N` stratified (min 15/bucket), `--pair-ids FILE` (bỏ qua status), `--reasons`, chunk 22 cặp/file JSONL + manifest.json; text CV/job cắt 1200 ký tự.
- [ ] T006 [US2] Tạo `backend/apps/labeling/management/commands/import_labels.py`: validate (pair tồn tại, 5 score 0..2 int) atomic, LabelingBatch(workers=0) + HumanLabel(note='claude-labeled') + pair→LABELED (giữ nguyên nếu đã LABELED), idempotent per batch-file, `--dry-run`.
- [ ] T007 [US2] Tạo `backend/apps/labeling/management/commands/audit_labels.py`: phân phối overall per-bucket (%0/%1/%2, n) đối chiếu Expected (R2), `--batch N` filter.
- [ ] T008 [P] [US2] Unit tests export/import/audit trong `backend/apps/labeling/tests.py`: export schema + chunking + --pair-ids bypass status; import validate-reject + idempotent + đúng note/batch; audit đếm đúng.
- [ ] T009 [US2] **PILOT**: export `--pilot 180` → Claude chạy ~8 agents (prompt = agent-rubric.md) → import → audit → đối chiếu Expected → ghi `specs/022-relabel-dataset-buckets/pilot-report.md` với GATE DECISION. Lệch → dừng, sửa, re-pilot (lặp T009).
- [ ] T010 [US2] **SCALE** (chỉ sau pilot PASS): export remaining → Workflow ~10-16 agents song song, import theo lô, theo dõi tiến độ; mọi chunk lỗi schema → re-run agent.
- [ ] T011 [US2] **AGREEMENT**: sample 200 cặp đã label (seeded) → export `--pair-ids` → agents độc lập → so sánh, ghi `specs/022-relabel-dataset-buckets/agreement-report.md` (exact % overall + per-dim); cặp lệch ≥2 mức → judgment thứ 3 (latest-wins). Target ≥80%.

---

## Phase 4: User Story 3 — Re-label slice cũ (P2)

- [ ] T012 [US3] Query 2 slice: (a) pairs có >1 distinct overall (≈284), (b) pairs có HumanLabel skill_fit=2 & domain_fit=0 (≈232, trừ trùng với a) → dump pair_ids ra file.
- [ ] T013 [US3] Export `--pair-ids` → agents label với rubric mới → import → verify slice skill2/domain0 giờ ≈0% positive (latest-wins) — SC-004.

---

## Phase 5: User Story 4 — Export verified (P2)

- [ ] T014 [US4] Mở rộng `backend/export_dataset.py`: labels.json row += `bucket` (pair.selection_reason); metadata += `bucket_split_counts`.
- [ ] T015 [US4] Chạy `export_dataset.py --output data/processed/v4_relabel` → verify: unique pairs, positive rate 25-40% (hoặc ghi nhận lệch), mọi bucket đủ train/val/test, graph build qua guard 021 không raise (script nhỏ load dataset → GraphBuilder.build) — SC-005.

---

## Phase 6: Polish

- [ ] T016 Full test suite labeling + matching xanh; cập nhật `docs/codebase-knowledge/10-master-plan.md` (tick 1.1-1.6 + số liệu: tổng nhãn mới, agreement, positive rate) + `03-labeling-pipeline.md` (thêm đường label bằng agent).

---

## Dependencies & Execution Order

T001 → US1 (T002-T004) → US2 hạ tầng (T005-T008, có thể song song với T004) → T009 PILOT (gate cứng) → T010 SCALE → T011 AGREEMENT → US3 (T012-T013, sau khi rubric chứng minh qua pilot — có thể chạy cùng T010/T011) → US4 (T014-T015) → T016.

### Gates
- **T009 là gate cứng**: không PASS không được chạy T010+.
- T011 agreement <80% → dừng, điều tra trước khi export.

### MVP
US1 + US2 (pilot→scale) = giá trị cốt lõi; US3/US4 chốt dataset cho Đợt 2.
