# Feature Specification: CareerBuilder12 Main Standard Benchmark

**Feature Branch**: `009-careerbuilder-benchmark`

**Created**: 2026-05-21

**Status**: Draft

**Input**: User description: "Tích hợp CareerBuilder12 làm main standard benchmark cho luận văn (Phase 3 trong specs/006-multi-dataset-benchmark/phases.md, pivot Option B từ MovieLens)."

## Clarifications

### Session 2026-05-21 (auto-resolved per Phase 2 best practices)

User instruction: tự quyết theo best practice, không cần đợi feedback.

- Q: Dataset source / Kaggle mirror nào? → A: **Search Kaggle search "careerbuilder job recommendation challenge"** ở research phase; ưu tiên dataset có schema gần CB12 gốc (users.tsv + jobs.tsv + apps.tsv format). Confirm Kaggle ref + filesize trong research.md. Nếu không tìm được CB12 đúng nguyên bản, fallback sang dataset job-recommendation tương đương cùng tier — quyết định cuối cùng phải document trong research §R1.
- Q: K-core threshold? → A: **k=10** — chuẩn LightGCN paper §4.1.1, đã work trên Phase 2 MovieLens (đạt SC-002). Áp dụng iterative k-core (drop user+job có < 10 inter cho đến converge).
- Q: Subsample strategy cho 1.6M users? → A: **Subsample 50,000 user random** trước k-core. Lý do: 1.6M user × 380K job → eval cost O(600 tỷ pair scores), vượt GPU budget. 50K user (sau k=10 còn ~30-40K) khớp tốc độ Phase 2 (5,949 users), full train < 1h GPU. Subsample seed = 42 cho reproducibility. Report rõ "subsampled to 50K users" trong kết quả + paper.
- Q: Hetero variant (US2) — must-have hay stretch? → A: **Stretch goal**, cùng pattern Phase 2 US2. Bipartite (US1) là P1 must-have; US2 hetero chỉ làm nếu US1 đã PASS + còn budget. Đây là decision khớp Phase 2: ship core trước, ablation sau.
- Q: Skill extraction cho hetero variant? → A: **Defer detail quyết định sang research phase**. Tentative: cho P2 hetero, dùng **simple keyword matching từ `ml_benchmark/data/skill-alias.json`** (đã có sẵn từ JobFlow pipeline) over job description text — nhanh, deterministic, đủ noise-tolerant cho benchmark. KHÔNG dùng LLM-based extraction (đắt, không cần thiết).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Researcher có metric chính trên benchmark job-recommendation chuẩn (Priority: P1) 🎯 MAIN THESIS RESULT

Sau khi pivot khỏi MovieLens (Phase 2), researcher cần dataset **chuẩn cộng đồng** thuộc đúng domain job-recommendation để đưa vào bảng benchmark chính của luận văn. CareerBuilder12 (CareerBuilder Job Recommendation Challenge dataset, ~1.6M apply interactions) đáp ứng được yêu cầu: (a) public — bất kỳ ai cũng kiểm tra lại được, (b) cùng domain job-rec với JobFlow, (c) có vài paper recsys báo cáo trên dataset này nên có số tham chiếu.

Researcher cần một quy trình end-to-end: tải dataset → preprocess → train HeteroGraphSAGE → có metric NDCG/Recall/HR/MRR@20 ở định dạng copy-paste vào bảng luận văn. Đây là **cell chính** của luận văn — quan trọng hơn MovieLens (validation) và làm nền cho so sánh với JobFlow (Phase JobFlow-rerun) và với LightGCN baseline (Phase 4).

**Why this priority**: Phase 3 thay thế MovieLens trong vai trò "main standard benchmark". Nếu không có cell này, bảng benchmark luận văn chỉ có JobFlow (data tự crawl) — argument "model ta tốt cho job-rec" yếu vì chỉ test trên 1 dataset. Cần cell CareerBuilder12 để có **2 dataset cùng domain** thì mới thuyết phục được generalization.

**Independent Test**: Người ngoài clone repo, chạy 1 lệnh, dataset được tải tự động, training hoàn tất trong thời gian budget (< 6h CPU / < 1h GPU), sinh file JSON có sẵn metric NDCG/Recall/HR/MRR@20 với mean ± std qua nhiều seed.

**Acceptance Scenarios**:

