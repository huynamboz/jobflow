# Quickstart: Targeted Relabeling (Đợt 1)

```bash
cd backend

# 1.1 — sinh cặp bucket (~3.8k, dedup, stratified)
.venv/bin/python manage.py generate_pairs --buckets --n-pairs 3800 --dry-run   # xem bảng quota
.venv/bin/python manage.py generate_pairs --buckets --n-pairs 3800

# 1.3 — PILOT (hard gate)
.venv/bin/python manage.py export_pending_pairs --out /tmp/labeling-022/pilot --pilot 180
#   → Claude chạy ~8 agents trên các chunk → ghi labels JSONL
.venv/bin/python manage.py import_labels --in /tmp/labeling-022/pilot-labels/ --dry-run
.venv/bin/python manage.py import_labels --in /tmp/labeling-022/pilot-labels/
.venv/bin/python manage.py audit_labels --batch <N> --buckets
#   → đối chiếu Expected → GATE: scale / stop+fix (ghi specs/022/pilot-report.md)

# 1.4 — SCALE + AGREEMENT (chỉ sau khi pilot PASS)
.venv/bin/python manage.py export_pending_pairs --out /tmp/labeling-022/full
#   → Claude Workflow ~10-16 agents song song → import theo lô
#   → double-label: sample 200 id đã label → export --pair-ids → agents độc lập →
#     agreement report (specs/022/agreement-report.md) → re-label cặp lệch ≥2

# 1.5 — re-label slice cũ (284 conflict + 232 skill2/domain0)
#   → query id → export --pair-ids → label → import (latest-wins tự thay nhãn cũ)

# 1.6 — export dataset mới + verify
.venv/bin/python export_dataset.py --output data/processed/v4_relabel
#   → check: positive rate 25-40%, bucket đủ 3 split, graph build 0 conflict
```

## Gates & success signals

- **Pilot gate**: cross_domain ≥95% overall=0 · related_skill đa số ≥1 · seniority_hard_neg ≈0 · boundary trộn. Lệch → DỪNG.
- Agreement ≥80% exact overall trên 200 cặp; mọi lệch ≥2 mức có judgment 3.
- Export: unique pairs, 0 graph conflict, bucket phủ 3 split, mọi nhãn mới truy vết được (note='claude-labeled' + batch).

## Resume an toàn

Đứt giữa chừng: export mặc định chỉ lấy pending → chạy lại tự bỏ phần đã label; import idempotent per batch-file.
