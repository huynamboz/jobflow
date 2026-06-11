# Evaluation & Weight Tuning (lịch sử 019 → 020)

## Công cụ

### `tune_hybrid_weights` (apps/matching/management/commands/)
- Load engine **không snapshot** (`job_pool_dir` absent) → pool = training jobs mà nhãn trỏ tới.
- `engine.labeled_pair_components()`: từ cạnh match/no_match trong graph.pt → per-pair `(cv_idx, job_idx, label, gnn, skill, seniority, domain, cv_role, job_role)` — tính 1 lần, sweep chỉ re-weight.
- Sweep simplex `α+β+γ+δ=1` grid 0.05 (~1771 combo). Mỗi combo đo **2 loại metric**:
  - **label-AUC**: tách match/no_match (không dùng role)
  - **role-NDCG@10 / role-P@10**: per-CV query, relevant = `infer_role(cv)==job.role_category`
- **Objective mặc định "balanced"**: max role-NDCG **s.t.** label-AUC ≥ 0.85·max **và** δ ≤ 0.40. Lý do: pure role-NDCG **degenerate** — δ=1.0 biến score = chính tín hiệu relevance (NDCG=1.0, AUC sụp 0.62).
- Output: dual ablation markdown (`specs/020-domain-aware-ranking/ablation.md`) + `--write` → metadata.json.

### `eval_matching` (harness chất lượng)
- **20 CV cố định** (FE React/Vue, BE Python/Node/Java/PHP/.NET/Go, fullstack, devops, data/ML, data eng, mobile RN/Android/iOS, QA, cloud, UI/UX, junior) chạy `match_cv_data` với **live engine**.
- Báo per-CV top-K (title·score·domain_fit) + `top1_on_domain` (domain_fit ≥ 0.5) + summary rate.
- Dùng làm regression guard — chạy lại sau mọi thay đổi scoring.

## Lịch sử số liệu (quan trọng — đừng lặp lại sai lầm)

