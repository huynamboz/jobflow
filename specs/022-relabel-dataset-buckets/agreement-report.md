# Inter-Rater Agreement Report (022 / 1.4) — 2026-06-10

**Thiết kế**: 200 cặp random (seed 7) từ batch 13 (3.310 nhãn scale) được agent Sonnet **độc lập chấm lại** (không thấy nhãn gốc), cùng rubric. Nhãn gốc: 25 chunk đầu Fable, còn lại Sonnet.

## Kết quả

| Chiều | Exact agreement |
|---|---|
| **overall** | **87.0%** (target ≥80% ✅) |
| experience_fit | 99.0% |
| domain_fit | 93.5% |
| seniority_fit | 92.0% |
| skill_fit | 84.0% |

- **Lệch ≥2 mức: 1/200 cặp** (pair 25646: 0 vs 2) → judgment thứ 3 độc lập quyết định (latest-wins).
- skill_fit là chiều "mềm" nhất (phán đoán transferable + đọc text) — 84% exact với thang 3 mức là mức đồng thuận tốt; mọi bất đồng còn lại đều 1 mức.

## So chéo 2 model (calibration trước scale — 66 cặp Fable↔Sonnet)

Sau khi vá rubric (rule tag `other`): domain 98.5% · overall **93.9%** · 0 lệch ≥2 mức → 2 model dùng lẫn được; 25 chunk Fable + 126 chunk Sonnet trong cùng dataset là chấp nhận được và có bằng chứng định lượng.

## Kiểm soát cơ học bổ sung (toàn bộ 3.310 nhãn)

- 0 vi phạm rule cứng (skill=0→0, domain=0→0, seniority-under→0, điều kiện overall=2).
- `seniority_fit` enforce đúng công thức sau label: 48 hiệu chỉnh (1.5%), 0 mâu thuẫn phát sinh.

**Kết luận**: chất lượng nhãn đo được và đạt chuẩn đề ra — dataset đủ điều kiện vào bước export/retrain.
