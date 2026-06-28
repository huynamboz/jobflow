# Research: còn cải tiến gì được cho HeteroGraphSAGE?

## 1. Chẩn đoán — "headroom" nằm ở đâu?
Từ thực nghiệm đã chạy (sandbox, không đụng production):

| Bối cảnh | Hiệu năng | Còn dư địa? |
|---|---|---|
| resume-JD warm-start (dày) | R@20 ≈ 0,93, NDCG@20 ≈ 0,50 | **Gần bão hòa** → tweak kiến trúc KHÔNG giúp (đã chứng minh: attention/JK/L2/sum/depth đều trong nhiễu; 3 lớp còn HẠI do over-smoothing) |
| v4 nội bộ, xếp toàn kho 6.251 | NDCG@20 ≈ 0,05; **bare GNN decode AUC = 0,46** (dưới ngẫu nhiên) | **Còn nhiều dư địa** — đây mới là chỗ yếu thật |
| Cold-start (CV mới hoàn toàn) | chưa đo | Khoảng trống lớn nhất |

→ **Nút thắt KHÔNG ở kiến trúc encoder trên dữ liệu dày, mà ở (a) bài toán so khớp khó/thưa, (b) bare GNN yếu, (c) cold-start.**

## 2. Phát hiện then chốt: có TÍN HIỆU đang bỏ phí
Điều tra mã nguồn cho thấy 3 nguồn tín hiệu **đã có sẵn nhưng GNN KHÔNG dùng**:

### (A) Trọng số cạnh (importance / proficiency) — BỎ PHÍ
- `builder.py` đã gắn `edge_attr`: cạnh `requires_skill` mang **mức quan trọng kỹ năng (1–5)**, cạnh `has_skill` mang **mức thành thạo**.
- Nhưng SAGEConv/GAT đang **mean/attention KHÔNG dùng edge_attr** → coi mọi kỹ năng như nhau. Một job "yêu cầu Python (mức 5)" và "biết Git (mức 1)" được lan truyền ngang nhau — sai trực giác.
- **Cơ hội rõ nhất, dữ liệu có sẵn.**

### (B) Nhãn đa trục (5 trục) — chỉ reranker dùng, GNN KHÔNG
- Nhãn có 5 trục: skill_fit / seniority_fit / experience_fit / domain_fit / overall (thang 0–2).
- GNN encoder chỉ train bằng **BPR nhị phân** (`bpr_loss`); 4 trục phụ chỉ nuôi reranker.
- → GNN bỏ lỡ tín hiệu giám sát giàu.

### (C) Học tương phản (contrastive) — CHƯA có
- `grep` không thấy InfoNCE/SimGCL/SGL. Đây là kỹ thuật mạnh nhất gần đây cho GNN gợi ý.

## 3. Các hướng cải tiến CÓ CƠ SỞ (ưu tiên theo khả thi × tác động)

| # | Hướng | Cơ sở (paper) | Khả thi | Kỳ vọng |
|---|---|---|---|---|
| **1** | **Tổng hợp có trọng số cạnh** (dùng importance/proficiency) | MPNN (Gilmer 2017), ECC (Simonovsky 2017), GATv2 với `edge_dim` (Brody 2021) | **CAO** (data có sẵn, đổi conv) | Giúp ở so khớp khó: "kỹ năng nào QUAN TRỌNG" |
| **2** | **Học tương phản đồ thị** (SimGCL/SGL) | SGL (Wu 2021, SIGIR), **SimGCL** (Yu 2022, SIGIR — chỉ thêm nhiễu vào embedding, đơn giản mà mạnh) | TRUNG BÌNH | Cải thiện chất lượng biểu diễn, đặc biệt nút thưa |
| **3** | **Giám sát đa nhiệm cho GNN** (dự đoán 5 trục, không chỉ BPR nhị phân) | Multi-task GNN; UniMP (Shi 2020) | TRUNG BÌNH | Embedding giàu hơn, ít overfit nhị phân |
| **4** | **Cold-start nội dung** (đánh giá + cải thiện cho CV/job mới) | Heater (Zhu 2020), content-aware inductive | TRUNG BÌNH | Đúng khoảng trống sản phẩm |
| **5** | Hard-negative tốt hơn / loss tương phản có giám sát | PinSage (Ying 2018, đã có curriculum), SupCon | THẤP | Đã làm một phần |

## 4. Kết luận trung thực
- **Tweak kiến trúc thuần (attention/depth/aggr) đã cạn** trên dữ liệu hiện có — đã kiểm chứng.
- **Còn 3 nguồn tín hiệu bỏ phí**: edge weights, nhãn 5 trục, contrastive. Đây mới là chỗ "cải tiến có cơ sở".
- **Lực bẩy lớn nhất thực ra là DỮ LIỆU** (nhiều nhãn hơn, dày hơn — hiện chỉ 0,53% ma trận được gán nhãn). Không kỹ thuật nào bù được nhãn quá thưa.

## 5. Khuyến nghị triển khai
**Thử #1 trước (Tổng hợp có trọng số cạnh)** vì: dữ liệu đã có (importance/proficiency), thay đổi gọn (đổi conv sang loại nhận edge_attr, ví dụ `GATv2Conv(edge_dim=1)` hoặc `NNConv`), và đo được trên **bộ v4** (nơi importance tồn tại + còn dư địa). Nếu có hiệu lực → đây là cải tiến kiến trúc THẬT, có ablation, đúng hướng paper.

Đo trên bộ có dư địa (v4 sampled / cold-start), KHÔNG đo trên resume-JD warm (đã bão hòa).
