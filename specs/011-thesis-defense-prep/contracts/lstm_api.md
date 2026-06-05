# Contract — LSTM/BiLSTM Baseline API

**Date**: 2026-05-21

## 1. New module

```python
from ml_benchmark.baselines.lstm import LSTMEncoder, LSTMScorer, Vocab, build_vocab, tokenize
```

## 2. Vocab

```python
@dataclass
class Vocab:
    word_to_idx: dict[str, int]
    idx_to_word: list[str]
    pad_idx: int   # = 0
    unk_idx: int   # = 1
    size: int

def build_vocab(texts: Iterable[str], max_size: int = 30_000) -> Vocab: ...
def tokenize(text: str, vocab: Vocab, max_len: int) -> tuple[list[int], int]: ...
```

## 3. LSTMEncoder / LSTMScorer

Per [data-model §E3-E4](../data-model.md).

## 4. CLI

```bash
# Single seed LSTM
python backend/scripts/train_lstm.py --dataset careerbuilder --seed 42 \
    --output results/lstm/careerbuilder_seed42.json

# Single seed BiLSTM
python backend/scripts/train_lstm.py --dataset careerbuilder --seed 42 --bilstm \
    --output results/bilstm/careerbuilder_seed42.json

# Multi-seed via benchmark_compare
python backend/scripts/benchmark_compare.py \
    --train-script scripts/train_lstm.py \
    --seeds 42 123 2024 \
    --output results/lstm/careerbuilder_summary.json \
    --extra --dataset careerbuilder

python backend/scripts/benchmark_compare.py \
    --train-script scripts/train_lstm.py \
    --seeds 42 123 2024 \
    --output results/bilstm/careerbuilder_summary.json \
    --extra --dataset careerbuilder --bilstm
```

## 5. Output JSON schema

Identical Phase 2-4 with `model: "LSTM"` or `"BiLSTM"`. See [data-model §E6](../data-model.md#e6-output-json-schema).

## 6. Backward compatibility

Phase 1-4 surface untouched. Phase 2 + 3 + 4 smoke must still pass.
