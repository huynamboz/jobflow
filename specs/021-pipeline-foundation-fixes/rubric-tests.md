# Rubric Test Cases (validation fixture)

Ba case kiểm chứng 3 bản vá rubric (A4/A5/A6). Mọi labeler (LLM provider hay Claude agent, Đợt 1) phải chấm ĐÚNG cả 3 trước khi label hàng loạt.

## Case 1 — (A5) skill cao × khác nghề → overall = 0

**CV**: role=backend, seniority=SENIOR, exp=5y, skills: python, django, postgresql, docker, redis.
**Job**: "Senior Compositor (VFX)", role=design (khác nghề), required: python, nuke; seniority SENIOR, không yêu cầu exp.

| Chiều | Kỳ vọng | Vì sao |
|---|---|---|
| skill_fit | 1-2 | python trùng trực tiếp (50% required) |
| domain_fit | **0** | backend ↔ design: khác nghề (bảng cứng) |
| **overall** | **0** | rule mới: skill_fit=2 & domain_fit=0 → 0 (và skill=1&domain=0→0 sẵn có) |

FAIL nếu: overall ≥ 1 (lỗi "judgment call" cũ).

## Case 2 — (A4) related-skill → partial credit, KHÔNG bị ép 0

**CV**: role=backend, seniority=MID, exp=3y, skills: flask, celery, sqlalchemy, mysql, gitlab_ci.
**Job**: "Backend Developer (Django)", role=backend, required: django (5), postgresql (4), jenkins (3); seniority MID, exp ≥ 2y.

| Chiều | Kỳ vọng | Vì sao |
|---|---|---|
| skill_fit | **1** (không phải 0) | 0 trùng trực tiếp NHƯNG flask≈django, mysql≈postgresql, gitlab_ci≈jenkins → partial credit ≈ 50% → mức 1 (30-70%) |
| domain_fit | 2 | backend ↔ backend |
| seniority_fit | 2 · experience_fit | 2 |
| **overall** | **1** | skill=1 & domain≥1 → 1 |

FAIL nếu: skill_fit=0 / overall=0 (rubric cũ ép negative — chính lỗi giết lợi thế GNN).

## Case 3 — (A6) mobile × mobile → domain = 2

**CV**: role=mobile, seniority=MID, exp=3y, skills: kotlin, android, java.
**Job**: "Android Developer", role=mobile, required: kotlin (5), android (5); seniority MID.

| Chiều | Kỳ vọng | Vì sao |
|---|---|---|
| skill_fit | 2 | kotlin+android = 100% required |
| domain_fit | **2** | mobile ↔ mobile (mục mới trong bảng) |
| **overall** | **2** | skill=2 & domain≥1 & seniority≥1 → 2 |

FAIL nếu: domain_fit=0 (bảng cũ thiếu mobile → "everything else").

## Cách dùng

1. Đưa 3 case (input phần CV/Job) qua labeler → so output với cột kỳ vọng.
2. Cả 3 đúng → labeler đạt chuẩn rubric, được phép label hàng loạt (Đợt 1).
3. Sai bất kỳ → sửa prompt/agent instructions, KHÔNG label tiếp.
