# Master Plan — Matching đúng bản chất (GNN-driven)

**Cập nhật**: 2026-06-10 · **Trạng thái**: ✅ Đợt 0 HOÀN THÀNH (feature 021) — baseline bên dưới · Đợt 1 sẵn sàng
**Mục tiêu cuối**: hệ matching mà **GNN thực sự gánh tín hiệu** (học được cả domain từ data, α đáng kể sau tune), kết quả chính xác kiểm chứng được, mọi con số có cơ sở — sẵn sàng trình bày với lý thuyết đúng.

## Bối cảnh (đọc trước)

- Hiện trạng: on-domain 90% nhưng nhờ **δ·domain vá ngoài** (0.40); GNN chỉ α=0.10. Ground truth = 11.6k nhãn LLM bị **3 lỗi rubric + selection bias** → GNN không học được domain và không thể vượt skill-overlap baseline.
- Audit end-to-end tìm thêm **3 bug CRITICAL** trong pipeline (exp_min câm, nhãn trùng/mâu thuẫn vào graph, reranker bị sort cuối vô hiệu).
- Chi tiết: [08-improvement-opportunities](08-improvement-opportunities.md) · [09-pipeline-audit](09-pipeline-audit.md) · phân tích nhãn: [04](04-label-data-analysis.md).

## Nguyên tắc xuyên suốt

1. **Fix nền trước, data sau, train cuối** — không train trên data bẩn, không đo bằng thước hỏng.
2. Mỗi đợt có **acceptance check chạy được** (command cụ thể), xong mới sang đợt sau.
3. **Backup trước mọi thay đổi phá huỷ** (checkpoint, metadata) — luôn có đường rollback.
4. Label bằng **Claude agents** (Cách 1): rubric vá xong → pilot → audit phân phối → mới scale; double-label đo agreement.
5. Mọi số liệu cũ (AUC 0.917, ablation 019/020) **hết hiệu lực sau retrain** — regenerate toàn bộ.

---

## ĐỢT 0 — Fix nền pipeline (trước khi label/train bất kỳ thứ gì)

> Vá các bug làm sai lệch mọi thứ downstream. Tham chiếu mã lỗi trong [09](09-pipeline-audit.md).

- [x] **0.1 (A1)** `build_jobdata_from_db` truyền `experience_min/max` vào JobData → rebuild job pool. *Check: gate kinh nghiệm hoạt động lại (job exp_min=5 × CV 1y bị penalty).*
- [x] **0.2 (A2)** Dedup nhãn lúc export (mỗi pair lấy nhãn **mới nhất** theo created_at) + builder **assert** không có cặp vừa match vừa no_match. *Check: labels.json unique theo (cv_idx,job_idx); graph 0 cặp xung đột.*
- [x] **0.3 (A3)** Chốt semantics thứ tự cuối: final order = **reranker score × penalties** (hoặc bỏ reranker reorder có chủ đích — quyết định ghi vào doc 06); display score monotonic với thứ tự. *Check: list trả về không non-monotonic.*
- [x] **0.4 (A7)** `_evaluate_split` → **per-CV metrics** (group theo cv, average) thay vì global ranking. *Check: precision@5 không còn 1.0 artifact.*
- [x] **0.5 (A4+A5+A6)** Vá prompt `pair_scoring.md` (3 lỗi): (a) overall: skill=2&domain=0 → 0; (b) skill_fit tính **transferable skills** partial credit (Flask≈Django, Vue≈React, MySQL≈PostgreSQL, GCP≈AWS…); (c) bảng domain bổ sung mobile↔mobile=2, ba↔ba=2 (+ mobile↔frontend=1?). *Check: 3 case test prompt cho kết quả đúng.*
- [x] **0.6 (A9)** Dedup top-K khi serve (fingerprint/title+company) + dọn 731 row job trùng trong DB (giữ row mới nhất, migrate match FK nếu có). *Check: eval_matching không còn job lặp trong top-5.*
- [x] **0.7** Chạy lại `eval_matching` + test suite → ghi baseline mới sau fix nền (để so với sau retrain).

**Ưu tiên trong đợt**: 0.1 → 0.2 → 0.5 (chặn đường label) → 0.3 → 0.4 → 0.6 → 0.7.


**📊 Baseline post-fix (2026-06-10, feature 021):**
- eval_matching: **top1_on_domain 15/20 (75%) · on_domain@5 0.80** · 0 job trùng trong top-K
- ⚠️ Thấp hơn số 020 (90%) là ĐÚNG: số cũ đo khi final sort bypass reranker (bug A3); giờ kiến trúc 2 tầng chạy đúng → lộ reranker train-trên-nhãn-bẩn. Đợt 2 retrain phải vượt mốc 75% này VÀ mốc 90% cũ.
- Pool: 5.803 jobs (sau dedup 733 row) · export sạch 8.598 nhãn unique · full test suite xanh
- Số test_metrics cũ trong checkpoint (precision@5=1.0...) tuyên bố VÔ HIỆU (global-ranking artifact) — regenerate per-CV khi retrain.

## ĐỢT 1 — Data: sinh cặp + label lại (Claude agents)

