# Full-Pipeline Audit (2026-06-10)

> **UPDATE**: A1, A2, A3, A4-A6, A7, A9 đã **FIXED** trong feature 021 (Đợt 0). A8/A10-A20 còn lại thuộc Đợt 1-3.

Audit end-to-end: crawl → extraction → labeling → export → train → serving. Nguồn: 3 audit agent (code) + query DB thật + **verify tay các phát hiện nặng**. Ký hiệu: ✅ = đã verify trực tiếp, 🔎 = agent-reported (đáng tin, chưa verify tay).

## TỔNG QUAN — bảng ưu tiên

| # | Lỗ hổng | Tầng | Mức | Verify |
|---|---|---|---|---|
| A1 | `build_jobdata_from_db` **quên experience_min/max** → gate kinh nghiệm + experience_fit **câm với 100% pool live** | Serving | 🔴 CRITICAL | ✅ matching_service.py:286-296 |
| A2 | Export **không khử nhãn trùng**: 2.967 dòng trùng (34.5%), **247-284 cặp mâu thuẫn** → **181 cặp có CẢ cạnh match VÀ no_match** → BPR gradient ngược chiều | Export/Train | 🔴 CRITICAL | ✅ DB: 2.031 pairs >1 nhãn, 284 conflict; 🔎 builder/trainer không dedup |
| A3 | **Final sort ghi đè thứ tự reranker** (engine.py:497 sort theo display score = stage-1 + penalty) → reranker gần như chỉ còn cấp match_level | Serving | 🔴 HIGH | ✅ engine.py:497 |
| A4 | Rubric `skill_fit` chỉ tính coverage trực tiếp → **related-skill positives bị ép negative** (giết lợi thế GNN trong ground truth) | Labeling | 🔴 HIGH | ✅ pair_scoring.md:46-51,71 |
| A5 | Rule `overall` bỏ sót skill=2&domain=0 → 43% slice đó nhãn nhiễu | Labeling | 🔴 HIGH | ✅ (đã biết, doc 04) |
| A6 | Bảng `domain_fit` **thiếu mobile/ba/other** → mobile↔mobile = 0 (DB có 3 CV + 186 job mobile trong tập label) | Labeling | 🔴 HIGH | ✅ pair_scoring.md:66-68 + DB |
| A7 | **Test metrics trong metadata degenerate**: rank toàn cục 1.744 cặp thay vì per-CV → precision@5=1.0/NDCG=1.0/MRR=1.0 vô nghĩa (AUC 0.876 là số tin được duy nhất) | Train/Eval | 🟠 HIGH | 🔎 trainer.py:373-433 |
| A8 | **34% job live thiếu role** (2.198/6.536 trống/"other"; phía labeling 45%) → δ·domain trung tính 1/3 pool | Data | 🟠 HIGH | ✅ DB |
| A9 | **731 row job trùng** (343 nhóm title+company) + **không dedup trong top-K** → "JavaScript Tutor" ×3 | Data/Serving | 🟠 MED-HIGH | ✅ DB + eval output |
| A10 | Skill LLM trả về **không validate với catalog** → drop âm thầm ở sync (log DEBUG, không đếm) | Extraction | 🟠 MED | 🔎 sync_extracted.py:176-182 |
| A11 | `importance`/`proficiency` **default 3** khi LLM bỏ trống → tín hiệu "required (≥4)" (must_have penalty, missing_required features) không đáng tin | Extraction | 🟠 MED | 🔎 llm_jd_extractor.py:137 |
| A12 | **46% job seniority=MID (3.006)** — nghi default model (`Job.seniority default=MID`) khi extraction không xác định → gate seniority méo | Data | 🟠 MED | ✅ DB + models.py:89 |
| A13 | **48% job thiếu experience_min** (3.153 null/0) → kể cả fix A1, gate vẫn no-op nửa pool | Data | 🟠 MED | ✅ DB |
| A14 | **Reranker distribution skew**: feature stage1_score/gnn_rank train trên weights cũ (0.55/0.30/0.15), serve trên weights mới (0.10/0.25/0.25/0.40) | Serving | 🟠 MED | 🔎 features.py:278 |
| A15 | `infer_role` nhận text khác nhau giữa các path (full text vs 500 từ) → role có thể đổi giữa match lần đầu và re-match | Serving | 🟡 MED | 🔎 matching_service.py:325 |
| A16 | **7% job tiếng Việt** (427) × embedding MiniLM tiếng Anh → text_sim kém cho nhóm này; không có language detection ở đâu | Data/Embedding | 🟡 MED | ✅ DB |
| A17 | Normalization leakage: minmax salary/exp tính trên cả train+test (~0.5% feature) | Train | 🟡 LOW-MED | 🔎 builder.py:58-99 |
| A18 | 16 CV (4.4%) không có positive nào → không có tín hiệu BPR | Train data | 🟡 LOW | 🔎 |
| A19 | Over-fetch ×2 có thể trả < top_k khi nhiều job expired | Serving | 🟡 LOW | 🔎 |
| A20 | Salary không clamp/swap-check; combined_text phụ thuộc thứ tự field (phá dedup content_hash); seniority-vs-years không cross-check | Extraction | 🟡 LOW | 🔎 |

