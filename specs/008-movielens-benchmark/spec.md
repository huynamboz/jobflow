# Feature Specification: MovieLens-1M Benchmark Integration

**Feature Branch**: `008-movielens-benchmark`

**Created**: 2026-05-21

**Status**: Draft

**Input**: User description: "Tích hợp MovieLens-1M làm dataset benchmark thứ hai cho ml_benchmark sandbox (Phase 2 trong specs/006-multi-dataset-benchmark/phases.md)."

## Clarifications

### Session 2026-05-21

- Q: Preprocessing — có áp k-core filtering kiểu LightGCN paper không? → A: **k-core = 10** (drop mọi user và movie có < 10 tương tác trước khi split). Lý do: chuẩn LightGCN/NGCF/PinSage paper (§4.1.1 của LightGCN, He et al. SIGIR 2020) — bắt buộc nếu muốn metric của ta nằm trong cùng order of magnitude với paper (SC-002).
- Q: Full training budget — bao nhiêu epoch tối đa, có early stopping không? → A: **max 500 epoch, early stopping patience = 50 epoch trên val NDCG@20**. Lý do: paper dùng tới 1000 epoch nhưng converge thực tế ở 200-500; ràng buộc 500 vừa đủ converge, vừa giữ thời gian train trên CPU local trong ngưỡng vài giờ.
- Q: Hetero variant (US2 với node genre) — must-have cho Phase 2 hay stretch goal? → A: **Stretch goal**. Phase 2 có thể ship khi chỉ hoàn thành US1 (bipartite); US2 hetero variant đưa lên trước khi sang Phase 3 nếu thời gian cho phép, nhưng không chặn Phase 2 close.
- Q: Train kiến trúc model nào trên MovieLens? → A: **HeteroGraphSAGE only** (cùng kiến trúc đã dùng cho JobFlow, được generalize cho metadata động). R-GCN defer sang phase sau — trên bipartite R-GCN suy biến về GCN, không thêm insight đủ đáng cho thời gian Phase 2.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Researcher train được model trên MovieLens-1M và lấy được metric (Priority: P1) 🎯 MVP

Nhà nghiên cứu (thesis author) cần dùng MovieLens-1M — bộ dữ liệu chuẩn được mọi paper GNN-recsys báo cáo số — để chứng minh rằng kiến trúc model của họ chạy được trên benchmark chính thống, không chỉ data nhà tự sinh. Họ cần một quy trình end-to-end: tải dataset → convert sang đồ thị → train → có metric (NDCG@20, Recall@20, HR@20, MRR) ở định dạng so sánh được trực tiếp với LightGCN paper. Output cuối cùng là một file kết quả có thể đưa nguyên vào bảng so sánh trong luận văn.

**Why this priority**: Đây là deliverable chính của Phase 2. Không có metric MovieLens, bảng benchmark trong luận văn sẽ thiếu một cột quan trọng. Phải hoàn thành trước khi làm CareerBuilder hoặc LightGCN baseline.

**Independent Test**: Một người mới (không phải author) clone repo, checkout branch, chạy đúng 1 lệnh từ tài liệu hướng dẫn → thấy script tự tải MovieLens-1M (nếu chưa có), train xong, in metric ra console và ghi vào file kết quả. Người này không cần biết về model hay graph để chạy được.

**Acceptance Scenarios**:

