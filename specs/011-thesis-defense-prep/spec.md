# Feature Specification: Thesis Defense Preparation

**Feature Branch**: `011-thesis-defense-prep`

**Created**: 2026-05-21

**Status**: Draft

**Input**: User description: "Phase 5: Address thầy's review notes — implement LSTM/BiLSTM baselines, viết documentation cho 4 notes của thầy."

## Clarifications

### Session 2026-05-21 (auto-resolved per Phase 4 best practices)

User instruction: tự quyết theo best practice.

- Q: Phạm vi LSTM/BiLSTM — encode gì? → A: **Encode CV/user side bằng skill list (CB12 không có user CV text), encode Job side bằng job description text** (đã có từ jobs_filtered.tsv Phase 4c). Dot product 2 vectors → score. Đây là pattern chuẩn cho text-based recsys baseline.
- Q: LSTM trên dataset nào? → A: **CB12 only** trong Phase 5. MovieLens không có text features, JobFlow data quá nhỏ. Out-of-scope per user note. Còn budget thì test thêm.
- Q: Documentation viết bằng ngôn ngữ nào? → A: **Vietnamese**, đặt trong `specs/011-thesis-defense-prep/thesis_notes.md` để stable + version-controlled cùng spec. Có thể symlink hoặc copy sang `roadmap/docs/` nếu muốn.
- Q: Multi-seed cho LSTM/BiLSTM? → A: **3 seeds** (42, 123, 2024) — giữ pattern Phase 3/4 cho fair comparison.
- Q: Hyperparameters LSTM? → A: **Sensible defaults**: hidden=64 (cùng GNN), num_layers=1 (LSTM thường 1-2 enough), lr=1e-3, max_seq_len=200 tokens (đủ cho job title + first paragraph of description), max_epochs=100 (LSTM converge nhanh hơn GNN). KHÔNG tune per-dataset.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — LSTM/BiLSTM baseline trên CB12 (Priority: P1) 🎯 MVP

Sau Phase 4 (LightGCN baseline) thầy yêu cầu so sánh thêm với LSTM, BiLSTM trên cùng dataset để justify GNN choice. Researcher cần implement 2 baseline sequence-based, train trên CB12 với cùng eval methodology, output JSON cho bảng so sánh.

**Why this priority**: Thầy explicitly request → quan trọng cho defense. Không có baseline LSTM/BiLSTM → argument "vì sao chọn GNN không chọn LSTM" yếu.

**Independent Test**: 2 file `results/lstm/careerbuilder_summary.json` và `results/bilstm/careerbuilder_summary.json` chứa mean ± std qua 3 seed; metric NDCG@20/Recall@20/HR@20/MRR.

**Acceptance Scenarios**:

1. **Given** CB12 dataset có jobs_filtered.tsv (Phase 4c), **When** chạy `train_lstm.py --dataset careerbuilder --seed 42`, **Then** sinh result JSON theo cùng schema Phase 2/3/4.
2. **Given** train xong 3 seeds, **When** chạy benchmark_compare.py, **Then** có summary JSON với mean ± std.
3. **Given** smoke 5 epoch, **When** chạy, **Then** xong < 5 phút, exit 0, no NaN.
4. **Given** train full, **When** so sánh với HeteroSAGE + LightGCN, **Then** có bảng 4-row (HeteroSAGE / LightGCN / LSTM / BiLSTM) trên CB12.

---

### User Story 2 — Thesis defense documentation (Priority: P1) 🎯 MVP

Researcher cần document Vietnamese trả lời 4 notes của thầy, ready cho buổi defense + draft luận văn.

**Why this priority**: Equal P1 với US1 — cả 2 cần thiết cho defense. Có thể làm parallel.

**Independent Test**: File `specs/011-thesis-defense-prep/thesis_notes.md` tồn tại với 4 section: (1) HeteroSAGE justification, (2) Improvement directions, (3) Application scenario, (4) GNN vs LSTM comparison — đầy đủ, dễ đọc, có table/diagram.

**Acceptance Scenarios**:

1. **Given** kết quả Phase 2-4 + Phase 5 LSTM, **When** thầy đọc thesis_notes.md, **Then** mỗi note 1/2/6/7 có câu trả lời cụ thể (không chung chung).
2. **Given** doc viết xong, **When** print, **Then** ≤ 10 trang A4, có table comparison + use case diagram.
3. **Given** thesis_notes.md, **When** thầy hỏi follow-up, **Then** có evidence từ JSON files (link cụ thể).

---

### Edge Cases

