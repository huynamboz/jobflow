import numpy as np
from sentence_transformers import SentenceTransformer

from ml_benchmark.embedding.base import EmbeddingProvider

_MODEL_NAME = "all-MiniLM-L6-v2"
_DIM = 384


class EnglishProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._model = SentenceTransformer(_MODEL_NAME)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    @property
    def dim(self) -> int:
        return _DIM
