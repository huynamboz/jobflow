# Improvement Opportunities (đúng bản chất "matching bằng GNN")

Tổng hợp mọi gap đã xác định được từ phân tích codebase + data (2026-06-10). Mục tiêu: GNN **tự học** được matching (kể cả domain), không dựa vào công thức vá ngoài; mọi con số có cơ sở.

## Bức tranh nhân-quả (vì sao GNN weight chỉ 0.10)

```
Chọn cặp label thiên skill-overlap (cross-domain chỉ rơi vào bucket RANDOM 10%)
  → tập nhãn chỉ có 2% cặp "skill cao × khác nghề" (232/11.611)
    → trong đó 43% bị LLM chấm SAI (prompt bỏ sót rule skill=2&domain=0)
      → GNN không học được ranh giới domain (bug Compositor)
        → phải vá δ·domain ngoài score (020)
          → tune trên nhãn skill-driven → β cao, α (GNN) thấp
```
**Sửa tận gốc = sửa nhãn → retrain.** Các fix dưới xếp theo ưu tiên.

## P1 — Data nhãn (gốc rễ)

1. **Vá prompt labeling** (`apps/labeling/prompts/pair_scoring.md` L70-78): thêm rule tường minh `skill_fit=2 & domain_fit=0 → overall=0` (hoặc max 1 nếu role thực sự chuyển đổi được). Hiện case này rơi "judgment call" → 100/232 nhãn mâu thuẫn.
2. **Sinh batch cross-domain hard negatives**: `generate_pairs.py` thêm bucket mới — cặp (skill overlap ≥ 0.2 × role KHÔNG tương thích) — chính pattern Compositor. Đề xuất vài nghìn cặp (nâng slice từ 2% lên ~15-20%). Chạy LabelingBatch LLM với prompt đã vá.
3. **Re-label/loại 100 cặp mâu thuẫn cũ** (skill=2, dm=0, overall=1) trước khi export.
4. **Vá taxonomy role**: (a) label `role_category` cho jobs đang trống (nhóm Data Analyst...) qua JD extraction; (b) **đồng bộ taxonomy** giữa `role_classifier.infer_role` (data/ml/security/erp) và `ROLE_CATEGORIES` của Job (data_ml/data_eng/qa/ba/design) — hiện lệch nhau, làm nhiễu cả domain term lẫn metric.

## P2 — Training (sau khi có nhãn tốt)

5. **Hard-negative sampling thêm chiều domain** (`trainer._sample_bpr_pairs` L126-128): hiện "hard" = overlap ≥ 0.15 & Δsen ≤ 1 — thêm loại hard = "overlap cao & role mismatch" để BPR ép GNN tách domain.
6. **CV node features thiếu role**: job có role one-hot[11], CV không có (chỉ ngầm trong text). Cân nhắc thêm role one-hot vào CV features (386→397) — đối xứng tín hiệu. (Đổi node_dims → retrain bắt buộc, đã nằm trong kế hoạch.)
7. **Retrain GNN + reranker** trên dataset mới (export batch mới) → đo lại: kỳ vọng GNN standalone AUC/role-NDCG tăng, tune lại ra **α cao tự nhiên**, giảm δ.

## P3 — Đo lường & minh bạch

8. **Leave-one-out ablation**: với best weights, lần lượt zero từng thành phần → đo cả 2 metric → định lượng đóng góp biên của GNN (trả lời "GNN thấp thế cần gì GNN").
9. **Test lợi thế GNN vs skill-overlap baseline**: tập cặp related-skill (Flask↔Django — overlap trực tiếp = 0) mà baseline bắt buộc trượt; đo GNN recall trên đó. Đây là giá trị học thuật cốt lõi của đề tài.
10. **eval_matching mở rộng**: thêm CV cross-domain (designer, BA) kiểm tra không bị match bừa vào dev jobs; thêm `--json` output để track theo thời gian.

## P4 — Vệ sinh hệ thống (nhỏ, không gấp)

11. `train_service` (in-app TrainRun) vẫn dùng `PairLabeler` synthetic — hoặc nâng cấp đọc HumanLabel, hoặc đánh dấu rõ "demo only" để khỏi nhầm với production path.
12. `_gnn_score_fast` trộn cứng `0.6·gnn + 0.4·text_sim` (engine.py:786) — magic number còn sót; cân nhắc đưa vào tuning hoặc docs hoá thành business rule.
13. Penalty/gate factors (0.40/0.70/0.85/0.75...) — đã chấp nhận là business rules; giữ docs nhất quán.
14. Skill catalog 145 skills — khá nhỏ so với catalog job thực; mở rộng alias khi thấy nhiều skill bị rớt (`skill_skipped_edges` trong RebuildReport).

## P5 — Serving scale (sau feature 027 — bottleneck = rerank, không phải retrieval)

027 đã tách retrieve→rerank + recall vectorized (`vector` mode, parity 20/20, ~10x@100k)
và đưa pgvector làm store. Bottleneck còn lại = **decoder GNN per-candidate ở rerank**
(cross-encoder-like, không dot-product → không ANN/vectorize được). Thứ tự đáng làm:

15. **Batch decoder** (win lớn nhất, rẻ, không retrain): hiện `_gnn_score_fast` gọi
    `model.decode` **từng candidate trong vòng lặp Python**. Gom K candidate (shortlist)
    thành **1 forward pass batch** → nhanh 10–100x. Stage A đã co N→K=1500; bước này
    score K đó theo lô.
16. **Cascade co K**: thêm tầng giữa composite-proxy → top ~200 → chỉ decoder 200
    (thay vì 1500). Giảm ~7x decoder calls.
17. **Two-tower** (chuẩn-prod, cần retrain — ngoài 027): tách CV-tower/job-tower để
    điểm GNN = **dot product** → retrieval = ANN trực tiếp, scoring O(1). Lúc đó
    pgvector ANN mới có nghĩa. Đây là cách production làm retrieval ở scale lớn.
18. pgvector **retriever** (ANN per-request) đã thử + **bỏ** ở 027 — chỉ đáng khi N
    hàng triệu + embedding không nhét RAM. Đừng làm lại trước khi có (15)/(17).

## Trình tự đề xuất (1 feature spec-kit)

```
021-label-quality-retrain:
  vá prompt (1) → sinh cặp cross-domain (2) → chạy LLM batch → làm sạch (3) + vá taxonomy (4)
  → export dataset mới → retrain GNN+reranker (5,6,7)
  → re-tune (dual metric) → eval_matching + leave-one-out (8,9)
  → rebuild job pool + rematch + restart
Backup checkpoints/latest trước khi retrain (rollback được).
Mọi số liệu 019/020 (AUC 0.917, ablation...) sẽ đổi — đúng, vì ground truth đổi.
```
