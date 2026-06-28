# Câu hỏi tự kiểm tra — ôn bảo vệ JobFlow (GNN / MLP / Embedding)

Tự trả lời bằng lời của mình (nói to hoặc viết ra), rồi đối chiếu với
[ml_service-giai-thich.md](ml_service-giai-thich.md) + code. **Không nói lại được =
chưa hiểu.** Cột "soi code" là gợi ý chỗ kiểm chứng.

Quy ước tự chấm: ✅ trả lời trôi · 🔶 ấp úng, cần ôn lại · ❌ chưa biết.

---

## A. Nền tảng — MLP & phi tuyến (Ngày 1)

| # | Câu hỏi | Soi code |
|---|---|---|
| A1 | Một neuron làm phép tính gì? `w` và `b` là gì, cái nào model học? | `ranker.py` |
| A2 | Một lớp `Linear(23, 64)` nghĩa là gì? Vào bao nhiêu, ra bao nhiêu? | `ranker.py:36` |
| A3 | Vì sao xếp nhiều `Linear` mà **không có ReLU** thì vô nghĩa? | — |
| A4 | `ReLU(-3)` = ? `ReLU(5)` = ? ReLU phá vỡ điều gì? | — |
| A5 | "Phi tuyến" là gì? Cho 1 ví dụ quan hệ phi tuyến trong matching CV-job. | — |
| A6 | `loss.backward()` và `optimizer.step()` mỗi cái làm gì? | `trainer.py` |
| A7 | Vì sao lúc serving (`torch.no_grad()`) không chạy 2 cái đó? | `engine.py:1073` |
| A8 | `Dropout(0.2)` chống cái gì, bằng cách nào? | `ranker.py:38` |
| A9 | `lr` (learning rate) là gì? Lớn quá / nhỏ quá thì sao? | — |

## B. Embedding & node feature (Ngày 2)

| # | Câu hỏi | Soi code |
|---|---|---|
| B1 | Embedding văn bản là gì? Vì sao "gần nhau = giống nghĩa"? | `embedding/` |
| B2 | Hệ dùng model embedding nào? Vì sao **đa ngữ**? | — |
| B3 | Vì sao embedding 384 chiều cố định? Đổi model có phải dựng lại node? | — |
| B4 | CV node 397 chiều gồm những gì? (tách từng mảnh) | `builder.py:48` |
| B5 | Job node 397 và CV node 397 — vì sao **cố ý bằng nhau**? | `builder.py` |
| B6 | `role one-hot 11` là gì? CV và job có dùng chung không? Để làm gì? | `builder.py:30` |
| B7 | Cosine similarity đo cái gì? | — |

## C. Đồ thị & cấu trúc dữ liệu (Ngày 3)

| # | Câu hỏi | Soi code |
|---|---|---|
| C1 | Vì sao **không** dùng CNN/RNN cho đồ thị? Đồ thị khác ảnh/chuỗi ở đâu? | — |
| C2 | Graph trong code = những loại mảng nào? (feature + cạnh) | `schema.py` |
| C3 | `job.x` là gì? Shape bao nhiêu? `job.x[0]` là gì? | `graph.pt` |
| C4 | Vì sao gọi là `.x`? (quy ước thư viện nào) | — |
| C5 | `edge_index` lưu gì — `job_id` hay chỉ số hàng? Vì sao? | `builder.py:143` |
| C6 | Cạnh `(job, requires_skill, skill)` được dựng từ đâu? | `builder.py:142` |
| C7 | 4 loại node và các loại cạnh chính của graph JobFlow? | `schema.py` |
| C8 | Vì sao **skill là nút trung gian**? Cho ví dụ CV gặp job qua skill. | — |

## D. Message passing & encode (Ngày 3-4) ⭐ trọng tâm

