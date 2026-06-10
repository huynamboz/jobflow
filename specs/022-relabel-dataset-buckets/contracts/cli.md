# Contracts: commands (022)

## CHANGED: `python manage.py generate_pairs --buckets --n-pairs 3800 [--per-cv-cap 30] [--seed 42] [--dry-run]`

- `--buckets`: chế độ mới — sinh 5 bucket theo quota R2 (32/20/13/10/15% + 10% random/top-up); mặc định (không cờ) giữ hành vi cũ nguyên vẹn.
- Dedup vs ALL PairQueue (mọi status). Per-CV cap. Split 70/15/15 stratified theo bucket (seeded).
- Output: bảng per-bucket (requested/created/shortfall) — shortfall LOG, không nới điều kiện.

## NEW: `python manage.py export_pending_pairs --out DIR [--reasons a,b] [--pilot N] [--pair-ids FILE] [--chunk-size 22] [--limit N]`

- Mặc định: pairs status=pending (mới chưa label). `--pilot N`: sample stratified theo bucket (min 15/bucket). `--pair-ids FILE`: export đúng các id (bỏ qua status — dùng cho re-label/double-label).
- Ghi `DIR/chunk_NNN.jsonl` (schema ở data-model E3) + `DIR/manifest.json` {num_pairs, num_chunks, buckets}.

## NEW: `python manage.py import_labels --in FILE_OR_DIR [--dry-run]`

- Đọc JSONL (schema E4). Validate: pair_id tồn tại; 5 score ∈ {0,1,2} (int). Lỗi → liệt kê, exit ≠ 0, KHÔNG ghi gì (atomic).
- Ghi: 1 LabelingBatch (workers=0) + HumanLabel/pair (note="claude-labeled") + pair status=LABELED (giữ nguyên nếu đã LABELED — re-label case).
- Idempotent: pair đã có label trong batch import này → skip (đếm `skipped_dup`). `--dry-run`: validate only.
- Output: imported/skipped_dup/errors + batch id.

## NEW: `python manage.py audit_labels [--batch N] [--buckets] [--since TS]`

- Bảng phân phối nhãn per-bucket (overall 0/1/2 %) đối chiếu cột Expected (in kèm) — dùng cho pilot gate + báo cáo cuối. `--batch N` giới hạn 1 batch import.

## CHANGED: `python backend/export_dataset.py …`

- labels.json row += `"bucket"` (PairQueue.selection_reason). metadata += `bucket_split_counts` (per-bucket per-split).

## Labeling protocol (không phải command — orchestration của Claude)

- Agent prompt: `specs/022-relabel-dataset-buckets/agent-rubric.md` (rubric vá 021 + 3 worked examples + output contract). 1 agent = 1 chunk. Workflow structured-output ép schema.
- Trình tự bắt buộc: pilot 180 → audit → GATE → scale → double-label 200 → agreement → re-label lệch ≥2 → re-label old slices → export.
