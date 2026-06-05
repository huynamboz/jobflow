from abc import ABC, abstractmethod

import numpy as np


class EmbeddingProvider(ABC):
    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into embedding vectors.

        Returns:
            np.ndarray of shape (len(texts), dim).
        """

    @property
    @abstractmethod
    def dim(self) -> int:
        """Dimensionality of the embedding vectors."""