| # | Câu hỏi | Soi code |
|---|---|---|
| D1 | Mô tả **3 bước** message passing cho 1 node (thu thập/mean/cập nhật). | `gnn.py:76` |
| D2 | "Node biết thông tin hàng xóm" — dịch sang ngôn ngữ vector nghĩa là gì? | — |
| D3 | Hệ dùng aggregator **mean**. Nêu 1 lý do mean tốt hơn sum. | `gnn.py:67` |
| D4 | Vì sao 3 lớp = bán kính lan truyền 3 bước? Vẽ đường CV→...→job. | `gnn.py:62` |
| D5 | **Over-smoothing** là gì? Vì sao nhiều lớp quá thì hỏng? | — |
| D6 | Encode gồm 2 phần nào? (projection + 3 lớp) projection để làm gì? | `gnn.py:74-76` |
| D7 | Trộn xong **đổi node cũ** hay **tạo vector mới**? Feature gốc có đổi? | `gnn.py:75` |
| D8 | Sau trộn graph có thành "graph mới" không? Cái gì đổi, cái gì giữ? | — |
| D9 | Cái gì lưu các version vector trung gian (z⁰,z¹,z²)? Lưu bao lâu? | — |
| D10 | Gọi `encode` khi nào, `decode` khi nào? Cái nào tốn, cái nào rẻ? | `trainer.py:377`, `engine.py:290` |
| D11 | Lúc serving, embedding cuối cache ở đâu? Vì sao phục vụ nhanh? | `engine.py:124` |
| D12 | CV ghi "ReactJS", job cần "HTML/CSS" — vẫn match được không? Qua đâu? | `builder.py` |

## E. Cạnh relates_to & PMI (đào sâu build graph)

| # | Câu hỏi | Soi code |
|---|---|---|
| E1 | Cạnh `relates_to` nối gì với gì? Để làm gì? | `builder.py:191` |
| E2 | 2 nguồn dựng `relates_to` là gì? Bù khuyết điểm nhau ra sao? | `builder.py:173-181` |
| E3 | Công thức PMI? `log(P(a,b)/(P(a)P(b)))` — vì sao chia cho `P(a)P(b)`? | `skill_graph.py:67` |
| E4 | Trọng số `argocd↔istio = 0.66` do ai đánh? Tính ra sao? | `skill_graph.py` |
| E5 | Vì sao lọc `count ≥ 3` và `PMI > 0`? | `skill_graph.py:62,72` |
| E6 | Nguồn ngữ nghĩa dùng gì? Ngưỡng bao nhiêu? Bù cho trường hợp nào? | `skill_graph.py:129` |

## F. GraphSAGE / Inductive / Hetero (Ngày 4) ⭐ phòng thủ

| # | Câu hỏi | Soi code |
|---|---|---|
| F1 | **Inductive** vs **transductive** khác nhau gì? | — |
| F2 | Thêm job mới có phải train lại GNN không? Vì sao? | `engine.py:989` |
| F3 | Mô tả các bước encode 1 CV mới (thêm node tạm → nối cạnh → encode). | `engine.py:1003` |
| F4 | Job mới chưa có nhãn match — lấy đâu tín hiệu để encode? | — |
| F5 | `to_hetero` làm gì? Vì sao cần xử lý nhiều loại node/cạnh riêng? | `gnn.py:67` |
| F6 | `role_head` để làm gì? Bỏ nó thì sao (AUC = ?)? Chạy khi nào? | `gnn.py:72` |
| F7 | Đã thử encoder khác (GAT/RGCN/sum/max) chưa? Kết quả? Nút thắt thật là gì? | `specs/028` |

## G. Học xếp hạng — BPR & pretrain (Ngày 5)