> Chiến lược bucket chi tiết đã chốt — xem hội thoại/spec 021. Tóm tắt:

- [ ] **1.1** Mở rộng `generate_pairs.py` với bucket mới (~3.5-4k cặp, dedup với 10.5k cũ):
  | Bucket | Quota | Nhãn kỳ vọng (audit) |
  |---|---|---|
  | cross_domain_hard_neg (overlap≥0.15 × role không tương thích) | ~32% | ≥95% overall=0 |
  | related_skill_positive (direct<0.15, expanded≥0.5, cùng role) | ~20% | đa số ≥1 |
  | seniority_hard_neg (cùng role, overlap≥0.2, Δsen≥2) | ~13% | =0 dù skill cao |
  | missing_must_have | ~10% | 0/1 |
  | boundary_medium + positives bổ sung + random | ~25% | trộn / ≥1 / ≈0 |
  - Cap per-CV, stratify 11 role, split 70/15/15 **stratify theo bucket**.
- [ ] **1.2** Hạ tầng label bằng agent: command `export_pending_pairs` (dump JSONL) + `import_labels` (validate + ghi HumanLabel, note="claude-labeled").
- [ ] **1.3** **Pilot 150-200 cặp** → audit phân phối nhãn từng bucket so với kỳ vọng → lệch thì sửa rubric/selection trước khi scale.
- [ ] **1.4** Scale label toàn bộ (Workflow song song ~10-16 agents) + **double-label 200 cặp** → báo cáo inter-rater agreement.
- [ ] **1.5** Re-label 284 cặp mâu thuẫn cũ + slice skill=2/domain=0 (232 cặp) bằng rubric mới.
- [ ] **1.6** Export dataset mới (sau dedup 0.2) → kiểm metadata: positive rate ~30-40%, đủ bucket trong cả 3 split.

## ĐỢT 2 — Retrain + re-verify

- [ ] **2.1** Backup `checkpoints/latest` (+ metadata) → `checkpoints/backup_pre021/`.
- [ ] **2.2** (tuỳ chọn, khuyến nghị) BPR hard-negative thêm chiều domain (overlap cao × role mismatch) trong `_sample_bpr_pairs`.
- [ ] **2.3** Retrain GNN (`run_train_save.py`, dataset mới) + retrain reranker (nhãn + dims mới) + calibration. *Check: per-CV val metrics (0.4) hợp lý.*
- [ ] **2.4** Re-tune `tune_hybrid_weights` (dual ablation). *Kỳ vọng: α tăng rõ so 0.10, δ giảm; nếu KHÔNG → điều tra trước khi adopt.*
- [ ] **2.5** Re-verify: `eval_matching` (top1_on_domain ≥ 90%, 0 VFX top-1) + **GNN-advantage test** (related-skill pairs: GNN recall vs skill-overlap baseline) + leave-one-out ablation (đóng góp biên từng thành phần).
- [ ] **2.6** Rebuild job pool (model mới) → rematch employees → restart server → spot-check emp 20.
- [ ] **2.7** Cập nhật docs (02/05/06/07) + CLAUDE.md với số liệu mới; archive số cũ.

## ĐỢT 3 — Data-ops nền (song song/sau, không chặn)

- [ ] **3.1 (A8)** Label `role_category` cho 2.198 job thiếu (chạy lại JD extraction hoặc batch riêng) → δ·domain + role-metric phủ đủ pool.
- [ ] **3.2 (A11)** Schema extraction importance rõ ([REQUIRED]/[PREFERRED]) + validate skill với catalog + **đếm/log skill bị drop**.
- [ ] **3.3 (A12/A13)** Extraction seniority/experience: phân biệt "không xác định" với default MID; cross-check seniority vs years.
- [ ] **3.4 (A16)** Cân nhắc embedding đa ngữ (paraphrase-multilingual-MiniLM) cho 7% job tiếng Việt — **cần retrain**, gộp vào lần retrain sau.
- [ ] **3.5** Đồng bộ taxonomy role giữa `role_classifier.infer_role` ↔ `ROLE_CATEGORIES` (1 nguồn duy nhất).
- [ ] **3.6 (A14)** Sau mỗi lần đổi hybrid weights → retrain reranker (tránh distribution skew stage1_score).

## Definition of Done (toàn kế hoạch)

1. `eval_matching`: top1_on_domain ≥ 90%, 0 cross-domain top-1, không job trùng trong top-K.
2. Tuned α (GNN) **đáng kể** (kỳ vọng ≥ 0.3) với δ giảm — hệ GNN-driven thật.
3. GNN-advantage test: GNN bắt được related-skill matches mà baseline trượt (số liệu cụ thể).
4. Graph 0 cặp nhãn xung đột; metrics per-CV; gate kinh nghiệm hoạt động; thứ tự cuối nhất quán với thiết kế.
5. Docs 02-09 cập nhật đúng hiện trạng; checkpoint cũ còn backup.

## Quy ước vận hành

- Mỗi đợt = 1 feature spec-kit (021 = Đợt 0+1+2; Đợt 3 tách 022+).
- Cập nhật checkbox file này khi xong từng mục (cùng commit với code).
- Mọi lần chạy tốn kém (label scale, retrain) phải có pilot/check trước.
