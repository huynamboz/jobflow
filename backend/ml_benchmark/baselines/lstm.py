"""LSTM / BiLSTM baseline (feature 011).

Sequence-based baseline for text-based recsys: encodes user side (a
concatenated sequence of skill keywords aggregated from the user's training
positive items) and job side (job title + description) using a shared LSTM
encoder, then scores user-job pairs by dot product.

Reuses Phase 2-4 evaluation infrastructure: per-user full-ranking
NDCG@20 / Recall@20 / HR@20 / MRR with train-seen masking.

Reference for sequence encoders in recsys baselines: standard practice in
Zhang et al. (2019) "Deep Learning based Recommender System: A Survey".
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import torch
import torch.nn as nn
from torch import Tensor

logger = logging.getLogger(__name__)

PAD_IDX = 0
UNK_IDX = 1


@dataclass
class Vocab:
    word_to_idx: dict[str, int]
    idx_to_word: list[str]
    pad_idx: int = PAD_IDX
    unk_idx: int = UNK_IDX

    @property
    def size(self) -> int:
        return len(self.idx_to_word)


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _split_tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def build_vocab(texts: Iterable[str], max_size: int = 30_000) -> Vocab:
    """Build word→idx vocab from the iterable of text strings.

    Special tokens: <pad> at index 0, <unk> at index 1; real words start at 2.
    Top (max_size - 2) most frequent words are kept.
    """
    counter: Counter[str] = Counter()
    for t in texts:
        counter.update(_split_tokens(t))
    most_common = counter.most_common(max_size - 2)
    idx_to_word = ["<pad>", "<unk>"] + [w for w, _ in most_common]
    word_to_idx = {w: i for i, w in enumerate(idx_to_word)}
    logger.info("Vocab built: %d unique words → kept top %d", len(counter), len(idx_to_word))
    return Vocab(word_to_idx=word_to_idx, idx_to_word=idx_to_word)


def tokenize(text: str, vocab: Vocab, max_len: int) -> tuple[list[int], int]:
    """Tokenize a text string into a list of vocab IDs, truncate/pad to max_len.

    Returns (ids, true_length). Padding done with PAD_IDX = 0.
    """
    tokens = _split_tokens(text)[:max_len]
    ids = [vocab.word_to_idx.get(t, vocab.unk_idx) for t in tokens]
    true_len = len(ids)
    if true_len < max_len:
        ids = ids + [vocab.pad_idx] * (max_len - true_len)
    # Edge case: empty sequence — keep length=1 so pack_padded_sequence works
    if true_len == 0:
        true_len = 1
    return ids, true_len


class LSTMEncoder(nn.Module):
    """Embedding + LSTM (uni- or bidirectional) → fixed-size vector.

    For bidirectional, concat forward / backward last hidden states then
    project back to hidden_dim so the output can be dot-producted with the
    other side's encoding.
    """

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 64,
        hidden_dim: int = 64,
        num_layers: int = 1,
        bidirectional: bool = False,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.bidirectional = bidirectional
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=PAD_IDX)
        self.lstm = nn.LSTM(
            embed_dim,
            hidden_dim,
            num_layers=num_layers,
            bidirectional=bidirectional,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        if bidirectional:
            self.project = nn.Linear(2 * hidden_dim, hidden_dim)
        else:
            self.project = nn.Identity()

    def forward(self, ids: Tensor, lengths: Tensor) -> Tensor:
        """ids: [batch, seq_len]; lengths: [batch] (true lengths before padding)."""
        x = self.embed(ids)  # [batch, seq_len, embed]
        packed = nn.utils.rnn.pack_padded_sequence(
            x, lengths.cpu().clamp(min=1), batch_first=True, enforce_sorted=False
        )
        _, (h_n, _) = self.lstm(packed)
        if self.bidirectional:
            # h_n: [num_layers*2, batch, hidden] — take last layer forward + backward
            h = torch.cat([h_n[-2], h_n[-1]], dim=-1)  # [batch, 2*hidden]
        else:
            h = h_n[-1]  # [batch, hidden]
        return self.project(h)  # [batch, hidden]


class LSTMScorer(nn.Module):
    """User-Job sequence-based scorer: shared encoder → dot product.

    Sharing the encoder across user-side and job-side reduces parameter count
    and helps the small per-side data (user text = aggregated skill list) latch
    onto the same vocab semantics as the job-side text.
    """

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 64,
        hidden_dim: int = 64,
        bidirectional: bool = False,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.encoder = LSTMEncoder(
            vocab_size=vocab_size,
            embed_dim=embed_dim,
            hidden_dim=hidden_dim,
            bidirectional=bidirectional,
            dropout=dropout,
        )

    def encode(self, ids: Tensor, lengths: Tensor) -> Tensor:
        return self.encoder(ids, lengths)

    def score(self, user_emb: Tensor, job_emb: Tensor) -> Tensor:
        return (user_emb * job_emb).sum(dim=-1)