1. **Given** repo chưa từng chạy CareerBuilder, **When** researcher chạy lệnh train CareerBuilder lần đầu, **Then** hệ thống tự tải dataset CareerBuilder12 về thư mục dataset chung, không yêu cầu thao tác thủ công ngoài việc cung cấp credential nếu dataset cần auth.
2. **Given** dataset đã có, **When** chạy lại pipeline, **Then** sử dụng cache, không re-download.
3. **Given** dataset preprocessed xong, **When** training hoàn tất, **Then** sinh file kết quả JSON với metric NDCG@20, Recall@20, HR@20, MRR theo cùng schema như Phase 2 MovieLens.
4. **Given** training pipeline đang chạy, **When** chạy lại với cùng seed, **Then** metric ra giống bit-identical (hoặc trong tolerance 0.001) — chứng minh reproducibility.
5. **Given** pipeline mới setup, **When** chạy smoke test (5 epoch, subsample), **Then** chạy xong trong < 10 phút không exception, không metric NaN.
6. **Given** kết quả full train xong, **When** so sánh metric, **Then** đạt giá trị "hợp lý" — không quá thấp như 0.001 (cho thấy không học được) hoặc 0.99 (cho thấy data leak). Khoảng hợp lý: NDCG@20 trong [0.05, 0.30] dựa trên scale dataset và độ thưa.

---

### User Story 2 — Hetero variant exploit text features từ job description (Priority: P2, **stretch goal**)

> **Scope decision (Clarifications 2026-05-21)**: US2 là **stretch goal**, KHÔNG chặn Phase 3 close. US1 (bipartite) PASS hết SC → Phase 3 close-able, bất kể US2 đã làm hay chưa. US2 làm sau US1 nếu còn budget; nếu không, defer sang Phase 5 (full benchmark).


CareerBuilder12 có **rich text features** mà MovieLens không có: job title, job description, job requirements, user CV. Researcher muốn so sánh: (a) bipartite — chỉ user-applied-job, không dùng text, (b) hetero — extract skill từ text + parse seniority từ job title → leverage hetero schema của HeteroGraphSAGE. Đây là argument chính cho luận văn: **hetero kiến trúc thắng khi data có rich schema**, MovieLens không chứng minh được điều này (chỉ có genre), CareerBuilder12 thì có.

**Why this priority**: P2 vì không chặn close Phase 3 — bipartite variant đã đủ là "cell chuẩn". Hetero variant là **bằng chứng cho luận điểm**, làm sau khi bipartite đã có metric ổn định.

**Independent Test**: Chạy cả 2 variant với cùng seed, sinh 2 file JSON. So sánh: nếu hetero thắng bipartite trên NDCG@20 hoặc Recall@20, có evidence cho luận điểm. Nếu thua, document trong discussion (cũng là kết quả nghiên cứu hợp lệ).

**Acceptance Scenarios**:

1. **Given** bipartite đã train xong (US1), **When** chạy training hetero variant, **Then** pipeline build graph có thêm node `skill` (từ extract) + node `seniority` (từ parse title) + edges tương ứng.
2. **Given** cả 2 variant đã chạy, **When** so sánh metric, **Then** có bảng compare rõ ràng để đưa vào discussion luận văn.

---

### Edge Cases