| # | Câu hỏi | Soi code |
|---|---|---|
| G1 | BPR loss công thức? `-log σ(pos-neg)` ép điều gì? | `losses.py:11` |
| G2 | Vì sao dùng BPR (ranking) thay vì loss phân loại (BCE)? | — |
| G3 | "Hard negative" là gì? Curriculum 0→30→70% nghĩa là gì? | `trainer.py` |
| G4 | Vì sao **nhãn thưa ~0,53%**? (3 lý do) | — |
| G5 | Pretrain (self-supervised link prediction) làm gì? Finetune làm gì? | `run_pretrain.py` |
| G6 | "Structure first, supervision after" nghĩa là gì? | — |

## H. Reranker & Calibration (Ngày 6)

| # | Câu hỏi | Soi code |
|---|---|---|
| H1 | Kiến trúc retrieve→rerank: vì sao tách 2 giai đoạn? | `engine.py:434` |
| H2 | Reranker dùng model gì? 23 đặc trưng gồm nhóm nào? | `ranker.py`, `features.py` |
| H3 | Vì sao MLP cho rerank (không phải GBDT/cross-encoder)? | — |
| H4 | Ordinal 3 lớp (0/1/2) — điểm tổng tính sao? Vì sao chia 2? | `ranker.py:191` |
| H5 | 4 đầu phụ (multi-task) để làm gì? Chạy khi nào? | `ranker.py:42` |
| H6 | Điểm reranker thô vì sao "vô nghĩa" (về mặt xác suất)? | — |
| H7 | Platt scaling công thức? `P = σ(a·s+b)`. `a`, `b` nghĩa là gì? | `calibration.py:104` |
| H8 | `a=7.96, b=-2.45` do ai đặt? Tính ra sao? | `calibration.py:48` |
| H9 | Vì sao `P ≥ 0.50` ⟺ điểm thô ≈ 0.31? | — |
| H10 | Điểm hiển thị cho HR nghĩa là gì chính xác? | — |

## I. Toàn pipeline & câu phòng thủ tổng (Ngày 7)

| # | Câu hỏi | Soi code |
|---|---|---|
| I1 | Kể 6 bước `match_cv` từ CV vào đến điểm ra. | `engine.py:434` |
| I2 | Hybrid 4 thành phần: công thức + trọng số? Vì sao không để GNN quyết hết? | — |
| I3 | Vì sao dùng GNN mà không chỉ cosine văn bản? | — |
| I4 | Chống lệch lĩnh vực (frontend↔devops) bằng mấy tầng? | — |
| I5 | Gates/penalty là gì? Kể vài gate + hệ số. | `engine.py` |
| I6 | Toàn bộ "hộp đen" của hệ nằm ở đâu? Phần nào tường minh, tái lập tay được? | — |
| I7 | Số production: hidden / lớp / α,β,γ,δ / node dims? (đừng đọc nhầm default) | `metadata.json` |

---

## Cách dùng file này
1. **Vòng 1** — đọc câu hỏi, tự trả lời miệng, chấm ✅/🔶/❌.
2. **Vòng 2** — chỉ ôn lại nhóm 🔶/❌, soi code cột bên phải.
3. **Vòng 3** (sát ngày) — nhờ người khác hỏi ngẫu nhiên, trả lời không nhìn tài liệu.

Ưu tiên nhóm ⭐ (D, F) — đó là phần hội đồng đào sâu nhất.

---
---

# ĐÁP ÁN (tự che lại khi làm vòng 1)

> Đáp án ngắn gọn để đối chiếu. Số production lấy từ `checkpoints/latest/metadata.json`.

## A. MLP & phi tuyến

