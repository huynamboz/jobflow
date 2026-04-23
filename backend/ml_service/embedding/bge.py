import numpy as np
from sentence_transformers import SentenceTransformer

from ml_service.embedding.base import EmbeddingProvider

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_DIM = 384


class BgeSmallProvider(EmbeddingProvider):
    """BGE-small-en-v1.5 embedding provider.

    Same dim as MiniLM (384) but significantly better on MTEB benchmarks.
    Drop-in replacement: no graph rebuild needed when switching from EnglishProvider.
    """

    def __init__(self) -> None:
        self._model = SentenceTransformer(_MODEL_NAME)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    @property
    def dim(self) -> int:
        return _DIM
