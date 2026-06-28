# Phân tích lựa chọn kiến trúc bộ mã hóa (ablation)

Mục này trả lời câu hỏi: *bộ mã hóa HeteroGraphSAGE (tổng hợp trung bình, 2 lớp)
đang dùng đã là lựa chọn tốt chưa, hay còn cải tiến kiến trúc nào nâng được hiệu
năng?* Để trả lời trung thực, chúng tôi thử một loạt hướng cải tiến có cơ sở trong
tài liệu, đo trên **hai bộ dữ liệu** và **hai chế độ** khác nhau, giữ nguyên mọi
phần còn lại của hệ thống. Toàn bộ thí nghiệm chạy trong môi trường thử nghiệm
tách biệt, **không** đụng tới mô hình/checkpoint/kết quả production.

## 1. Các hướng cải tiến đã thử

| Nhóm | Hướng | Cơ sở (tài liệu) |
|---|---|---|
| Hàm tổng hợp | Attention (GATv2, 4 đầu) thay cho trung bình | GAT (Veličković 2018), GATv2 (Brody 2021) |
| Hàm tổng hợp | Tổng (sum) thay cho trung bình giữa các loại cạnh | GIN (Xu 2019) |
| Chuẩn hóa | Chuẩn hóa L2 embedding đầu ra | thực hành phổ biến trong truy hồi |
| Độ sâu | 3 lớp thay cho 2 lớp | khảo sát over-smoothing |
| Kết nối | Jumping-Knowledge (nối tầng) | JKNet (Xu 2018) |
| **Trọng số cạnh** | **GATv2 dùng mức quan trọng/thành thạo kỹ năng (edge_dim)** | **MPNN (Gilmer 2017), GATv2 edge features** |
| Chính quy hóa | DropEdge (bỏ ngẫu nhiên cạnh khi huấn luyện) | DropEdge (Rong 2020) |
| Học biểu diễn | Học tương phản (SimGCL: thêm nhiễu + InfoNCE) | SGL (Wu 2021), SimGCL (Yu 2022) |

Trong đó **trọng số cạnh** là hướng hứa hẹn nhất trên giấy tờ: đồ thị đã sẵn có
mức quan trọng của kỹ năng đối với job (thang 1–5) và mức thành thạo của ứng viên,
nhưng hàm tổng hợp trung bình/attention hiện tại **bỏ qua** thông tin này, coi mọi
kỹ năng như nhau.

## 2. Giao thức đo

- **Bộ resume-JD (công khai, chế độ warm-start, dày nhãn):** xếp hạng toàn không
  gian, đặc trưng nội dung cho nút, 3 hạt giống. Đây là chế độ đã **gần bão hòa**
  (NDCG@20 ≈ 0,49; Recall@20 ≈ 0,93).
- **Bộ nội bộ v4 (chế độ khó, thưa nhãn, còn dư địa):** xếp hạng có lấy mẫu âm
  (1 phù hợp vs 100 không phù hợp), 3 hạt giống. Đây là chế độ **còn nhiều dư địa**
  (NDCG@20 ≈ 0,39).

Mỗi hướng đều so trực tiếp với baseline (HeteroGraphSAGE trung bình, 2 lớp) trên
cùng dữ liệu/giao thức/hạt giống.

## 3. Kết quả

### 3.1 Bộ resume-JD (warm-start, gần bão hòa) — NDCG@20

| Biến thể | NDCG@20 | Δ vs gốc |
|---|---|---|
| HeteroGraphSAGE (trung bình, 2 lớp) — **gốc** | **0,494** | — |
| + Attention (GAT) | ≈ 0,49 | trong nhiễu |
| + sum / + L2 / + JK | ≈ 0,49 | trong nhiễu |
| 3 lớp (sâu hơn) | −0,08 đến −0,10 | **hại (over-smoothing)** |
| + DropEdge | −0,010 | trung tính/hơi hại |
| + Học tương phản (SimGCL) | −0,153 | **hại** |
| + DropEdge + Tương phản | −0,238 | **hại nặng** |

### 3.2 Bộ nội bộ v4 (khó, còn dư địa) — NDCG@20, 3 hạt giống (TB ± std)