1. **Given** repo chưa từng chạy MovieLens, **When** researcher chạy lệnh train MovieLens lần đầu, **Then** hệ thống tự tải dataset MovieLens-1M về một thư mục dataset chung, không yêu cầu thao tác thủ công.
2. **Given** dataset MovieLens-1M đã tải về, **When** researcher chạy lại lệnh train, **Then** hệ thống KHÔNG tải lại — dùng cache.
3. **Given** dataset đã sẵn sàng, **When** training pipeline chạy đến hết, **Then** xuất hiện một file kết quả chứa metric NDCG@20, Recall@20, HR@20, MRR với mean ± std (nếu chạy nhiều seed) — sẵn sàng đưa vào bảng luận văn.
4. **Given** metric đã được sinh ra, **When** so sánh với LightGCN paper (Recall@20 ≈ 0.26, NDCG@20 ≈ 0.22), **Then** metric của ta nằm trong cùng order of magnitude (vd Recall@20 trong khoảng [0.10, 0.40], NDCG@20 trong khoảng [0.10, 0.35]) — chứng minh pipeline hoạt động đúng, không sai lệch nghiêm trọng.
5. **Given** training pipeline đang chạy, **When** researcher chạy lại pipeline lần thứ hai với cùng seed, **Then** metric ra giống nhau bit-exact (hoặc ít nhất trong khoảng noise < 0.001) — chứng minh reproducibility.
6. **Given** pipeline mới setup chưa qua test thật, **When** researcher chạy chế độ smoke test (5 epoch), **Then** pipeline chạy xong trong < 10 phút trên máy local CPU không exception — đảm bảo "code không gãy" trước khi train full.

---

### User Story 2 — Hetero variant với genre để khảo sát lợi thế của heterogeneous GNN (Priority: P2, **stretch goal**)

> **Scope decision (Clarifications 2026-05-21)**: US2 là **stretch goal**, KHÔNG chặn Phase 2 close. Nếu US1 (bipartite) đã pass tất cả SC và còn ngân sách thời gian, làm tiếp US2 trước khi sang Phase 3 (CareerBuilder). Nếu hết thời gian, defer US2 sang sau.


Researcher muốn chứng minh trong luận văn rằng kiến trúc heterogeneous GNN (có nhiều loại node + edge) cho kết quả tốt hơn bipartite GNN (chỉ user-item) — nhưng để chứng minh được điều này trên MovieLens, cần thêm node `genre` (vì MovieLens không có skill/seniority như JobFlow). Họ cần một biến thể hetero của loader/training để so sánh trực tiếp metric bipartite vs hetero trên cùng một dataset.

**Why this priority**: Hỗ trợ một luận điểm phụ trong luận văn ("hetero GNN có lợi thế ngay cả với metadata đơn giản như genre"). Có giá trị nhưng không chặn các phase sau — kể cả khi không có biến thể hetero, vẫn có thể nộp luận văn với một bảng đầy đủ. Vì vậy P2.

**Independent Test**: Researcher chạy hai lệnh: một cho bipartite, một cho hetero variant. Cả hai chạy thành công và sinh ra metric riêng. So sánh metric: nếu hetero ≥ bipartite trên ít nhất một metric, có dữ liệu để hỗ trợ luận điểm; nếu thấp hơn, vẫn document được "trên dataset này hetero không lợi thế" — cũng là kết quả nghiên cứu hợp lệ.

**Acceptance Scenarios**:

1. **Given** dataset MovieLens-1M đã có, **When** researcher chạy training với flag chọn variant hetero, **Then** pipeline build đồ thị có thêm node `genre` và edge `has_genre` (movie → genre), train xong và sinh metric riêng cho variant hetero.
2. **Given** cả hai variant đã chạy xong, **When** xem file kết quả, **Then** có hai entry rõ ràng (bipartite vs hetero) để dễ so sánh.

---

### Edge Cases

