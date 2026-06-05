# Feature Specification: Duplicate ML Service for Benchmark

**Feature Branch**: `007-duplicate-ml-benchmark`

**Created**: 2026-05-21

**Status**: Draft

**Input**: User description: "Duplicate backend/ml_service/ thành backend/ml_benchmark/ để dùng cho việc benchmark multi-dataset (MovieLens-1M, CareerBuilder12, JobFlow) mà không ảnh hưởng đến production code."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Researcher có sandbox để benchmark mà không phá production (Priority: P1)

Nhà nghiên cứu (thesis author) cần một bản sao độc lập của ML service để tự do refactor, thêm dataset mới, đổi schema graph, mà tuyệt đối không gây rủi ro cho hệ thống production đang chạy ổn định (verifier, scheduler, admin dashboard). Sau khi duplicate, họ có thể chạy lại training pipeline gốc trên dataset JobFlow hiện tại trong sandbox mới và thấy kết quả tương đương production — chứng minh rằng bản copy là một baseline đáng tin cậy để bắt đầu mở rộng.

**Why this priority**: Đây là điều kiện tiên quyết của toàn bộ benchmark suite. Nếu không có sandbox tách biệt, mọi thay đổi tiếp theo (thêm MovieLens, CareerBuilder, LightGCN) đều có nguy cơ làm hỏng production. Không có P1 thì các phase sau không thể bắt đầu.

**Independent Test**: Sau khi duplicate xong, chạy training pipeline trên dataset JobFlow trong sandbox (`backend/ml_benchmark/`). So sánh các metric (NDCG@10, Recall@10, AUC) với baseline production gần nhất — sai số phải nằm trong khoảng noise của random seed (~±1%). Đồng thời chạy lại các test/CLI của production (`backend/ml_service/`) để xác nhận không có gì bị ảnh hưởng.

**Acceptance Scenarios**:

1. **Given** kho code có `backend/ml_service/` đang chạy production, **When** thực thi quy trình duplicate, **Then** xuất hiện thư mục mới `backend/ml_benchmark/` chứa các module cốt lõi (graph, models, training, evaluation, baselines, data, embedding, config, utils) và `backend/ml_service/` vẫn nguyên vẹn từng byte.
2. **Given** sandbox `backend/ml_benchmark/` đã được tạo, **When** nhà nghiên cứu chạy lại training pipeline trên dataset JobFlow trong sandbox, **Then** pipeline chạy thành công không lỗi import và sinh ra checkpoint trong thư mục checkpoint riêng của benchmark (không ghi đè checkpoint production).
3. **Given** sandbox và production cùng tồn tại, **When** import cả hai trong cùng một Python session, **Then** không xảy ra xung đột module/namespace, hai service hoạt động độc lập.
4. **Given** sandbox đã sẵn sàng, **When** nhà nghiên cứu xem các module production-only như `verifier/`, `crawler/`, `cv_parser/`, `inference/`, `reranker/`, `api/` trong sandbox, **Then** các module này không tồn tại — sandbox chỉ chứa phần cần cho benchmark.

---

### User Story 2 — Sandbox không nhiễm bẩn lịch sử git của production (Priority: P2)

Người maintain code (kể cả người khác trong nhóm) cần phân biệt rõ ràng giữa "code production" và "code benchmark cho thesis" qua lịch sử git. Khi xem log, một commit duy nhất giới thiệu sandbox phải dễ nhận diện, và các commit tiếp theo trong sandbox không bị lẫn vào diff của production module.

**Why this priority**: Giúp việc review, rollback, và sau khi nộp luận văn có thể xóa toàn bộ sandbox bằng một commit revert duy nhất. Quan trọng nhưng không chặn việc benchmark — vì vậy P2.

**Independent Test**: Chạy `git log --oneline backend/ml_benchmark/` thấy commit khởi tạo có message rõ ràng nhận diện được mục đích (vd: "chore: duplicate ml_service → ml_benchmark for thesis benchmarking"). Chạy `git log -- backend/ml_service/` không thấy commit nào của benchmark xen vào.

**Acceptance Scenarios**:

1. **Given** sandbox vừa được tạo, **When** commit thay đổi, **Then** xuất hiện đúng 1 commit duy nhất với message mô tả rõ mục đích duplicate.
2. **Given** sandbox đã commit, **When** xem `git log -- backend/ml_service/`, **Then** không thấy commit của benchmark xen vào lịch sử production.

