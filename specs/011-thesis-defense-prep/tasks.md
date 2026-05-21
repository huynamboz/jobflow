---
description: "Task list for feature 011 — Thesis Defense Preparation (LSTM/BiLSTM baselines + thesis docs)"
---

# Tasks: Thesis Defense Preparation

**Input**: Design documents from `/specs/011-thesis-defense-prep/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/lstm_api.md, quickstart.md

**Tests**: Not requested. Verify via smoke + metric range + Phase 2-4 regression.

**Organization**: 2 user stories (US1 baseline P1, US2 docs P1) — có thể chạy parallel.

## Format: `[ID] [P?] [Story?] Description`

## Path Conventions

- Sandbox: `backend/ml_benchmark/baselines/` + `backend/scripts/` + `backend/results/`
- Docs: `specs/011-thesis-defense-prep/thesis_notes.md`
- Server: `/home/dana/huynam/jobflow-gnn/backend/`

---

## Phase 1: Setup

- [x] T001 [P] Tạo `backend/results/lstm/` + `backend/results/bilstm/` với `.gitkeep`.
- [x] T002 [P] Verify `Dataset/careerbuilder-12/jobs_filtered.tsv` tồn tại local + server (Phase 4c output).
- [x] T003 [P] Verify PyTorch `nn.LSTM` available trên server: `sshpass -e ssh dana@10.9.0.4 ".venv/bin/python -c 'import torch; print(torch.nn.LSTM)'"`.

---

## Phase 2: Foundational (BLOCK US1)

- [x] T004 Viết `backend/ml_benchmark/baselines/lstm.py`:
  - `Vocab` dataclass + `build_vocab(texts, max_size=30000)` + `tokenize(text, vocab, max_len)`
  - `LSTMEncoder(vocab_size, embed_dim, hidden_dim, bidirectional, dropout)` theo [data-model §E3](data-model.md#e3-lstm-encoder)
  - `LSTMScorer(num_users, num_jobs, vocab_size, embed_dim, hidden_dim, bidirectional)` theo [data-model §E4](data-model.md#e4-lstm-scorer-full-model) — shared encoder cho user và job side
  - Sử dụng `nn.utils.rnn.pack_padded_sequence` + `enforce_sorted=False` cho padding
- [x] T005 Viết `backend/scripts/train_lstm.py` (~200 lines):
  - sklearn + torch_geometric pre-warm (Phase 2 lessons)
  - CLI args: `--dataset careerbuilder`, `--seed`, `--bilstm`, `--max-epochs 100`, `--patience 20`, `--embed-dim 64`, `--hidden-dim 64`, `--max-seq-len 200`, `--vocab-size 30000`, `--dropout 0.3`, `--lr 1e-3`, `--output`
  - Load CB12 bipartite từ `careerbuilder_loader.load_careerbuilder_12()` (reuse Phase 3)
  - Load jobs_filtered.tsv → build vocab từ training jobs only
  - Build user text từ aggregate skills (chỉ train apps, no leak — extract skills via Phase 4c logic)
  - Tokenize all user + job text
  - Train BPR loss + per-user full ranking eval (reuse pattern Phase 4 evaluate_lightgcn)
  - Output JSON schema theo [data-model §E6](data-model.md#e6-output-json-schema), `model="LSTM"` or `"BiLSTM"`

---

## Phase 3: User Story 1 — LSTM/BiLSTM training (P1 🎯)

- [x] T006 [US1] Sync code lên server: `backend/ml_benchmark/baselines/lstm.py` + `backend/scripts/train_lstm.py`.
- [x] T007 [US1] Smoke LSTM trên server: `python scripts/train_lstm.py --dataset careerbuilder --seed 42 --max-epochs 5 --output /tmp/lstm_smoke.json`. Verify exit 0, no NaN, < 5 min.
- [x] T008 [US1] Smoke BiLSTM: `python scripts/train_lstm.py --dataset careerbuilder --seed 42 --max-epochs 5 --bilstm --output /tmp/bilstm_smoke.json`. Verify cùng.
- [x] T009 [P] [US1] **Regression Phase 2-4**: `python scripts/smoke_test_movielens.py` + `python scripts/smoke_test_careerbuilder.py`. Cả 2 PASS với metric chệch < 5%.
- [x] T010 [US1] **Full train LSTM 3 seeds**: `python scripts/benchmark_compare.py --train-script scripts/train_lstm.py --seeds 42 123 2024 --output results/lstm/careerbuilder_summary.json --extra --dataset careerbuilder`. Wall time ~30-60 min.
- [x] T011 [US1] **Full train BiLSTM 3 seeds**: `python scripts/benchmark_compare.py --train-script scripts/train_lstm.py --seeds 42 123 2024 --output results/bilstm/careerbuilder_summary.json --extra --dataset careerbuilder --bilstm`. Wall time ~30-60 min.
- [x] T012 [US1] Verify metric range (SC-002): LSTM + BiLSTM NDCG@20 ∈ [0.01, 0.20].
- [x] T013 [US1] Sync results về local: `results/lstm/` + `results/bilstm/`.
- [x] T014 [P] [US1] Verify SC-005 production untouched: `git diff --stat backend/ml_service/` empty.
- [x] T015 [US1] Generate 5-row comparison table (HeteroSAGE bipartite + hetero + LightGCN + LSTM + BiLSTM) theo quickstart Step 6, save vào `/tmp/comparison_table.txt`.

**Checkpoint**: US1 done.

---

## Phase 4: User Story 2 — Thesis documentation (P1, parallel with US1)

- [x] T016 [P] [US2] Viết section 1 trong `specs/011-thesis-defense-prep/thesis_notes.md` — HeteroSAGE justification:
  - Why GraphSAGE (inductive, scalable, PyG to_hetero, PinSage)
  - Comparison matrix (GCN, GAT, R-GCN, HGT, LightGCN, GraphSAGE) — pros/cons mỗi cái cho job-rec
  - Evidence từ Phase 3-4: thắng JobFlow (rich schema), thua LightGCN trên CB12 (pure CF)
- [x] T017 [P] [US2] Viết section 2 — Improvement directions (future work):
  - LLM-based NER skill extraction
  - Hybrid scoring (đã có production)
  - Attention mechanism (HGT)
  - Pre-trained text embeddings
  - Hard negative mining
  - Mỗi improvement: short description + estimated impact + effort
- [x] T018 [P] [US2] Viết section 3 — Application scenario:
  - Input: CV (PDF text)
  - Pipeline diagram: parse → embed → rank → top-K with explanation
  - Output example (mock JSON với top 10 jobs + matched skills explanation)
  - Integration: existing `backend/ml_service/inference/engine.py` + REST API
  - Production deployment readiness
- [x] T019 [P] [US2] Viết section 4 — GNN vs LSTM/BiLSTM comparison (cần T015 xong trước):
  - Argument: vì sao GNN > sequence model cho job-rec
  - Evidence: bảng comparison Phase 4 + Phase 5 (5 models trên CB12)
  - Discussion: LSTM mạnh ở text encoding nhưng yếu ở collaborative signal; GNN bipartite (LightGCN) ngược lại
- [x] T020 [US2] Verify thesis_notes.md (SC-007): ≤ 10 trang A4, có ≥ 1 table, ≥ 1 diagram (ASCII art OK).

**Checkpoint**: US2 done.

---

## Phase 5: Polish

- [x] T021 [P] Update `specs/006-multi-dataset-benchmark/phases.md` mark Phase 5 DONE + link 011.
- [x] T022 [P] Save comparison table vào `specs/011-thesis-defense-prep/_comparison_5models.md` (committed evidence).

---

## Phase 6: Commit

- [ ] T023 Stage feature 011 artifacts:
  ```
  git add backend/ml_benchmark/baselines/lstm.py \
          backend/scripts/train_lstm.py \
          backend/results/lstm/ backend/results/bilstm/ \
          specs/011-thesis-defense-prep/ \
          specs/006-multi-dataset-benchmark/phases.md \
          CLAUDE.md \
          .specify/feature.json
  ```
  TUYỆT ĐỐI KHÔNG `git add backend/ml_service/`.
- [ ] T024 Verify staged sạch: `git diff --cached --stat | grep ml_service` empty.
- [ ] T025 Commit với heredoc message (detailed at implement time).
- [ ] T026 Verify single commit + production history clean.

---

## Dependencies

- Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1) + Phase 4 (US2 parallel) → Phase 5 (Polish) → Phase 6 (Commit)
- T019 (US2 section 4) phụ thuộc T015 (US1 comparison table)
- T009 + T014 ([P]) parallel với US1 main path

## MVP scope

T001-T015 → có baseline LSTM/BiLSTM. T016-T020 docs parallel. Skip Phase 5/6 nếu cần MVP trước.

## Notes

- LSTM training ước tính 5-10 min mỗi seed (CB12 nhỏ, sequence ngắn) → 3 seeds × 2 models = 60 min GPU.
- Thesis docs viết tay (Vietnamese, ~10 trang) → ~2-3 hours work, parallel với training.
- Total Phase 5 effort: ~5h work + ~1h GPU (target SC-008).
