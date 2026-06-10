# Pilot Report (022 / 1.3) — 2026-06-10

**Pilot**: 176 cặp (22 × 8 bucket, stratified) · 8 agent song song · import batch 11 (+ batch 12 re-label).

## Vòng 1 — phát hiện lỗ hổng rubric (gate hoạt động đúng)

| Bucket | %0 / %1 / %2 | Kỳ vọng | Verdict |
|---|---|---|---|
| cross_domain_hard_neg | **100 / 0 / 0** | ≥95% =0 | ✅ |
| related_skill_positive | 32 / 64 / 5 (**68% ≥1**) | đa số ≥1 | ✅ |
| seniority_hard_neg | 14 / **86** / 0 | ≈0 | ❌ |
| missing_must_have | 14 / 82 / 5 | trộn 0/1 | ✅ |
| boundary_medium | 32 / 64 / 5 | trộn | ✅ |
| high_overlap | 5 / 14 / 82 | đa số ≥1 | ✅ |
| random / hard_negative | 100 / 0 / 0 | ≈100% =0 | ✅ |

**Root cause FAIL**: rubric không có rule cứng cho seniority — cặp skill=2/domain=2/Δsen≥2 rơi vào "judgment" → agents chấm 1. Cùng lớp lỗi với lỗ hổng domain (A5) đã vá ở 021. Pilot gate bắt được TRƯỚC khi nhân ra 3.800 nhãn — đúng mục đích thiết kế.

## Fix + vòng 2

Vá rubric (cả `pair_scoring.md` + `agent-rubric.md`), rule bất đối xứng đúng nghiệp vụ staffing:
- **Job cao hơn CV ≥2 bậc → overall = 0** (junior không giao được việc lead)
- **CV cao hơn job ≥2 bậc → overall ≤ 1** (làm được nhưng lệch placement)

Re-label 22 cặp seniority (batch 12, latest-wins supersede): **36.4% =0 (under-qual) · 63.6% =1 (over-qual, cap) · 0% =2** — khớp kỳ vọng bất đối xứng. Cột Expected trong `audit_labels` cập nhật tương ứng.

## GATE DECISION: ✅ **PASS — SCALE**

Mọi bucket khớp kỳ vọng sau fix. Bucket quan trọng nhất (cross_domain — pattern bug Compositor) đạt 100% =0; related_skill (lợi thế GNN) cho 68% positive — tín hiệu mà ground truth cũ KHÔNG THỂ có (rubric cũ ép 0).

Lưu ý cho agreement check (1.4): cụm seniority/judgment là vùng chấm khó nhất — sample double-label nên phủ đủ bucket này.
