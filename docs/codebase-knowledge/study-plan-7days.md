# Kế hoạch 7 ngày ôn kiến thức bảo vệ — GNN / HeteroGraphSAGE / MLP / Embedding

Mục tiêu: hiểu **bản chất** (không học vẹt) đủ để trả lời mọi câu hỏi hội đồng về lõi
ML của JobFlow. Mỗi ngày: **lý thuyết (sáng) → tài nguyên (chiều) → nối vào hệ của mình
(tối)**. Khoảng 3–4h/ngày. Phần "Nối vào đồ án" là quan trọng nhất — học xong soi lại
code/tài liệu để chốt.

> Tài liệu gốc của hệ: [ml_service-giai-thich.md](ml_service-giai-thich.md). Mọi ngày
> đều quay về đây đối chiếu số liệu production.

---

## Ngày 1 — Nền tảng: Neural network + MLP + phi tuyến

**Khái niệm cần nắm:** neuron, lớp Linear (`Wx+b`), hàm kích hoạt (ReLU/sigmoid),
**vì sao cần phi tuyến** (xếp chồng Linear vẫn là Linear), forward pass, loss,
gradient descent + backprop (ý tưởng, không cần đạo hàm tay), overfitting + dropout.

**Tài nguyên:**
- 3Blue1Brown — "Neural Networks" (4 video đầu, YouTube) — trực giác đẹp nhất.
- StatQuest — "Neural Networks / Backpropagation" (YouTube) — chậm, dễ.
- Đọc lướt: CS231n notes phần "Neural Networks 1".

**Nối vào đồ án:**
- Mở [ranker.py](../../backend/ml_service/reranker/ranker.py) — đọc `_RerankerMLP`
  (`Linear 23→64 → ReLU → Dropout → Linear 64→64 → ReLU → Linear 64→3`). Tự chỉ ra
  đâu là phi tuyến, đâu là chống overfit.
- **Decoder** của GNN ([gnn.py](../../backend/ml_service/models/gnn.py) `MLPDecoder`)
  cũng là một MLP → cùng nguyên lý.
- Chốt câu: "vì sao MLP mạnh hơn tổ hợp tuyến tính / tích vô hướng".

---

## Ngày 2 — Embedding & biểu diễn vector

**Khái niệm:** vector hoá văn bản, không gian embedding, **cosine similarity**, vì sao
"gần nhau = giống nghĩa", one-hot vs dense embedding, sentence embedding (Sentence-BERT),
chuẩn hoá L2. Khái niệm "cùng số chiều thì so sánh được".

**Tài nguyên:**
- Jay Alammar — "The Illustrated Word2Vec" (blog) — trực quan embedding.
- sbert.net — trang chủ Sentence-Transformers, đọc "Usage" + ý tưởng.
- Sentence-BERT paper (Reimers & Gurevych, EMNLP 2019) — đọc abstract + hình kiến trúc.

**Nối vào đồ án:**
- Hệ dùng `paraphrase-multilingual-MiniLM-L12-v2` (384 chiều). Xem
  [embedding/](../../backend/ml_service/embedding/).
- Đối chiếu node feature: CV 397 = embed 384 + exp 1 + edu 1 + role one-hot 11
  ([builder.py](../../backend/ml_service/graph/builder.py)). Tự giải thích từng mảnh.
- Chốt: "vì sao đa ngữ", "vì sao 384 cố định", "EMBEDDING_PROVIDER lệch = điểm vô nghĩa".

---

## Ngày 3 — GNN căn bản: đồ thị + message passing

**Khái niệm:** đồ thị (node/edge), vì sao dữ liệu đồ thị khác ảnh/text, **message
passing** (gom thông tin từ hàng xóm), aggregation (mean/sum/max), số lớp = bán kính
lan truyền (k lớp = nghe được hàng xóm cách k bước), node embedding.

**Tài nguyên:**
- Distill.pub — "A Gentle Introduction to Graph Neural Networks" (đọc kỹ, có tương tác).
- Distill.pub — "Understanding Convolutions on Graphs".
- Stanford CS224W (Jure Leskovec) — Lecture "GNN 1: Message Passing" (YouTube).

**Nối vào đồ án:**
- 3 lớp GraphSAGE = mỗi node nghe được hàng xóm trong 3 bước (CV → skill → job → skill).
- Vẽ tay đồ thị JobFlow: CV–skill–job–seniority (4 loại node). Đối chiếu
  [schema.py](../../backend/ml_service/graph/schema.py).
- Chốt: "vì sao skill là **nút trung gian** để CV và job gặp nhau".

---

## Ngày 4 — GraphSAGE + Inductive + Heterogeneous

**Khái niệm:** GraphSAGE (sample + aggregate), **inductive vs transductive** (điểm
sống còn của đồ án), vì sao GraphSAGE encode được node mới không cần train lại,
**heterogeneous graph** (nhiều loại node/edge), `to_hetero` (mỗi loại cạnh một phép biến đổi).

**Tài nguyên:**
- GraphSAGE paper (Hamilton, Ying, Leskovec — NeurIPS 2017, arxiv 1706.02216) — đọc
  abstract, Section 3 (thuật toán), hình 1.
- CS224W — Lecture "GraphSAGE / Inductive".
- PyTorch Geometric docs — "Heterogeneous Graph Learning" + `to_hetero` tutorial.

**Nối vào đồ án:**
- Đọc [_inductive_gnn_encode_cv](../../backend/ml_service/inference/engine.py) — chỉ ra
  bước "thêm node tạm → nối cạnh skill/seniority → encode 1 lần dưới `no_grad`".