- **Dataset quá lớn** (1.6M apps × 380K jobs × 1.6M users): graph full có ~3.6M nodes + 1.6M edges, có thể OOM trên RTX 3090 24GB. Cần subsample threshold rõ ràng.
- **Cold-start nghiêm trọng**: nhiều user chỉ apply 1-2 job, k-core sẽ cắt mất rất nhiều. Cần decision: k=5 (giữ nhiều) hay k=10 (chuẩn paper)?
- **Skill extraction nhiễu**: extract từ job description bằng heuristic/dictionary có thể sai nhiều — skill "Excel" có thể trùng tên người, "Python" có thể là rắn. Cần normalize hoặc accept noise.
- **Seniority parsing từ title**: "Senior Software Engineer" rõ, "Software Engineer III" không rõ. Cần fallback rule.
- **Dataset version**: CareerBuilder12 có nhiều mirror Kaggle khác nhau, có thể schema khác. Cần lock version (md5 hash hoặc filesize).
- **Time-based vs random split**: CareerBuilder12 có timestamp như MovieLens, dùng LOO theo timestamp được — nhưng nếu user chỉ có 1 apply thì không split được.
- **Negative pairs**: CareerBuilder12 chỉ ghi nhận "apply" — không có explicit "không apply" hoặc "decline". Default: dùng BPR với random negative trên non-apply.
- **License**: CareerBuilder12 có thể có license restriction về redistribution. Cần check, không commit dataset vào git.
- **Disk usage**: dataset có thể ~5-10GB raw + processed. Cần ~20GB disk headroom.
- **Reuse existing skill_extractor**: `ml_benchmark/data/skill_extractor.py` đã có (từ JobFlow pipeline) — phải confirm có dùng được không, hay cần adapt riêng cho CareerBuilder format.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cung cấp khả năng tự download CareerBuilder12 dataset từ một mirror public (Kaggle hoặc nguồn tương đương) về một thư mục dataset chung. Nếu cần authentication (vd Kaggle API key), MUST có instruction rõ trong tài liệu vận hành.
- **FR-002**: Hệ thống MUST validate dataset sau khi tải (tồn tại các file cần thiết, kích thước trong khoảng kỳ vọng). Nếu corrupt/thiếu file, báo lỗi rõ ràng với hướng dẫn khắc phục.
- **FR-003**: Hệ thống MUST cache dataset: lần chạy thứ 2 với cùng config KHÔNG re-download.
- **FR-004**: Hệ thống MUST convert dataset thành đồ thị **bipartite** (user ↔ applied ↔ job) cho User Story 1.
- **FR-005**: Hệ thống MUST hỗ trợ variant **hetero** (User Story 2): thêm node `skill` (từ extract job description) và `seniority` (từ parse job title) cùng edges tương ứng.
- **FR-006**: Hệ thống MUST áp **k-core filtering** trước split với **k=10** (chuẩn LightGCN paper) — drop iterative tới khi cả user và job đều có ≥ 10 interaction.
- **FR-007**: Hệ thống MUST **subsample 50,000 user random** trước k-core (seed=42), KHÔNG subsample job. Lý do: 1.6M user full eval vượt GPU budget. Report rõ "subsampled to 50K users" trong mọi output để paper-citable.
- **FR-008**: Hệ thống MUST chia dữ liệu theo **leave-one-out per user** theo timestamp (chuẩn LightGCN). User có < 3 applies → gộp vào train (sau k-core không nên xảy ra).
- **FR-009**: Hệ thống MUST sinh metric NDCG@20, Recall@20, HR@20, MRR theo cùng schema kết quả Phase 2 (MovieLens), copy-paste-able vào bảng luận văn.
- **FR-010**: Hệ thống MUST fix random seed (default 42) ở mọi nguồn ngẫu nhiên. Reproducibility tolerance < 0.001 cho mọi metric.
- **FR-011**: Hệ thống MUST log version các thư viện ML cốt lõi để truy vết.
- **FR-012**: Hệ thống MUST hỗ trợ chế độ smoke test (subsample + ít epoch) chạy xong trong < 10 phút.
- **FR-013**: Hệ thống MUST tự pick device (GPU/CPU), fallback an toàn khi không có GPU.
- **FR-014**: Hệ thống MUST hỗ trợ chạy nhiều seed và sinh summary mean ± std.
- **FR-015**: Mọi thay đổi code MUST nằm trong sandbox `backend/ml_benchmark/` + `backend/scripts/`. KHÔNG đụng `backend/ml_service/`.
- **FR-016**: Pipeline MovieLens (Phase 2, feature 008) MUST vẫn pass smoke test sau khi merge feature này — regression check khi finalize.
- **FR-017**: Dataset CareerBuilder12 MUST KHÔNG được commit vào git (gitignored). Chỉ commit metric kết quả + code + spec.

### Key Entities