- **A1.** Neuron: `y = w₁x₁+...+wₙxₙ + b` — nhân mỗi đầu vào với trọng số, cộng lại, cộng bias. `w` (tầm quan trọng) và `b` (độ lệch) là cái **model học** (lúc đầu ngẫu nhiên).
- **A2.** `Linear(23,64)` = 23 số vào → 64 số ra (= 64 neuron song song); về toán là 1 phép nhân ma trận `Wx+b` với W cỡ 64×23.
- **A3.** Vì 2 lớp Linear nối nhau gộp lại vẫn là 1 lớp tuyến tính (`W₂W₁x = Wx`) → xếp 100 lớp cũng như 1 lớp, chỉ vẽ được đường thẳng.
- **A4.** `ReLU(-3)=0`, `ReLU(5)=5`. ReLU = `max(0,x)`, "gãy khúc" tại 0 phá vỡ tính tuyến tính → mạng học được quan hệ có điều kiện.
- **A5.** Phi tuyến = quan hệ không phải đường thẳng (cong/gãy/có điều kiện). VD: "lệch cấp bậc chỉ phạt nặng khi job là senior"; "kinh nghiệm tăng điểm tới mức rồi bão hoà, thừa quá lại trừ".
- **A6.** `backward()` = backprop, tính gradient (mỗi w làm loss tăng/giảm hướng nào). `step()` = chỉnh w ngược hướng dốc 1 bước → loss giảm.
- **A7.** Serving chỉ cần **dự đoán**, không học → không tính gradient, không chỉnh w. `no_grad` tắt autograd → nhanh + tiết kiệm RAM; trọng số đông cứng.
- **A8.** Chống **overfit**. Lúc train ngẫu nhiên tắt 20% neuron mỗi vòng → model không dựa dẫm vài neuron, buộc học quy luật tổng quát.
- **A9.** `lr` = độ lớn mỗi bước gradient descent. Lớn quá → nhảy qua đáy, không hội tụ; nhỏ quá → học rất chậm.

## B. Embedding & node feature

- **B1.** Biến văn bản → vector số mang nghĩa. Model huấn luyện sao cho câu cùng nghĩa ra vector gần nhau → cosine cao = giống nghĩa.
- **B2.** `paraphrase-multilingual-MiniLM-L12-v2`. Đa ngữ vì catalog có ~7% tiếng Việt; model tiếng Anh đọc tiếng Việt thành nhiễu.
- **B3.** Vì model luôn xuất 384 chiều (hằng số của nó). Đổi sang model khác **cùng 384** thì không phải dựng lại kích thước node.
- **B4.** CV 397 = embed văn bản 384 + kinh nghiệm 1 + học vấn 1 + role one-hot 11.
- **B5.** Để decoder ghép `[z_cv ‖ z_job]` và so trong **cùng không gian**; phần 384+11 cuối giống hệt nhau nên so lĩnh vực trực tiếp.
- **B6.** Vector 11 chiều, bật 1 ở đúng lĩnh vực. CV và job **dùng chung** 11 lĩnh vực → là cách hệ so domain (thành phần δ).
- **B7.** Cosine = góc giữa 2 vector (bỏ qua độ dài); gần 1 = cùng hướng = giống nghĩa.

## C. Đồ thị & cấu trúc dữ liệu

- **C1.** Ảnh = lưới đều, chuỗi = thẳng hàng; đồ thị = quan hệ **bất quy tắc** (số hàng xóm khác nhau, không thứ tự). CNN/RNN giả định cấu trúc đều nên không dùng được.
- **C2.** 2 nhóm mảng: **feature** (mỗi loại node 1 ma trận `.x`) + **cạnh** (`edge_index` mỗi loại quan hệ).
- **C3.** `job.x` = ma trận mọi job, shape (6251, 397). `job.x[0]` = vector 397 số của job đầu tiên (text đã thành số).
- **C4.** Quy ước **PyTorch Geometric**: `.x` = node feature matrix (`x` = biến đầu vào).
- **C5.** Lưu **chỉ số hàng** (0..N-1), KHÔNG phải `job_id` nghiệp vụ. Vì message passing cần truy cập thẳng `job.x[idx]`. Builder dịch id→index.
- **C6.** Từ `job.skills`: duyệt từng job, mỗi skill trong danh sách → tạo cạnh `(job_idx, skill_idx)`, trọng số = mức quan trọng 1-5.
- **C7.** 4 node: CV/JOB/SKILL/SENIORITY. Cạnh: has_skill, requires_skill, has/requires_seniority, relates_to (skill-skill), similar_to, match/no_match (chỉ train).
- **C8.** Vì CV và job hiếm khi có nhãn match trực tiếp; chúng "gặp nhau" qua kỹ năng chung. VD: CV-Nam và Job-Backend cùng nối `python, django` → liên hệ được.

