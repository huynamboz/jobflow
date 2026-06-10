import numpy as np

from ml_service.embedding.base import EmbeddingProvider


class MultilingualProvider(EmbeddingProvider):
    """GNN v2/E5 (master plan 3.4): multilingual sentence embeddings.

    paraphrase-multilingual-MiniLM-L12-v2 — 384-dim, drop-in replacement for
    all-MiniLM-L6-v2 (same width → node_dims unchanged), covers Vietnamese
    (~7% of the catalog reads as noise to the English-only model).
    """

    _MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._MODEL)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)

    @property
    def dim(self) -> int:
        return 384