| Mốc | Weights | Kết quả |
|---|---|---|
| Gốc (hand-set) | 0.55/0.30/0.15/— | label-AUC 0.861 · eval chưa đo |
| **019**: tune label-AUC | 0.20/**0.75**/0.05/— | label-AUC **0.917** NHƯNG eval 20-CV lộ bug: backend CV → **Compositor/Animator** (top1_on_domain **50%**) |
| 020 pure role-NDCG (degenerate, KHÔNG dùng) | 0/0/0/**1.0** | role-NDCG 1.0 giả tạo, AUC sụp 0.62 |
| **020 balanced (HIỆN TẠI)** | **0.10/0.25/0.25/0.40** | role-NDCG 0.998 · label-AUC 0.798 · eval **top1_on_domain 90%**, on_domain@5 0.90 |

**Bài học cốt lõi**:
1. **Label-AUC cao ≠ ranking thật tốt** — nhãn skill-driven nên optimizer dồn về skill, kéo job lạc nghề lên top.
2. **Metric chứa tín hiệu nằm trong score → degeneracy** (circularity) — phải constrain (AUC floor + δ cap) + verify bằng eval định tính độc lập.
3. **α (GNN) thấp (0.10)** vì: nhãn skill-biased + GNN học từ chính nhãn đó (multicollinearity với β,δ) + 2 metric đều ưu ái tín hiệu thô. GNN vẫn sống ở reranker (feature gnn_score/gnn_rank/stage1) + inductive encoding. Muốn α lên đúng bản chất → sửa **nhãn** (xem 08).

## 2 ca lệch còn lại trong eval

Data/ML + Data Engineer CV → top job "Senior Data Analyst" có `role_category=""` (chưa được LLM extraction label) → domain trung tính 0.5 nhưng các job VFX có python vẫn chen được khi pool thiếu job data có nhãn. Fix = vá taxonomy (label role cho nhóm data/analyst jobs).

## Test liên quan

`apps/matching/tests.py`: `DomainAwareTests` (role fit 1/0.5/0, simplex4 sum=1, NDCG helper thưởng relevant-on-top), `DimensionScoreTests` (6 test công thức dims), snapshot/jobdata tests (018).

## Cập nhật sau Đợt 2 (retrain trên v4_relabel — 2026-06-10)

| Mốc | Weights | Eval 20-CV | Ghi chú |
|---|---|---|---|
| Đợt 0 baseline (model cũ, pipeline đúng) | 0.10/0.25/0.25/0.40 | 75% | reranker cũ train nhãn bẩn |
| v4 + AUC-max weights | 0.15/0.75/0/0.10 | 45% | δ yếu → skill flood retrieve |
| v4 + balanced | 0.05/0.35/0.20/0.40 | 60% | reranker bị job degenerate lừa |
| **v4 + balanced + domain gate ×0.40 (HIỆN TẠI)** | như trên | **90% · on_domain@5 0.90** | gate = thực thi rule nhãn |

**Bài học metric (3 hồi, khép vòng):** (1) label-AUC trên nhãn bẩn → lạc nghề (019); (2) role-NDCG chữa được nhưng degenerate nếu không constrain (020); (3) sau khi nhãn tự encode domain (022), role-NDCG bão hoà 1.0 — label-AUC sạch + eval định tính thành bộ thước cuối; và **AUC pairwise vẫn không phải proxy cho chất lượng retrieve top-K** (stage-1 cần domain mạnh chống flood).

**Negative result GNN (trung thực):** GNN decode AUC ≈ 0.51 trên slice related-skill (760 cặp) — ngang đoán mò, oversample ×3 không đổi — trong khi semantic-skill thủ công đạt 0.861. Hệ quả: α tune 0.05-0.15 là phản ánh đúng; giá trị GNN còn lại = inductive encoding (018) + feature trong reranker. Đây là phát hiện đáng trình bày: "ensemble các tín hiệu đồ thị thủ công + rules thắng GNN học ở quy mô data này (366 CV)".

**Domain gate (022):** ordering penalty ×0.40 khi `_role_domain_fit=0` — không phải magic number tự do mà là thực thi rule ground-truth (`domain=0 → overall=0`) ở serving; cần thiết vì catalog có job degenerate (VFX còn 2 skill sau lọc catalog — A10) đánh lừa mọi feature skill của reranker (acc 0.70).

## Cập nhật GNN v2 (feature 024 — 2026-06-11): negative result được GIẢI, không chỉ ghi nhận

Hồi 2 của câu chuyện GNN (hồi 1 ở trên: decode 0.512 ngang đoán mò, 3 phép đo hội tụ). 8 thí
nghiệm có kiểm soát (bảng đầy đủ: [12-gnn-v2-proposal](12-gnn-v2-proposal.md) mục 6):

| Nhóm | Thí nghiệm | Slice AUC | Kết luận |
|---|---|---|---|
| Training | aux role head, bucket-curriculum, slice early-stop, skill-rel loss, pretrain-alone | 0.51-0.55 | trần cứng — KHÔNG phải lỗi training |
| Kiến trúc | GATv2 attention | 0.540 | không phải mean-dilution |
| **Đầu vào** | **embedding đa ngữ** (E5) | **0.734** | **nút thắt thật** |
| Production | E6 = đa ngữ + pretrain | 0.705 | pipeline AUC 0.860 (kỷ lục) |

**Hệ quả lên trọng số**: re-tune trên E6 → **α=0.30 / β=0.20 / γ=0.10 / δ=0.40** (balanced;
label-AUC 0.786, role-NDCG 0.994). GNN từ tín-hiệu-phụ (α=0.05) thành đồng-trụ-cột với domain.
DoD "α≥0.3" — từng sửa trung thực vì negative result — **khôi phục bằng thực lực**.

**Xác nhận chất lượng 2 lớp**: harness 20-CV = 100% VÀ held-out 20 persona mới (Flask→Django,
Svelte, SRE, DBA, fresh-grad...) = **100%, on_domain@5 1.00** — loại nghi ngờ overfit harness.
Ca chứng minh năng lực mới: Flask CV → Python Developer jobs top-1 (related-skill transfer).

**Bài học phương pháp**: khi nhiều can thiệp training/kiến trúc đều kẹt cùng một trần → nghi
NGUỒN TÍN HIỆU ĐẦU VÀO trước khi nghi thuật toán. Caveat đo lường: global-decode AUC của model
BPR là thước méo (offset giữa CV phá pairwise toàn cục dù per-CV ranking tốt) — dùng per-CV
metrics + slice AUC.

**Vận hành**: `EMBEDDING_PROVIDER=multilingual` trong backend/.env BẮT BUỘC khớp checkpoint;
quy trình thí nghiệm chuẩn: train exp-dir trên Neptune → `measure_slice.py` trên server →
chỉ promote khi đủ (slice + pipeline + eval + re-tune + A14 reranker).