## D. Message passing & encode ⭐

- **D1.** ① Thu thập vector hàng xóm → ② **mean** chúng → ③ trộn (chính nó + mean) qua Linear+ReLU → vector mới.
- **D2.** = vector (256 chiều) của node đã được **trộn thêm vector hàng xóm** → các chiều dịch chuyển để phản ánh hàng xóm. Không có "trí nhớ", chỉ là phép cộng/trung bình số.
- **D3.** Mean không phụ thuộc số hàng xóm: job 4 skill hay 20 skill đều ra cùng thang đo. Sum thì job nhiều skill có vector "to" bất thường.
- **D4.** Mỗi lớp nghe hàng xóm cách 1 bước; 3 lớp = bán kính 3. Đường: CV → skill → (relates_to) → skill → job (3 bước) cần đúng 3 lớp.
- **D5.** Mỗi lớp là một lần lấy trung bình; lặp quá nhiều (8+ lớp) thì mọi embedding hội tụ giống nhau, mất danh tính → model hết phân biệt được.
- **D6.** (1) **Projection**: chiếu mọi loại node về 256 chiều (vì thô khác chiều: 397/385/6). (2) **3 lớp** message passing.
- **D7.** Tạo **vector mới** (z), không sửa node cũ; feature gốc `data[nt].x` **giữ nguyên** (encode chỉ đọc, return z mới). Shape đổi 397→256.
- **D8.** KHÔNG thành graph mới — **cạnh giữ nguyên**; chỉ **vector node được cập nhật**. "Cùng graph, embedding mới".
- **D9.** **Không cái gì** lưu version trung gian (z⁰,z¹,z²) — tensor tạm, lớp sau dùng xong giải phóng. Chỉ **trọng số lớp** (lưu lâu, để tái tạo) và **embedding cuối** (cache) được giữ.
- **D10.** `encode` 1 lần (tốn, chạy 3 lớp cả graph) → `decode` nhiều lần (rẻ, ghép 2 vector mỗi cặp). Nấu 1 nồi → bán nhiều tô.
- **D11.** `self._z_dict` (cache lúc khởi động, `engine.py:124`). Mỗi request chỉ decode trên cache, không encode lại → nhanh.
- **D12.** Được, **yếu hơn**. Không chung node skill, nhưng đi qua cạnh `relates_to`: CV→ReactJS→(relates_to)→HTML/CSS→Job (3 bước, khớp 3 lớp).

## E. relates_to & PMI

- **E1.** Cạnh **skill–skill** ("2 kỹ năng liên quan, trọng số w"). Là cầu nối phụ giúp CV và job dùng kỹ năng khác nhau nhưng cùng họ vẫn liên hệ.
- **E2.** (1) **PMI** (đồng xuất hiện thực tế, chắc nhưng hẹp) + (2) **cosine ngữ nghĩa ≥0,70** (bù cặp tương đương hiếm đi đôi như flask↔fastapi). Bù khuyết điểm nhau.
- **E3.** `PMI = log(P(a,b)/(P(a)·P(b)))`. Chia cho `P(a)P(b)` để **trừ yếu tố phổ biến** — skill phổ biến (python) không bị thổi phồng, chỉ giữ cặp "dính nhau bất thường".
- **E4.** **Không ai gán tay** — máy tính từ PMI. argocd&istio cùng xuất hiện 6/6617 docs → PMI thô 4.097 → chuẩn hoá [0,1] = 0.66.
- **E5.** `count≥3`: cặp gặp 1-2 lần là nhiễu, không tin. `PMI>0`: chỉ giữ liên quan dương (>0 = đi cùng nhiều hơn mức tình cờ).
- **E6.** Cosine giữa embedding tên kỹ năng, ngưỡng **0,70**, tối đa 5 cạnh mới/skill, chỉ thêm cặp PMI chưa có. Bù cặp gần nghĩa mà ít đồng xuất hiện.