- **Hardcoded node dimensions trong model**: Kiến trúc model hiện tại fix node dim cho đúng schema CV–Job–Skill–Seniority. Với MovieLens (user, movie, optional genre — dim khác hoàn toàn), model phải chấp nhận metadata động. Nếu không xử lý, code sẽ crash ở runtime.
- **MovieLens không có rich features**: User/movie chỉ có id, không có text/embedding sẵn. Cần khởi tạo node feature dạng learnable embedding — researcher không phải tự lo về việc model "không có x để encode".
- **Disk space cho cache**: MovieLens-1M nén ~5MB, giải nén ~25MB. Phải fail rõ nếu disk không đủ thay vì silent corrupt.
- **Network khi download**: Lần đầu chạy cần internet. Nếu mạng đứt giữa chừng, lần sau chạy lại phải biết file tải dở là invalid và tải lại — không dùng file corrupt.
- **Split per user**: Chuẩn LightGCN dùng leave-one-out per user. User có ít hơn 3 tương tác không thể chia train/val/test → cần lọc bỏ hoặc gộp vào train.
- **Cold-start trong evaluation**: Khi đánh giá ở test, có thể có movie mới (chưa từng xuất hiện trong train) → model không có embedding cho nó. Cần xử lý nhất quán (skip hoặc dùng zero embedding).
- **Random seed drift**: Nếu shuffle dùng generator khác nhau giữa lần chạy, metric sẽ khác bất chấp seed cố định. Phải kiểm tra reproducibility.
- **Smoke test fail giả**: Nếu smoke test 5 epoch nhưng dataset quá lớn → có thể quá 10 phút. Cần subsample hoặc giảm batch size cho smoke test riêng để không nhầm "code lỗi" với "thiết lập quá nặng".
- **GPU vs CPU device mismatch**: Sandbox hiện chạy CPU on macOS. Trên máy GPU, code phải tự pick CUDA mà không cần researcher sửa.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cung cấp khả năng tự download MovieLens-1M (file ml-1m.zip) về một thư mục dataset chung khi chưa có; nếu file đã tồn tại và checksum/size hợp lệ, MUST KHÔNG tải lại.
- **FR-002**: Hệ thống MUST validate dataset đã tải (tồn tại các file `ratings.dat`, `movies.dat`, `users.dat`) trước khi bắt đầu pipeline; nếu thiếu hoặc corrupt, MUST báo lỗi rõ ràng kèm hướng dẫn khắc phục.
- **FR-003**: Hệ thống MUST convert ratings của MovieLens thành đồ thị bipartite (user ↔ rated ↔ movie), với rating ≥ 4 được coi là positive interaction (chuẩn LightGCN paper).
- **FR-004**: Hệ thống MUST hỗ trợ biến thể hetero (optional) thêm node `genre` và edge `has_genre` cho movie, để researcher có thể so sánh bipartite vs hetero.
- **FR-005**: Hệ thống MUST áp **k-core filtering với threshold = 10** (drop mọi user và movie có < 10 tương tác sau khi đã lọc rating ≥ 4) TRƯỚC khi split — chuẩn LightGCN paper. Sau filter, MUST chia dữ liệu theo chiến lược leave-one-out per user: với mỗi user, tương tác mới nhất → test, tương tác trước cuối → val, còn lại → train. (Sau k-core = 10, mọi user còn lại đều có ≥ 10 tương tác nên ≥ 3 luôn thoả mãn cho split.)
- **FR-006**: Hệ thống MUST khởi tạo node feature dạng learnable embedding cho user và movie (không có rich features sẵn) — researcher không cần tự cung cấp embedding.
- **FR-007**: Hệ thống MUST chấp nhận node feature dimension động cho mọi loại node — kiến trúc model KHÔNG được hardcode dim cho schema CV/Job/Skill/Seniority cũ.
- **FR-007a**: Kiến trúc model dùng cho MovieLens là **HeteroGraphSAGE** (kế thừa từ JobFlow, được generalize ở FR-007). R-GCN KHÔNG nằm trong phạm vi Phase 2 (defer sang phase sau hoặc phase mở rộng nếu cần) — vì trên đồ thị bipartite, R-GCN suy biến về GCN, không thêm insight.
- **FR-008**: Hệ thống MUST hỗ trợ negative sampling 1 random negative per positive cho training (BPR loss convention).
- **FR-009**: Hệ thống MUST fix random seed (default 42) ở mọi nguồn ngẫu nhiên (numpy, torch, dataloader) — chạy lại cùng seed phải cho cùng kết quả.
- **FR-010**: Hệ thống MUST log version của các thư viện ML cốt lõi (PyTorch, PyG) trong output để truy vết reproducibility.
- **FR-011**: Hệ thống MUST hỗ trợ chế độ smoke test (vd train chỉ 5 epoch) để verify pipeline trước khi train full — chạy xong trong < 10 phút trên CPU local.
- **FR-011a**: Full training MUST có ràng buộc `max_epochs = 500` và `early_stopping_patience = 50` (theo dõi val NDCG@20). Mục tiêu: model converge trong vài giờ trên CPU local, không yêu cầu GPU bắt buộc.
- **FR-012**: Hệ thống MUST sinh ra metric NDCG@20, Recall@20, HR@20, MRR ở định dạng có thể đưa nguyên vào bảng luận văn (file kết quả + console output).
- **FR-013**: Hệ thống MUST hỗ trợ chạy nhiều seed (vd 3 seed) và báo mean ± std cho mỗi metric — chuẩn paper.
- **FR-014**: Hệ thống MUST tự pick device (CUDA nếu có, fallback CPU) mà không cần researcher chỉnh code.
- **FR-015**: Mọi thay đổi code MUST nằm trong sandbox `backend/ml_benchmark/` và `backend/scripts/`; KHÔNG được thay đổi file nào trong `backend/ml_service/` (production).
- **FR-016**: Nếu generalize model làm thay đổi behavior cho dataset JobFlow cũ, hệ thống MUST đảm bảo smoke test JobFlow (feature 007) vẫn pass trong khoảng noise (regression check).