---

### Edge Cases

- **Import xung đột**: Nếu một module trong sandbox vẫn import bằng path `ml_service.X` (do bỏ sót), việc load đồng thời sẽ load nhầm code production. Cần phát hiện trước khi commit.
- **Checkpoint ghi đè**: Nếu cấu hình mặc định của trainer trong sandbox vẫn trỏ tới `backend/checkpoints/` (path production), một lần training trong sandbox có thể ghi đè checkpoint đang được production dùng. Cần đảm bảo path đã được tách.
- **Phụ thuộc ngầm vào module đã xóa**: Nếu một module được giữ lại (vd `training/`) ngầm import từ module bị xóa (vd `inference/`), sandbox sẽ lỗi runtime. Phải dò trước.
- **Skill alias / data file path**: File JSON/YAML chứa đường dẫn tương đối tới `ml_service/` sẽ trỏ sai sau khi copy. Phải rà soát.
- **Cache `__pycache__` cũ**: Bản copy mang theo `__pycache__/` với bytecode trỏ đường dẫn cũ → có thể gây nhầm lẫn khi debug. Phải dọn.
- **Test fixtures dùng chung**: Nếu sandbox và production cùng đọc/ghi vào cùng thư mục `data/processed/`, hai bên có thể đụng nhau. Cần xác định chính sách chia sẻ dữ liệu input (read-only) vs output (tách hoàn toàn).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST tạo ra một thư mục sandbox mới (`backend/ml_benchmark/`) chứa bản sao đầy đủ của các module cốt lõi từ production ML service: `graph/`, `models/`, `training/`, `evaluation/`, `baselines/`, `data/`, `embedding/`, `config/`, `utils/`, kèm theo `__init__.py` ở thư mục gốc.
- **FR-002**: Hệ thống MUST loại bỏ các module không liên quan tới benchmark khỏi sandbox: `verifier/`, `crawler/`, `cv_parser/`, `inference/`, `reranker/`, `api/`.
- **FR-003**: Hệ thống MUST đổi mọi import internal trong sandbox từ namespace `ml_service.*` sang `ml_benchmark.*`, đảm bảo không còn tham chiếu chéo về production.
- **FR-004**: Hệ thống MUST không thay đổi bất kỳ file nào trong `backend/ml_service/` — production phải nguyên vẹn từng byte có ý nghĩa.
- **FR-005**: Hệ thống MUST cấu hình sandbox để mọi đầu ra train (checkpoint, log, artifact) được ghi vào thư mục tách biệt khỏi production (vd `backend/checkpoints_benchmark/` thay vì `backend/checkpoints/`).
- **FR-006**: Sandbox MUST chạy lại được training pipeline trên dataset JobFlow hiện tại mà không lỗi import, không cần sửa cấu hình ngoài việc trỏ tới sandbox.
- **FR-007**: Sandbox và production MUST tải được đồng thời trong cùng một Python session mà không xảy ra xung đột tên module (cả hai phải là package độc lập).
- **FR-008**: Mọi file dữ liệu/asset bên trong sandbox có chứa đường dẫn (vd JSON config, alias file) MUST được rà soát; mọi reference tới `ml_service` MUST được cập nhật hoặc xác nhận không gây sai lệch.
- **FR-009**: Việc duplicate MUST được commit thành một commit git duy nhất với message thể hiện rõ mục đích (sandbox cho thesis benchmarking), tách biệt khỏi commit refactor sau này.
- **FR-010**: Sandbox MUST không tạo dependency ngược tới production (`from ml_service import ...` bị cấm trong toàn bộ `backend/ml_benchmark/`).
- **FR-011**: Sau khi duplicate, suite test của production MUST vẫn pass nguyên trạng (nếu có) để chứng minh không có side effect.
- **FR-012**: Sandbox MUST loại bỏ các thư mục cache (`__pycache__/`, `.pytest_cache/`) trong bản copy để tránh bytecode lỗi thời gây hiểu lầm khi debug.

### Key Entities *(include if feature involves data)*