## F. GraphSAGE / Inductive / Hetero ⭐

- **F1.** Transductive: học embedding cố định cho từng node đã thấy → node mới phải train lại. **Inductive**: học **hàm tổng hợp từ hàng xóm** → áp được cho node mới không train lại.
- **F2.** **Không**. GraphSAGE inductive — gắn node mới vào graph đông cứng, encode 1 lần. Chỉ rebuild embedding job, trọng số giữ nguyên.
- **F3.** Copy graph (không mutate gốc) → tạo feature CV mới đúng 397 chiều → nối cạnh has_skill/has_seniority tới node có sẵn → `encode()` dưới `no_grad` → lấy embedding node mới.
- **F4.** Qua **cạnh kỹ năng/cấp bậc** tới node skill/seniority đã train chín. Cạnh nhãn vốn bị gỡ khi serving (kể cả node cũ) — nhãn chỉ dùng lúc train.
- **F5.** `to_hetero` bọc backbone để mỗi **loại cạnh** có phép biến đổi riêng → xử lý đúng đồ thị nhiều loại node/cạnh (has_skill ≠ requires_skill ≠ seniority).
- **F6.** Đầu phụ phân loại 11 lĩnh vực, ép embedding **tách cụm theo nghề**. Bỏ nó → AUC lát-cắt-liên-quan ≈ **0,51**. Chỉ chạy **lúc train**.
- **F7.** Đã thử GAT, RGCN, sum, max, L2, jumping-knowledge, DropEdge, contrastive — **không cái nào vượt mean** ngoài độ lệch chuẩn. Nút thắt thật là **dữ liệu** (nhãn ~0,53%), không phải kiến trúc (`specs/028`).

## G. BPR & pretrain

- **G1.** `loss = -log σ(pos-neg)`. Ép điểm cặp **đúng > cặp sai** (pos>neg). Đúng thứ tự → loss nhỏ; sai → loss to.
- **G2.** Bài toán là **gợi ý/xếp hạng** (thứ tự quan trọng hơn điểm tuyệt đối). Nhãn thưa khiến BCE lệch về "không match"; BPR luôn so 1 đúng vs 1 sai nên né được.
- **G3.** Hard negative = cặp âm "khó" (trùng skill ≥0,15 và lệch cấp ≤1 — giống mà vẫn sai). Curriculum: tỉ lệ hard tăng dần (epoch <5→0%, <20→30%, sau→70%) — học dễ trước, khó sau.
- **G4.** (1) bùng nổ tổ hợp (366×6251 ≈ 2,3 triệu cặp); (2) nhãn cần chấm tay, hệ HR nội bộ không có implicit feedback; (3) match vốn hiếm (1 CV chỉ hợp 1 nhúm job).
- **G5.** **Pretrain** = self-supervised link prediction trên cạnh job–skill (giấu cạnh → đoán lại, không cần nhãn match) → backbone hiểu cấu trúc. **Finetune** = nạp backbone, train tiếp bằng BPR trên nhãn.
- **G6.** Học **cấu trúc** (skill nào đi với nhau, role cần gì) từ dữ liệu dồi dào không nhãn TRƯỚC, rồi mới tinh chỉnh bằng ít nhãn — đỡ tốn nhãn.

## H. Reranker & Calibration