### Key Entities

- **MovieLens Dataset**: Bộ dữ liệu chuẩn từ GroupLens (Univ. Minnesota). Quy mô: ~6,000 users × ~3,700 movies × ~1M ratings. Mỗi rating có user_id, movie_id, rating (1–5), timestamp. Có metadata phụ: genres (per movie), gender/age/occupation (per user — không dùng trong scope này). Là input read-only.
- **Interaction**: Một tương tác user–movie. Trong scope này: chỉ coi positive khi rating ≥ 4; rating thấp hơn bị bỏ qua (chuẩn LightGCN).
- **Bipartite Graph**: Đồ thị 2 loại node (user, movie) + 1 loại edge (rated). Dùng làm variant cơ bản.
- **Hetero Graph (optional)**: Đồ thị 3 loại node (user, movie, genre) + 2 loại edge (rated, has_genre). Dùng làm variant nâng cao.
- **Split**: Phân chia dữ liệu thành train/val/test theo leave-one-out per user.
- **Metric Result**: Tập hợp NDCG@20, Recall@20, HR@20, MRR cho từng variant × từng seed, kèm mean ± std.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Researcher có thể chạy đúng 1 lệnh (đã được document) để go from "chưa có dataset" → "có metric MovieLens hoàn chỉnh" mà không cần thao tác thủ công nào ngoài lệnh đó.
- **SC-002**: Pipeline đạt được metric trên MovieLens-1M trong cùng order of magnitude với LightGCN paper: Recall@20 trong khoảng [0.10, 0.40], NDCG@20 trong khoảng [0.10, 0.35]. (Không yêu cầu khớp đúng; chỉ cần không lệch >10×).
- **SC-003**: Chạy pipeline 2 lần với cùng seed cho metric bit-identical (sai số < 0.001 cho mọi metric) — chứng minh reproducibility.
- **SC-004**: Smoke test (5 epoch) hoàn tất trong < 10 phút trên máy CPU dev local (Apple Silicon), exit code 0, không exception, không có metric NaN.
- **SC-005**: Sau khi feature hoàn thành, 100% file trong `backend/ml_service/` không bị thay đổi (`git diff backend/ml_service/` rỗng cho mọi commit của feature này).
- **SC-006**: Smoke test của feature 007 (training JobFlow trong sandbox) vẫn pass sau khi generalize model — metric chệch < 5% so với baseline đã ghi nhận ở feature 007 (NDCG@10 = 0.9266).
- **SC-007**: File kết quả sinh ra có cấu trúc đủ để copy-paste trực tiếp vào bảng luận văn (mỗi row = 1 cấu hình, mỗi cell = mean ± std).
- **SC-008**: Toàn bộ Phase 2 (specify → plan → tasks → implement) hoàn thành trong ≤ 3 ngày làm việc, khớp budget trong [phases.md](../006-multi-dataset-benchmark/phases.md). Phase 2 được coi là "close-able" khi US1 PASS toàn bộ SC-001..SC-007, kể cả khi US2 (hetero variant) chưa làm.
- **SC-009**: Full training run cho US1 (HeteroGraphSAGE trên bipartite MovieLens-1M) hoàn tất (early-stopped hoặc đạt max 500 epoch) trong < 6 giờ trên CPU local hoặc < 1 giờ trên GPU thông thường — đảm bảo có thể chạy benchmark nhiều lần trong budget Phase 2.

