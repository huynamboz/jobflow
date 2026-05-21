import numpy as np

from ml_benchmark.embedding.base import EmbeddingProvider


class MultilingualProvider(EmbeddingProvider):
    """Placeholder — not yet implemented.

    Candidates: LaBSE (best quality), multilingual-e5 (best retrieval).
    """

    def encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError("Multilingual embedding provider is not yet implemented")

    @property
    def dim(self) -> int:
        raise NotImplementedError("Multilingual embedding provider is not yet implemented")