- **H1.** Giai đoạn 1 quét cả kho lọc thô ~1000 (nhanh); giai đoạn 2 chấm kỹ ~1000 đó (chính xác). Tách vì chấm kỹ cả 8900 job mỗi request quá chậm.
- **H2.** MLP nhỏ đa nhiệm. 23 đặc trưng: tương tự văn bản, overlap kỹ năng (3 kiểu), kỹ năng thiếu, cấp bậc, penalty lĩnh vực, kinh nghiệm, độ hiếm skill, tỉ lệ tool, **điểm+hạng GNN**, cờ must-have/edge-case.
- **H3.** Dữ liệu ít → model nhỏ trên đặc trưng đã chắt lọc là đủ, không overfit. MLP cho **đa nhiệm share-trunk** + **xác suất mượt** để Platt hiệu chuẩn. Cross-encoder cần nhiều nhãn + hộp đen; GBDT khó đa nhiệm.
- **H4.** Đầu chính cho 3 xác suất (p0/p1/p2), điểm = `(0·p0+1·p1+2·p2)/2`. Chia 2 để ép về [0,1] (vì max là 2).
- **H5.** 4 đầu phụ cho 5 trục giải thích (skill/experience/seniority/domain_fit). Chỉ chạy **lúc train** (multi-task ép embedding tốt hơn); inference chỉ dùng đầu chính.
- **H6.** Vì BPR/ordinal chỉ học **thứ tự**, không học xác suất tuyệt đối. 0,55 không nghĩa "55% match"; thang bị nén/lệch, không so tuyệt đối giữa người được.
- **H7.** `P = σ(a·s+b)`. `a` = **độ dốc** (model phân tách dứt khoát cỡ nào); `b` = **độ dịch** (đặt ngưỡng điểm thô đạt 50%).
- **H8.** **Không ai đặt** — fit bằng `LogisticRegression` (sklearn LBFGS) trên điểm reranker + nhãn của tập validation. Máy tối ưu ra a≈7,96, b≈-2,45.
- **H9.** `P=0,5` khi `a·s+b=0` → `s = -b/a = 2,45/7,96 ≈ 0,31`. Tức điểm thô ≥0,31 thì P≥0,5.
- **H10.** = P(cặp được ground-truth v4 chấm là phù hợp), đã hiệu chuẩn — **tuyệt đối, so sánh được giữa nhân viên**. Không phải "xác suất được nhận việc".

## I. Toàn pipeline & phòng thủ

- **I1.** (1) encode CV (text 384 + inductive GNN 256); (2) retrieve ~1000; (3) hybrid 4 thành phần; (4) rerank MLP 23 feat; (5) gates+penalty; (6) Platt → P, eligible ≥0,50.
- **I2.** `base = α·gnn + β·skill + γ·sen + δ·domain` (0,30/0,20/0,10/0,40). Không để GNN quyết hết vì GNN decode đơn lẻ trên nhãn thưa yếu (AUC ~0,5); 3 thành phần kia là công thức tường minh, giải thích được + kiểm soát bằng gates.
- **I3.** Cosine chỉ thấy tương tự văn bản. GNN lan tín hiệu qua **kỹ năng chung** (CV/job chưa có nhãn vẫn liên hệ) + học từ nhãn match (BPR).
- **I4.** 2 tầng: `domain` là thành phần mềm (δ=0,40, lớn nhất) **và** một gate cứng nhân 0,40 khi lệch rõ; cộng role_match_penalty {1,0/0,7/0,45}.
- **I5.** Hệ số phạt nhân vào điểm: domain gate 0,40; experience 0,40 (thiếu)/0,85 (thừa>3năm); seniority 0,70/0,75 (lệch ≥2 bậc).
- **I6.** Hộp đen chỉ có GNN + reranker. Còn lại (skill/seniority/domain/gates/5 trục) là **công thức tường minh**, tái lập bằng tay được.
- **I7.** hidden=256, lớp=3, embed 384, node 397/397/385/6, α/β/γ/δ=0,30/0,20/0,10/0,40, Platt a=7,96 b=-2,45. (KHÔNG đọc default trong code: hidden=128/2 lớp/α=0,55 — đã bị metadata ghi đè.)