## Assumptions

- Sandbox `backend/ml_benchmark/` đã sẵn sàng (feature 007 đã merge, kiến trúc model đã import được, training pipeline đã chạy được trên JobFlow).
- Researcher có internet ở lần chạy đầu tiên để download MovieLens-1M (~5 MB).
- Có đủ disk space (~30 MB) để cache dataset.
- Máy local có CPU đủ mạnh để train MovieLens-1M trong thời gian chấp nhận được (vài giờ cho 100 epoch), hoặc có GPU để tăng tốc.
- LightGCN paper là baseline tham chiếu chính (paper SIGIR 2020 của He et al.); các số cited (Recall@20 ≈ 0.26, NDCG@20 ≈ 0.22) là từ Table 2 của paper đó.
- Trong scope này không cần implement chính LightGCN — chỉ cần model của researcher chạy được; so sánh LightGCN sẽ ở Phase 4.
- Genre metadata trong MovieLens dùng dạng pipe-separated string (vd "Action|Adventure|Sci-Fi"). Cần split để thành multi-label.
- Không cần multi-GPU / distributed training — single-device là đủ cho MovieLens-1M.
- Format dataset MovieLens-1M ổn định (GroupLens không thay đổi structure file kể từ 2003); không cần xử lý nhiều version.

## Dependencies

- Sandbox `backend/ml_benchmark/` từ [feature 007](../007-duplicate-ml-benchmark/spec.md). Đặc biệt phụ thuộc:
  - Trainer, BPR loss, metric computation đã có sẵn.
  - Kiến trúc HeteroGraphSAGE / R-GCN — sẽ được generalize trong feature này (out-of-spec cho 007).
- Kế hoạch tổng quan: [phases.md Phase 2](../006-multi-dataset-benchmark/phases.md).
- LightGCN paper (He et al., SIGIR 2020) làm reference baseline numbers.
- MovieLens-1M dataset từ GroupLens (URL: https://files.grouplens.org/datasets/movielens/ml-1m.zip) — public, free for research.

## Out of Scope

- Implement LightGCN baseline để so sánh thực tế (thuộc Phase 4).
- Generalize R-GCN cho metadata động hoặc train R-GCN trên MovieLens (defer — không cần thiết vì trên bipartite R-GCN ≈ GCN).
- Tích hợp CareerBuilder12 dataset (thuộc Phase 3).
- Bảng benchmark đầy đủ 4 model × 3 dataset (thuộc Phase 5).
- Refactor toàn bộ schema graph từ `cv/job/skill` sang `user/item` chung — không bắt buộc cho Phase 2; có thể giữ tên cũ trong code và chỉ thêm node type mới.
- Viết phần discussion luận văn (thuộc Phase 6).
- Sửa bug trong production `backend/ml_service/`.
- Inference / serving model đã train (chỉ train + evaluate, không serve).
- UI / dashboard hiển thị metric.