(Đã biết từ trước, không lặp: taxonomy role lệch giữa role_classifier ↔ Job.role_category; magic 0.6/0.4 trong _gnn_score_fast; penalty factors hand-set; selection bias cross-domain 2% — doc 04/08.)

## Chi tiết các phát hiện CRITICAL

### A1 — experience_min bị quên khi rebuild pool (bug production)
`build_jobdata_from_db` (matching_service.py:286-296) dựng `JobData(job_id, seniority, skills, importances, salary, text, role_category)` — **không truyền `experience_min/experience_max`** dù `Job` có cột này. JobData default `experience_min=0.0` → `engine` gate `if job.experience_min and job.experience_min > 0` **không bao giờ chạy** với pool live; `experience_fit` luôn 1.0. Fix: 1 dòng + rebuild pool. (Lưu ý A13: kể cả fix, 48% job vốn không có dữ liệu exp.)

### A2 — Nhãn trùng & mâu thuẫn chảy thẳng vào graph
`export_dataset.py` lặp `HumanLabel.objects.all()` **không dedup theo pair** → labels.json 11.565 dòng / 8.598 cặp unique (2.967 trùng, 247 mâu thuẫn nhị phân). `builder.build` thêm cạnh theo từng dòng → **181 cặp có cả match + no_match edge**. `_sample_bpr_pairs` đưa cùng job vào cả pos lẫn neg của 1 CV → **gradient tự đánh nhau**. Fix: dedup lúc export (lấy nhãn mới nhất theo created_at hoặc majority-vote) + assert builder không nhận cặp xung đột.

### A3 — Reranker bị sort cuối vô hiệu hoá
Stage-2 rerank xếp lại candidates, nhưng sau khi áp penalty, `results.sort(key=r.score)` (engine.py:497) sort theo **display score gốc stage-1** → thứ tự cuối = stage-1 + penalties, KHÔNG phải reranker. Docs/thiết kế nói "reranker quyết thứ tự" — thực tế không còn đúng sau dòng này. Fix (chọn 1): sort theo reranker score đã nhân penalty; hoặc bỏ re-sort, giữ thứ tự reranker và áp penalty như tie-breaker; đồng bộ lại display để monotonic.

### A4-A6 — Rubric labeling (3 lỗi)
Xem doc 03/04. Tổng fix prompt: (1) thêm rule overall skill=2&domain=0→0; (2) skill_fit cho phép **transferable/equivalent skills** partial credit (Flask≈Django...); (3) bổ sung mobile↔mobile=2, ba↔ba=2 (+other↔other=1?) vào bảng domain.

### A7 — Metrics train không phản ánh ranking thật
`_evaluate_split` đánh giá **toàn cục** (flatten mọi cặp test thành 1 ranking) → precision@5=1.0/NDCG=1.0/MRR=1.0 là artifact. Mọi quyết định trước đây dựa các số này (trừ AUC) không đáng tin. Fix: chuyển per-CV (group theo cv_idx, average) — giống cách `tune_hybrid_weights` đã làm cho role-metrics.

## Hệ quả cho kế hoạch 021

Kế hoạch 021 (label quality + retrain) **đúng hướng nhưng PHẢI mở rộng**: nếu chỉ thêm nhãn cross-domain mà không fix A1/A2/A3/A7 thì train trên data bẩn (nhãn trùng/mâu thuẫn), đo bằng thước hỏng, và serve qua pipeline có 2 bug (exp_min, sort). Thứ tự đúng:

```
Đợt 0 — FIX NỀN (trước khi label/train gì):
  A1 experience_min (1 dòng + rebuild pool)        A2 dedup export + assert builder
  A3 chốt semantics thứ tự cuối                    A7 per-CV metrics
  A6+A5+A4 vá prompt (3 lỗi)                       A9 dedup top-K + dọn 731 job trùng
Đợt 1 — DATA: bucket strategy (doc 08) + label bằng Claude agents + audit pilot
Đợt 2 — RETRAIN + re-tune + re-verify (eval harness, GNN-advantage check)
Đợt 3 — DATA-OPS nền: label role 34% job thiếu (A8), importance schema (A11),
        seniority/exp extraction quality (A12/A13), multilingual embedding (A16 — cân nhắc)
```