- **CB12 không có user text** (chỉ có user_id + structured fields). LSTM với user side cần feature. Workaround: dùng user's applied skills list (aggregate skill từ apps history) → encode bằng LSTM trên skill sequence.
- **Job description text quá dài** (~1000+ tokens average). Truncate hoặc lấy first N tokens.
- **Tokenization choice**: simple whitespace split vs subword (BPE/WordPiece). Default: whitespace + lowercase, max_vocab_size = 30K most frequent words.
- **OOV (out-of-vocab) tokens**: map sang `<unk>`.
- **LSTM training trên small dataset có thể overfit nhanh** → early stopping + dropout 0.3.
- **GPU memory với batch large**: chunk eval theo Phase 2 pattern.
- **Reproducibility tolerance**: cùng spec Phase 3 (< 0.05 cho CB12).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Module `ml_benchmark/baselines/lstm.py` cung cấp class `LSTMScorer` và `BiLSTMScorer` — encode 1 chuỗi token → vector.
- **FR-002**: Module dùng word-level tokenization (whitespace + lowercase), vocab build từ training corpus, max_vocab 30K.
- **FR-003**: Script `backend/scripts/train_lstm.py` accept `--dataset careerbuilder`, `--bidirectional/--no-bidirectional` (or `--bilstm` flag), `--seed`, output JSON.
- **FR-004**: Score = dot product giữa user embedding (LSTM(user_skill_sequence)) và job embedding (LSTM(job_description_tokens)).
- **FR-005**: Output JSON theo cùng schema Phase 2/3/4 (đổi `model: "LSTM"` hoặc `"BiLSTM"`).
- **FR-006**: Eval theo per-user full ranking (cùng Phase 2/3/4 methodology, reuse GPU eval helper).
- **FR-007**: Multi-seed (3 seeds) via existing `benchmark_compare.py --train-script scripts/train_lstm.py`.
- **FR-008**: Reproducibility tolerance < 0.05 absolute cho CB12 (cùng SC-003 Phase 3).
- **FR-009**: Smoke test < 5 phút (LSTM converge nhanh hơn GNN).
- **FR-010**: Full train < 1h GPU per seed per dataset.
- **FR-011**: KHÔNG đụng `backend/ml_service/`. KHÔNG sửa Phase 2-4 code.
- **FR-012**: Document `specs/011-thesis-defense-prep/thesis_notes.md` (Vietnamese, ≤ 10 trang):
  - Section 1: HeteroSAGE justification (so với GCN/GAT/LightGCN/HGT, evidence từ Phase 3-4)
  - Section 2: Improvement directions (5+ concrete ideas + estimated impact)
  - Section 3: Application scenario (input/output/integration với production code)
  - Section 4: GNN vs LSTM/BiLSTM comparison (evidence từ Phase 5 results)
- **FR-013**: Bảng benchmark cuối có row LSTM + BiLSTM bên cạnh HeteroSAGE bipartite/hetero + LightGCN.

### Key Entities

- **LSTM Encoder**: 1-layer LSTM, hidden=64, dùng cuối hidden state (hoặc mean pooling) làm vector.
- **BiLSTM Encoder**: tương tự nhưng bidirectional; final = concat(forward last, backward last) → linear project to hidden=64.
- **Vocab**: dict[word, int_id] build từ tokenize tất cả job description text + canonical skill names trong training set.
- **Token Sequence**: list of int IDs (padded/truncated to max_seq_len).
- **LSTM Result JSON**: cùng schema Phase 2/3/4, thêm field `vocab_size` trong `config`.
- **Thesis Notes Doc**: markdown Vietnamese trả lời 4 notes thầy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Researcher chạy 1 lệnh per (model, dataset, seed) → có metric LSTM/BiLSTM.
- **SC-002**: LSTM/BiLSTM CB12 đạt NDCG@20 trong [0.01, 0.20] — chứng minh model train đúng (không random/leak).
- **SC-003**: Reproducibility tolerance < 0.05 absolute (cùng Phase 3 spec).
- **SC-004**: Smoke test < 5 phút.
- **SC-005**: 100% file trong `backend/ml_service/` không đổi.
- **SC-006**: Phase 2-4 smoke test vẫn pass sau Phase 5 merge (regression).
- **SC-007**: `thesis_notes.md` ≤ 10 trang, có ≥ 1 table comparison, ≥ 1 diagram/flowchart.
- **SC-008**: Phase 5 hoàn thành trong ≤ 1.5 ngày (target 5h + 1h GPU).
- **SC-009**: Cuối Phase 5, bảng benchmark có ≥ 4 row models (HeteroSAGE bipartite, HeteroSAGE hetero, LightGCN, LSTM, BiLSTM) trên CB12.

## Assumptions

- Sandbox `backend/ml_benchmark/` đã có đầy đủ infra Phase 2-4.
- `jobs_filtered.tsv` (4.6MB từ Phase 4c) đã có trên local và server — chứa job description text.
- Eval methodology per-user full ranking work cho LSTM/BiLSTM giống GNN.
- LSTM/BiLSTM 1 layer + hidden=64 đủ — không tune cao hơn.
- Tokenization whitespace đủ — không cần BPE/WordPiece (tăng complexity không cần).
- Production `inference/engine.py` đã chạy production → application scenario có thể document từ existing code, không cần demo mới.

## Dependencies

- Sandbox Phase 2-4 (007 + 008 + 009 + 010)
- jobs_filtered.tsv của Phase 4c (đã có local + server)
- `benchmark_compare.py` với `--train-script` (Phase 3)
- GPU eval helper (Phase 2)

## Out of Scope

- Transformer baseline (BERT/SBERT — defer cho future work)
- Train LSTM/BiLSTM trên MovieLens hoặc JobFlow (chỉ CB12 trong Phase 5)
- Production deployment of LSTM model (chỉ research baseline)
- Word embedding pre-trained (GloVe/Word2Vec — defer, dùng learnable embedding from scratch)
- Hyperparameter tuning sweep (dùng default sensible per clarification Q5)
- Translate thesis_notes.md sang English (Vietnamese cho thầy)