- **Production ML Service**: Codebase nguyên gốc tại `backend/ml_service/`, là source-of-truth cho hệ thống đang chạy (verifier, scheduler, admin dashboard, inference). Bất khả xâm phạm trong phạm vi feature này.
- **Benchmark Sandbox**: Codebase mới tại `backend/ml_benchmark/`, là một fork đông cứng dùng cho luận văn. Có vòng đời độc lập, có thể bị refactor mạnh, và có thể bị xóa toàn bộ sau khi luận văn kết thúc mà không ảnh hưởng production.
- **Shared Input Data**: Dữ liệu JobFlow (CV, jobs, labels) tại `backend/data/` và `Dataset/` — cả hai service đều read-only từ đây. Không thuộc phạm vi sửa của feature này.
- **Checkpoint Artifacts**: Đầu ra training. Production ghi vào `backend/checkpoints/`, benchmark ghi vào `backend/checkpoints_benchmark/` — hai không gian tách biệt.
- **Commit Lịch Sử**: Lịch sử git của thư mục `backend/ml_benchmark/` được khởi tạo bằng đúng một commit duplicate, sau đó tiếp tục độc lập.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sau khi duplicate, chạy training pipeline trên dataset JobFlow trong sandbox đạt metric (NDCG@10, Recall@10, AUC) trong khoảng ±1% so với baseline production gần nhất (chứng minh sandbox là baseline đáng tin cậy).
- **SC-002**: 100% file trong `backend/ml_service/` không có thay đổi nào (kiểm chứng bằng `git diff` rỗng cho thư mục này) sau khi feature hoàn thành.
- **SC-003**: 0 lỗi import khi chạy bất kỳ entry point nào trong sandbox (training script, evaluation script, baseline script).
- **SC-004**: 0 reference tới namespace `ml_service` trong toàn bộ thư mục `backend/ml_benchmark/` (kiểm chứng bằng grep).
- **SC-005**: Sandbox khởi tạo bằng đúng 1 commit git duy nhất, message commit chứa từ khóa định danh được mục đích (vd "benchmark", "thesis", "duplicate").
- **SC-006**: Cả hai service load được trong cùng một Python session mà không gây ImportError hoặc warning về xung đột namespace.
- **SC-007**: Sandbox không chứa bất kỳ thư mục cache nào (`__pycache__/`, `.pytest_cache/`) tại thời điểm commit.
- **SC-008**: Thời gian thực hiện toàn bộ quy trình duplicate + smoke test không vượt quá 1 ngày làm việc (đảm bảo đây là bước nhanh, không đắt).

## Assumptions

- Production code tại `backend/ml_service/` hiện tại đang chạy ổn định và là baseline đáng tin cậy để fork (không có bug ẩn cần fix trước khi duplicate).
- Dataset JobFlow hiện tại đủ ổn định để chạy smoke test reproducible — không phụ thuộc vào dữ liệu mới đang được crawl/extract đồng thời.
- Thư mục `backend/checkpoints_benchmark/` (hoặc tương đương) chưa tồn tại và có thể tạo mới mà không xung đột.
- Nhà nghiên cứu có quyền tạo branch git mới và commit trực tiếp lên branch feature.
- Sandbox sẽ được sử dụng độc lập, không có yêu cầu sync ngược tới production sau khi tạo (bug fix trong production sau này sẽ không tự động lan tới sandbox — chấp nhận drift).
- Phạm vi sandbox chỉ là benchmark; không phục vụ inference production, không phục vụ API, không phục vụ admin dashboard.
- Sandbox có thể bị xóa hoàn toàn sau khi luận văn nộp xong, không cần bảo trì dài hạn.
- Việc benchmark trong các phase sau (MovieLens, CareerBuilder, LightGCN) là phạm vi của các spec/feature khác — feature này chỉ chuẩn bị sandbox.

## Dependencies

- Tham chiếu kế hoạch tổng quan: [`specs/006-multi-dataset-benchmark/phases.md`](../006-multi-dataset-benchmark/phases.md) — feature này hiện thực hóa Phase 1 trong kế hoạch đó.
- Phụ thuộc trạng thái production: `backend/ml_service/` phải ở trạng thái ổn định (CI xanh, không có refactor lớn đang dở) tại thời điểm duplicate.

## Out of Scope

- Thêm dataset mới (MovieLens-1M, CareerBuilder12) — thuộc Phase 2 & 3.
- Thêm model baseline mới (LightGCN, NGCF) — thuộc Phase 4.
- Refactor abstraction layer cho config-driven trainer — thuộc Phase 2.
- Generalize schema graph từ `cv/job/skill` sang `user/item` chung — sẽ làm sau khi sandbox sẵn sàng.
- Viết kết quả benchmark cho luận văn — thuộc Phase 6.
- Sửa bug trong production ML service — không thuộc phạm vi.
