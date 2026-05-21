# Implementation Plan: Thesis Defense Preparation

**Branch**: `011-thesis-defense-prep` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)

## Summary

2 deliverables parallel:
1. **Code**: LSTM + BiLSTM baseline trên CB12 với cùng eval methodology Phase 2-4
2. **Documentation**: `thesis_notes.md` (Vietnamese) trả lời 4 notes của thầy

Reuse: jobs_filtered.tsv (Phase 4c), benchmark_compare.py, GPU eval helper, JSON schema.

## Technical Context

**Language/Version**: Python 3.11+
**Dependencies**: PyTorch (nn.LSTM built-in). KHÔNG thêm dep mới.
**Storage**: `backend/results/lstm/careerbuilder_summary.json` + `backend/results/bilstm/careerbuilder_summary.json`
**Performance**: Smoke < 5 min; full train < 1h GPU per seed
**Constraints**: KHÔNG đụng ml_service, KHÔNG sửa Phase 2-4
**Scale**: CB12 sau k-core=10 ≈ 3K user × 3K job × 50K train pair; vocab ~10-30K words

## Constitution Check

- Isolation: PASS — chỉ thêm trong `baselines/` + `scripts/` + `results/` + `specs/011*`
- Reversibility: PASS — 1 commit
- Reproducibility: PASS — seed fix theo Phase 3 spec
- Comparability: PASS — same eval, same dataset, same K

## Project Structure

```
backend/
├── ml_benchmark/
│   └── baselines/
│       └── lstm.py                ← NEW (~120 lines, both LSTM + BiLSTM)
├── scripts/
│   └── train_lstm.py              ← NEW (~200 lines, --bilstm flag)
└── results/
    ├── lstm/
    │   └── careerbuilder_summary.json + seed{42,123,2024}.json
    └── bilstm/
        └── careerbuilder_summary.json + seed{42,123,2024}.json

specs/011-thesis-defense-prep/
├── thesis_notes.md                ← NEW (Vietnamese, ~10 trang A4)
└── ... (spec/plan/research/etc.)
```

## Phase 0 — Research

Đã verified PyTorch nn.LSTM. 8 quyết định kỹ thuật:

| ID | Topic | Decision |
|---|---|---|
| R1 | LSTM impl | `torch.nn.LSTM` built-in (1 layer, bidirectional flag) |
| R2 | User encoding | Aggregate user's applied jobs' canonical skills → space-joined string → tokenize |
| R3 | Job encoding | Tokenize `title + " " + description` từ jobs_filtered.tsv |
| R4 | Tokenization | Whitespace split + lowercase, vocab top-30K most frequent words |
| R5 | Sequence length | max_seq_len=200 tokens (≥99% percentile job title+desc length sau truncation) |
| R6 | Padding/OOV | `<pad>` idx=0, `<unk>` idx=1; real words start from idx=2 |
| R7 | Pooling | Cuối hidden state (LSTM h_n) cho LSTM; concat(forward h_n, backward h_n) cho BiLSTM, sau đó Linear → hidden=64 |
| R8 | Scoring | Dot product user_emb @ job_emb.T → giống LightGCN scoring |

## Phase 1 — Design

Đã hoàn tất:
- [data-model.md](data-model.md): LSTM entity + vocab + sequence encoding
- [contracts/lstm_api.md](contracts/lstm_api.md): public API
- [quickstart.md](quickstart.md): 6-step verify procedure
- CLAUDE.md updated

## Phase 2 — Tasks (KHÔNG tạo ở /speckit-plan)

`/speckit-tasks` sẽ sinh ~12-15 tasks:
1. Setup results dir
2. Write lstm.py (Encoder + Scorer)
3. Write train_lstm.py
4. Smoke test
5. Train LSTM 3 seeds + BiLSTM 3 seeds (6 runs total)
6. Verify metric range + comparison table
7. Write thesis_notes.md
8. Commit

## Re-evaluation post-design

All gates PASS.
