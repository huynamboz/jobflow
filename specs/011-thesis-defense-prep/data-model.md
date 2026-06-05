# Phase 1 — Data Model: LSTM/BiLSTM Baseline

## E1. Vocab

```python
@dataclass
class Vocab:
    word_to_idx: dict[str, int]
    idx_to_word: list[str]
    pad_idx: int = 0
    unk_idx: int = 1
    size: int   # = len(idx_to_word)
```

Build process:
1. Tokenize tất cả job text (title + description) trong train set (chỉ train, no leak)
2. Count word frequencies
3. Keep top 30_000 most frequent
4. Assign idx: `<pad>=0`, `<unk>=1`, words from 2 to 30001

## E2. Token sequence

```python
@dataclass
class TokenizedExample:
    src_ids: list[int]   # user skill tokens (padded/truncated to max_seq_len)
    src_len: int         # actual length
    dst_ids: list[int]   # job text tokens
    dst_len: int
    label: int           # 1 for positive (apply); negative sampled during BPR
```

## E3. LSTM Encoder

```python
class LSTMEncoder(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_dim, num_layers=1, bidirectional=False, dropout=0.3):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(
            embed_dim, hidden_dim, num_layers=num_layers,
            bidirectional=bidirectional, dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
        )
        if bidirectional:
            self.project = nn.Linear(2 * hidden_dim, hidden_dim)
        else:
            self.project = nn.Identity()
    
    def forward(self, ids: Tensor, lengths: Tensor) -> Tensor:
        # ids: [batch, seq_len], lengths: [batch]
        x = self.embed(ids)  # [batch, seq_len, embed_dim]
        packed = nn.utils.rnn.pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, (h_n, _) = self.lstm(packed)
        # h_n: [num_layers * num_directions, batch, hidden]
        if self.lstm.bidirectional:
            # Concat last layer's forward + backward
            h = torch.cat([h_n[-2], h_n[-1]], dim=-1)  # [batch, 2*hidden]
        else:
            h = h_n[-1]  # [batch, hidden]
        return self.project(h)  # [batch, hidden]
```

## E4. LSTM Scorer (full model)

```python
class LSTMScorer(nn.Module):
    def __init__(self, num_users, num_jobs, vocab_size, embed_dim=64, hidden_dim=64, bidirectional=False):
        super().__init__()
        # Shared vocab encoder for both user and job (parameter sharing reduces overfit on small data)
        self.encoder = LSTMEncoder(vocab_size, embed_dim, hidden_dim, bidirectional=bidirectional)
    
    def encode_user(self, user_token_ids, user_lengths):
        return self.encoder(user_token_ids, user_lengths)  # [batch, hidden]
    
    def encode_job(self, job_token_ids, job_lengths):
        return self.encoder(job_token_ids, job_lengths)  # [batch, hidden]
    
    def score(self, user_emb, job_emb):
        # Dot product (cùng LightGCN convention)
        return (user_emb * job_emb).sum(dim=-1)  # [batch]
```

Note: shared encoder (1 instance) cho cả user và job. Lý do: user side là skill keywords (short), job side là full text — nhưng cùng vocab. Sharing tăng parameter efficiency + giảm risk overfit.

## E5. Data containers

```python
@dataclass
class LSTMDataset:
    train_pairs: list[tuple[int, int]]   # (user_idx, job_idx)
    val_pairs: list[tuple[int, int]]
    test_pairs: list[tuple[int, int]]
    num_users: int
    num_jobs: int
    
    # Tokenized text
    user_token_ids: Tensor   # [num_users, max_seq_len]
    user_lengths: Tensor     # [num_users]
    job_token_ids: Tensor    # [num_jobs, max_seq_len]
    job_lengths: Tensor      # [num_jobs]
    
    vocab: Vocab
```

## E6. Output JSON schema

`backend/results/{lstm,bilstm}/careerbuilder_seed{N}.json`:

```json
{
  "feature": "011-thesis-defense-prep",
  "dataset": "CareerBuilder12",
  "variant": "bipartite",
  "preprocessing": { ... same as Phase 3 ... },
  "model": "LSTM" | "BiLSTM",
  "config": {
    "embed_dim": 64,
    "hidden_dim": 64,
    "num_layers": 1,
    "bidirectional": false | true,
    "vocab_size": 30000,
    "max_seq_len": 200,
    "dropout": 0.3,
    "lr": 1e-3,
    "max_epochs": 100,
    "early_stopping_patience": 20,
    "seed": 42
  },
  "stats": {
    "num_users": ...,
    "num_jobs": ...,
    "num_train_pairs": ...,
    "num_val_pairs": ...,
    "num_test_pairs": ...,
    "vocab_actual_size": ...,
    "avg_user_seq_len": ...,
    "avg_job_seq_len": ...
  },
  "training": { ... },
  "test_metrics": { "ndcg@20": ..., "recall@20": ..., "hr@20": ..., "mrr": ... },
  "versions": { ... }
}
```

## E7. Invariants

| Rule | Check |
|---|---|
| Vocab built from train set only (no leak) | Vocab construction trước split usage |
| Pad idx = 0 throughout | `assert vocab.pad_idx == 0` |
| User text aggregated from TRAIN positives only | Track per-user train apply set |
| Job text from jobs_filtered.tsv | `assert jobs_filtered.tsv.exists()` |
| Sequence length capped at max_seq_len | `assert (lengths <= max_seq_len).all()` |
