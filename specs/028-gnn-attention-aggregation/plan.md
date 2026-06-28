# Plan: Cải tiến tổng hợp bằng Attention cho HeteroGraphSAGE (sandbox)

## Mục tiêu
Kiểm chứng giả thuyết: **thay hàm tổng hợp mean bằng attention (GAT/GATv2)** trong bộ mã hóa HeteroGraphSAGE có **tăng hiệu suất** trên bài toán so khớp hay không — để có một "cải tiến kiến trúc" thật, có ablation, đúng hướng các paper (GAT/HGT/Simple-HGN).

Lý do: HeteroGraphSAGE hiện dùng `to_hetero(GraphSAGE, aggr="mean")` — mean aggregator coi mọi lân cận như nhau, **bỏ qua** việc một số kỹ năng/quan hệ quan trọng hơn. Attention học trọng số từng lân cận.

## Ràng buộc (BẮT BUỘC)
- **KHÔNG đụng production** (`ml_service/`), KHÔNG sửa checkpoint, KHÔNG đổi model mặc định.
- **KHÔNG ghi đè** kết quả/bảng hiện có. Mọi kết quả mới ghi ra **file mới** trong `results/gnn_variant/`.
- Cải tiến chỉ là **opt-in** trong sandbox (`ml_benchmark`): thêm `model_type="gat"`, mặc định vẫn `graphsage`.
- Tất cả thay đổi đều **additive** (thêm class/flag/script mới), rollback bằng cách bỏ flag.

## Thiết kế
1. **Thêm class `HeteroGAT`** vào `ml_benchmark/models/gnn.py` (song song `HeteroGraphSAGE`):
   - Giữ nguyên: chiếu tuyến tính theo loại nút + `MLPDecoder`.
   - Backbone: PyG `GAT(v2=True, heads=4)` bọc `to_hetero` → attention TRONG từng loại cạnh; tổng hợp giữa các loại cạnh vẫn mean.
2. **Thêm `model_type == "gat"`** vào `ml_benchmark/training/trainer.py` (nhánh tạo model). Mặc định `"graphsage"` GIỮ NGUYÊN.
3. **Script so sánh mới** `bench_gnn_variant.py`:
   - Dùng đúng dữ liệu + giao thức warm-start resume-JD (như benchmark đã verify).
   - Với mỗi `model_type ∈ {graphsage, gat}` × 3 hạt giống (42/123/2024): train GNN có content features, eval full-space NDCG/Recall/MRR.
   - Ghi `results/gnn_variant/compare_3seed.json` + bảng.

## Tiêu chí thành công
- `gat` có NDCG@20 trung bình **cao hơn** `graphsage` vượt ngoài độ lệch chuẩn → cải tiến có hiệu lực.
- Nếu KHÔNG cao hơn: báo cáo trung thực "attention không giúp trên bộ này" (vẫn là kết quả khoa học hợp lệ, không ép).

## Các bước
1. Viết plan (file này). ✅
2. Implement `HeteroGAT` + nhánh `model_type="gat"` trong trainer.
3. Smoke test cục bộ (1 seed, smoke) để chắc chạy được, không lỗi chiều.
4. Chạy server: graphsage (baseline) + gat, 3 seed, lưu file mới.
5. Tổng hợp + so sánh + kết luận trung thực.

## Rollback
Bỏ flag `--model-type gat` → quay về hành vi cũ. Production không bị ảnh hưởng ở mọi bước.
