# Phase 0 — Research: LSTM/BiLSTM Baseline

**Date**: 2026-05-21

## R1. LSTM implementation source

### Decision

PyTorch `torch.nn.LSTM` built-in. `bidirectional=True` cho BiLSTM, `bidirectional=False` cho LSTM. Trong 1 file `ml_benchmark/baselines/lstm.py`, expose:

- `LSTMEncoder(vocab_size, embed_dim, hidden_dim, bidirectional)` — embedding + LSTM + pooling layer
- `LSTMScorer(num_users, num_jobs, vocab_size, ...)` — wrap encoder; produce user_emb, job_emb; dot product score

### Rationale

- PyTorch built-in: well-tested, GPU-accelerated, no extra deps
- 1 file cho cả 2 variant → less code duplication
- Bidirectional flag → 1 line difference

## R2. User encoding strategy

### Decision

**Aggregate skill sequence**: cho mỗi user, lấy tất cả `applied_job_id`, lookup skills extracted ở Phase 4c, join với space → 1 text string. Tokenize bằng cùng vocab như job side.

Example: user 42 applied to jobs [101, 205, 308]; skills extracted: {python, sql, docker, react, javascript}. User text = "python sql docker react javascript".

### Rationale

- CB12 không có user CV/resume text — chỉ có user_id + structured (gender/age/etc, không text)
- Skills là proxy semantic cho "user profile"
- Reuse skill extraction Phase 4c → không thêm complexity
- Có thể có "data leak" vì train pairs đóng góp vào user text → fix bằng cách chỉ dùng skills của jobs trong train set (no val/test)

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| Random init user embedding | Mất ý nghĩa "user profile từ text" — không fair với LSTM premise |
| User structured field (age/gender) | Quá thưa, không text-like |
| External CV dataset → match user_id | CB12 không công bố CV text gốc |

## R3. Job encoding

### Decision

`title + " " + description` từ jobs_filtered.tsv (4.6MB, đã có Phase 4c). Tokenize whitespace + lowercase.

### Rationale

- Description text rich content → LSTM có signal mạnh
- Title đứng đầu giúp model nhanh ngữ cảnh seniority/role
- Truncate 200 tokens (covers most jobs, avoid memory issues)

## R4. Tokenization

### Decision

- Whitespace split + lowercase
- Strip punctuation (simple regex: replace non-alphanumeric with space)
- Vocab: top-30K most frequent words từ training corpus (job text only; build before split)
- Special tokens: `<pad>` (idx 0), `<unk>` (idx 1)

### Rationale

- Đơn giản, deterministic, không cần dep ngoài
- 30K vocab đủ cho CB12 (~6-8K unique words sau filter, có headroom)
- BPE/WordPiece overkill cho baseline

### Alternatives considered

| Phương án | Lý do loại |
|---|---|
| HuggingFace BERT tokenizer | Thêm dep, không cần cho LSTM baseline (BPE đa năng hơn cần thiết) |
| GloVe pre-trained embed | Defer cho future work (per spec out-of-scope) |

## R5. Sequence length

### Decision

`max_seq_len = 200` tokens.

### Rationale

Quick analysis (đã check Phase 4c data): job description sau title concat ~200-1000 words. Truncate 200 → giữ title + first paragraph (đủ thông tin role/seniority/key skills). Memory: 200 × 64 hidden × batch 256 = manageable on RTX 3090.

User skill sequence: average ~10-30 skills per user → padding to 200, mostly empty padding (no harm).

## R6. Padding & OOV

### Decision

- `<pad>` = idx 0 (mask trong LSTM forward via `pack_padded_sequence`)
- `<unk>` = idx 1 (cho mọi word không trong top-30K)
- Real words: idx 2 to vocab_size-1

Pre-pad on left or right? Use right-padding (standard PyTorch, dùng `enforce_sorted=False` để không phải sort).

### Rationale

PyTorch convention; mask out pad positions từ hidden state contribution.

## R7. Pooling

### Decision

- **LSTM**: dùng cuối hidden state `h_n[-1]` (last layer's last time step), shape [batch, hidden]
- **BiLSTM**: concat(`h_n[-2]`, `h_n[-1]`) (forward last + backward last), then `Linear(2*hidden, hidden)` → [batch, hidden]

### Rationale

- Standard convention cho LSTM-based text encoding
- Linear projection ở BiLSTM keep output dim = hidden (so dot product với user side OK)

### Alternatives considered

- Mean pooling across all time steps — robust với short sequences nhưng dilute signal cho long
- Attention pooling — overkill cho baseline

## R8. Scoring

### Decision

`score(user, job) = dot_product(user_emb, job_emb)` — cùng pattern LightGCN.

### Rationale

- Fair compare với LightGCN scoring
- No extra params trong scoring → focus signal vào encoding quality

## Hyperparameters

| Param | Value | Lý do |
|---|---|---|
| embed_dim | 64 | Cùng GNN hidden |
| hidden_dim | 64 | Cùng GNN hidden |
| num_layers | 1 | LSTM 1 layer đủ cho baseline, tránh overfit |
| dropout | 0.3 | Standard cho LSTM regularization |
| lr | 1e-3 | Adam default, work tốt cho LSTM |
| max_epochs | 100 | LSTM converge nhanh hơn GNN |
| patience | 20 | Tighter than GNN (LSTM overfit nhanh) |
| batch_size | 256 | RTX 3090 memory fit |
| max_seq_len | 200 | Per R5 |
| vocab_size | 30_000 | Per R4 |

## Sẵn sàng Phase 1.