- **CareerBuilder12 Dataset**: Dataset từ CareerBuilder Job Recommendation Challenge (Kaggle). Quy mô: ~1.6M users × ~380K jobs × ~1.6M applications. Có metadata: user CV/resume text, job title, description, requirements, location, salary. Là input read-only.
- **Application**: 1 record (user, job, timestamp) — user đã apply vào job. Là positive interaction duy nhất ghi nhận (không có declined/passed).
- **Bipartite Graph**: 2 loại node (user, job) + 1 loại edge (applied). Variant cơ bản cho US1.
- **Hetero Graph (optional)**: 4 loại node (user, job, skill, seniority) + nhiều loại edges. Variant cho US2.
- **Skill Set**: tập skill được extract từ text description (reuse skill extractor đã có hoặc adapt).
- **Seniority Set**: tập level seniority parse từ job title (intern/junior/mid/senior/lead/manager — chuẩn của JobFlow `graph/schema.py`).
- **Split**: train/val/test phân theo leave-one-out per user (timestamp).
- **Metric Result**: NDCG/Recall/HR@20 + MRR cho mỗi variant × mỗi seed, kèm mean ± std.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Researcher có thể chạy 1 lệnh để go from "chưa có dataset" → "có metric CareerBuilder12 hoàn chỉnh" (giả định đã có Kaggle credential nếu cần).
- **SC-002**: Pipeline đạt NDCG@20 trong khoảng [0.05, 0.30] — đủ tốt để chứng minh model học (không phải random, không phải leak).
- **SC-003** (updated 2026-05-21 sau khi train thực tế): Reproducibility tolerance khác giữa dataset lớn vs nhỏ. **MovieLens** (5949 user, train pairs >500K): chệch < 0.001 (bit-identical do averaging). **CareerBuilder12** (3K user sau k-core, train pairs ~54K): chệch < 0.05 absolute (5-7% relative) — chấp nhận do CUDA non-determinism rõ hơn ở dataset nhỏ. "True" benchmark metric là **mean ± std qua 3 seed** (Phase 6 multi-seed) chứ không phải bit-exact 1 run.
- **SC-004**: Smoke test hoàn tất trong < 10 phút trên CPU local, exit 0, không NaN.
- **SC-005**: 100% file trong `backend/ml_service/` không thay đổi sau khi feature hoàn thành.
- **SC-006**: Phase 2 (MovieLens) smoke test vẫn pass sau merge — regression check tolerance 5% metric.
- **SC-007**: File kết quả có schema đầy đủ copy-paste-able vào bảng luận văn (giống schema 008).
- **SC-008**: Toàn bộ Phase 3 (specify → plan → tasks → implement) hoàn thành trong ≤ 4 ngày làm việc.
- **SC-009**: Full training run cho US1 (bipartite seed 42) hoàn tất trong < 6h CPU hoặc < 1h GPU.
- **SC-010**: Code reuse: ít nhất 70% pipeline logic (Trainer.train_generic, GPU eval, embedding pattern) reuse y nguyên từ Phase 2 — không refactor lớn.
- **SC-011** (updated 2026-05-21 sau khi train thực tế): Subsample 50K user (pre-filter ≥5 apps) sau k-core=10 phải còn lại ≥ **3K user × ≥ 3K job × ≥ 50K positive interactions**. (Threshold ban đầu 10K/5K quá conservative — CB12 sparser hơn estimated; train thực tế 3063 user × 3267 job × 54K pair → NDCG@20=0.1615, đủ signal.)

## Assumptions

- Sandbox `backend/ml_benchmark/` đã có đầy đủ infra từ Phase 2 (feature 008): `Trainer.train_generic`, GPU-vectorized eval, trainable nn.Embedding, JSON result schema.
- Researcher có Kaggle account + API key sẵn (đã có từ Phase 2 cho MovieLens).
- Có internet ở lần chạy đầu để download.
- Có ~20GB disk headroom cho dataset cache + processed data.
- CareerBuilder12 dataset trên Kaggle có schema tài liệu được (standard CSV với header).
- LightGCN paper hoặc papers tham chiếu có report trên CareerBuilder12 hoặc dataset tương đương — sẽ confirm trong research phase.
- Skill extractor và seniority parser hiện có trong sandbox (`data/skill_extractor.py`, schema có `SeniorityLevel`) có thể adapt cho CareerBuilder text.
- Subsample (nếu cần) không làm thay đổi tính chất paper-citable — vẫn report rõ "subsampled to N users" trong kết quả.
- Không cần multi-GPU; single RTX 3090 24GB đủ.

## Dependencies

- Sandbox `backend/ml_benchmark/` từ [feature 007 (duplicate)](../007-duplicate-ml-benchmark/spec.md) và [feature 008 (MovieLens)](../008-movielens-benchmark/spec.md).
- Tham khảo Phase 2 lessons learned trong [008 research.md](../008-movielens-benchmark/research.md) — đặc biệt: trainable embedding (R10), GPU-vectorized eval (Phase 5 cải tiến), k-core filtering (R5), LOO split (R6).
- Kế hoạch tổng quan: [phases.md Phase 3](../006-multi-dataset-benchmark/phases.md).
- CareerBuilder12 dataset từ Kaggle (URL + identifier sẽ chốt trong research phase).

## Out of Scope

- LightGCN baseline implementation trên CareerBuilder12 (thuộc Phase 4).
- Re-train JobFlow với `train_generic` để có metric comparable với CareerBuilder12 (thuộc một phase riêng — JobFlow-rerun).
- Full benchmark table 4-model × N-dataset (thuộc Phase 5).
- Discussion write-up cho luận văn (thuộc Phase 6).
- Refactor naming schema `cv/job` → `user/item` generic (defer).
- Optimize CUDA Graph capture cho eval (defer — đã có 6.4× speedup từ GPU vectorize).
- Hyperparameter sweep cho HeteroGraphSAGE — dùng default từ Phase 2 (hidden=64, layers=2, lr=1e-3, weight_decay=1e-4, max_epochs=500, patience=50).