| Biến thể | NDCG@20 (TB ± std) | Δ vs gốc |
|---|---|---|
| + sum (tổng hợp giữa các loại cạnh) | 0,394 ± 0,054 | +0,002 (hòa) |
| HeteroGraphSAGE (trung bình, 2 lớp) — **gốc** | **0,392 ± 0,048** | — |
| + L2 | 0,386 ± 0,047 | −0,006 (hòa) |
| **+ Trọng số cạnh (importance/proficiency)** | **0,372 ± 0,032** | **−0,020** |
| + Attention (GAT) | 0,366 ± 0,027 | −0,026 |
| + sum + Trọng số cạnh | 0,353 ± 0,049 | −0,039 |
| + DropEdge | 0,275 ± 0,083 | −0,117 (**hại nặng**) |
| + Học tương phản (SimGCL) | 0,213 ± 0,022 | −0,179 (**hại nặng**) |

Với độ lệch chuẩn ≈ 0,05, ba biến thể đầu (sum, gốc, L2) là một **thế hòa thống kê**:
khoảng cách giữa chúng (≤ 0,006) nhỏ hơn std cả chục lần. Attention và trọng số cạnh
rơi **dưới** baseline nhưng còn trong ~0,5 std (không phải cải thiện, cũng chưa phải
sụt rõ rệt). DropEdge và học tương phản sụt rõ ngoài độ lệch chuẩn.

## 4. Diễn giải

1. **Trên dữ liệu dày (resume-JD) các tinh chỉnh kiến trúc đã cạn dư địa.**
   Attention/sum/L2/JK đều rơi trong khoảng nhiễu của baseline. Tăng độ sâu lên 3
   lớp **làm giảm** hiệu năng — dấu hiệu over-smoothing kinh điển của GNN: chồng
   thêm lớp khiến biểu diễn các nút bị làm nhòe về nhau.

2. **Trên bài toán khó (v4) — nơi còn dư địa — vẫn không hướng nào vượt baseline
   ngoài độ lệch chuẩn.** Biến thể "tốt nhất" (+sum, +0,002) hòa với mean trong khi
   khoảng cách nhỏ hơn std hơn 20 lần — đây là nhiễu, không phải cải thiện. Điều đáng
   chú ý nhất: **trọng số cạnh — hướng hứa hẹn nhất về lý thuyết — KHÔNG giúp**, thậm
   chí thấp hơn baseline 0,020. Đưa thẳng thang quan trọng 1–5 vào attention khiến mô
   hình bám vào vài kỹ năng "điểm cao" và overfit trên tập nhãn thưa; tín hiệu thô này
   nhiễu và không nhất quán giữa các loại cạnh (mức quan trọng của job vs mức thành
   thạo của CV không cùng thang nghĩa). Tức là "tín hiệu đang bỏ phí" hóa ra **không
   khai thác được** bằng cách nhúng thẳng vào hàm tổng hợp.

3. **DropEdge và học tương phản hại trên cả hai bộ.** Cả hai kỹ thuật này được thiết
   kế để *tăng tính đều* (uniformity) của không gian biểu diễn; nhưng bài toán so
   khớp ở đây lại dựa vào việc *ghi nhớ* các quan hệ CV–job–kỹ năng cụ thể, nên việc
   ép đều phá vỡ chính tín hiệu cộng tác mà mô hình cần.

## 5. Kết luận

- **Kiến trúc gốc (HeteroGraphSAGE trung bình, 2 lớp) đã ở vùng tối ưu** cho dữ liệu
  và bài toán hiện có. Không tinh chỉnh kiến trúc nào trong số đã thử nâng được hiệu
  năng một cách bền vững; nhiều hướng còn làm giảm.
- **Lực bẩy thực sự không nằm ở kiến trúc bộ mã hóa mà ở DỮ LIỆU.** Ma trận nhãn
  hiện chỉ phủ ~0,53%; không kỹ thuật mô hình nào bù được nhãn quá thưa. Hướng đầu
  tư đúng cho công việc tương lai là gắn nhãn dày hơn (và đánh giá riêng kịch bản
  CV/job hoàn toàn mới — cold-start), chứ không phải thêm độ phức tạp cho encoder.
- Giá trị khoa học của mục này là **một kết quả phủ định có kiểm chứng**: đã thử các
  hướng cải tiến phổ biến (attention, sum, L2, JK, độ sâu, trọng số cạnh, DropEdge,
  học tương phản) theo đúng tài liệu và báo cáo trung thực rằng chúng không giúp —
  qua đó *biện minh cho lựa chọn kiến trúc đơn giản* của hệ thống.

> Tái lập: `backend/bench_gnn_variant.py` (resume-JD) và `backend/bench_v4_variant.py`
> (v4). Kết quả thô: `backend/results/gnn_variant/sweep3_3seed.json`,
> `.../v4_sweep_3seed.json`. Mã biến thể opt-in trong `ml_benchmark/models/gnn.py`
> (`make_model`); production không bị ảnh hưởng.