- Chốt 2 câu phòng thủ: "thêm job mới có train lại không?" và "job mới chưa có nhãn thì
  lấy đâu tín hiệu?" (qua cạnh skill tới node skill đã train chín).

---

## Ngày 5 — Học xếp hạng: BPR + hard negative + pretrain/finetune

**Khái niệm:** bài toán **ranking** vs classification, **BPR loss**
(`-log σ(pos-neg)`), positive/negative sampling, **hard negative**, curriculum
(dễ→khó), **self-supervised pretraining** (link prediction) → **finetune**, vì sao
pretrain giúp khi **nhãn thưa**.

**Tài nguyên:**
- BPR paper (Rendle et al., UAI 2009, arxiv 1205.2618) — đọc abstract + công thức.
- Blog bất kỳ: "Bayesian Personalized Ranking explained".
- Khái niệm self-supervised: bài blog "Self-supervised learning" (Lilian Weng) — phần
  link prediction / contrastive (đọc ý tưởng).

**Nối vào đồ án:**
- [losses.py](../../backend/ml_service/models/losses.py) `bpr_loss` — giải thích từng mảnh.
- [trainer.py](../../backend/ml_service/training/trainer.py) — curriculum 0→30→70% hard neg.
- [run_pretrain.py](../../backend/run_pretrain.py) — link prediction trên cạnh
  `job–skill` (giấu cạnh → đoán lại). Chốt: "structure first, supervision after".
- Câu lõi: "vì sao nhãn thưa ~0,53%" (bùng nổ tổ hợp + nhãn đắt + match vốn hiếm).

---

## Ngày 6 — Reranker (MLP đa nhiệm) + Hiệu chuẩn Platt

**Khái niệm:** kiến trúc **retrieve → rerank** (vì sao 2 giai đoạn), **multi-task
learning** (trunk chung + nhiều head), ordinal output, **calibration** (điểm thô ≠
xác suất), **Platt scaling** = logistic regression 1 biến (`P = σ(a·s+b)`), reliability
(predicted vs observed).

**Tài nguyên:**
- "Retrieve and Rerank" — blog sbert.net (có sơ đồ 2 giai đoạn).
- Guo et al. "On Calibration of Modern Neural Networks" (ICML 2017) — đọc abstract +
  hình reliability diagram.
- Bài blog "Platt scaling / probability calibration" (sklearn docs phần "Calibration").

**Nối vào đồ án:**
- [ranker.py](../../backend/ml_service/reranker/ranker.py) — trunk + main head (ordinal
  3 lớp) + 4 aux head (5 trục). Giải thích `(0·p0+1·p1+2·p2)/2`.
- [calibration.py](../../backend/ml_service/reranker/calibration.py) — `a=7,96 b=-2,45`,
  fit bằng `LogisticRegression`. Chốt: a=độ dốc, b=ngưỡng (P≥0,5 ⟺ điểm ≈ 0,31).
- Câu lõi: "điểm hiển thị nghĩa là gì", "vì sao reranker + GNN chứ không chỉ một".

---

## Ngày 7 — Ghép toàn pipeline + Mock defense

**Việc:** không học mới — **kể lại toàn bộ luồng** từ CV vào đến điểm ra, rồi tự hỏi-đáp.

**Luồng phải kể trôi (6 bước `match_cv`):**
1. Encode CV (text 384 + inductive GNN 256).
2. Retrieve ~1000 (stage-1 hybrid).
3. Hybrid 4 thành phần `α·gnn+β·skill+γ·sen+δ·domain` (0,30/0,20/0,10/0,40).
4. Rerank (MLP 23 feature).
5. Gates + penalty.
6. Platt → P(match), eligible ≥ 0,50.

**Tự kiểm tra (đóng tài liệu, trả lời miệng):**
- Vì sao GNN thay vì cosine? Inductive là gì? Điểm hiển thị nghĩa gì?
- Vì sao hybrid 4 thành phần chứ không để GNN quyết hết?
- Chống lệch lĩnh vực thế nào? Đã thử cải tiến encoder chưa (ablation 028)?
- a,b trong Platt từ đâu? BPR là gì? phi tuyến là gì?

**Tài nguyên:**
- Mục 15 trong [ml_service-giai-thich.md](ml_service-giai-thich.md) — "Câu hỏi phòng vệ".
- Dùng 3 hình 3D đã dựng (`viz_graph_3d.py`, `viz_match_3d.py`) để luyện kể trực quan.

---

## Lịch nén nếu thiếu thời gian (ưu tiên)
1. **Bắt buộc:** Ngày 1 (MLP), 3 (message passing), 4 (inductive + hetero), 7 (ghép).
2. **Nên có:** Ngày 5 (BPR), 6 (Platt).
3. **Bổ trợ:** Ngày 2 (embedding) — nếu quen NLP rồi thì lướt nhanh.

## Nguyên tắc học (đừng học vẹt)
- Mỗi khái niệm: tự hỏi **"vì sao cần nó? bỏ đi thì hỏng chỗ nào?"** — hệ này mọi lựa
  chọn đều có lý do (role_head bỏ đi → AUC 0,51; ReLU bỏ đi → sụp tuyến tính; pretrain
  bỏ đi → kẹt vì nhãn thưa).
- Sau mỗi ngày, **giải thích lại cho người không biết** (hoặc viết 5 dòng) — không nói
  lại được = chưa hiểu.
- Luôn nối lý thuyết về **một dòng code thật** trong repo.
