from ml_service.embedding.base import EmbeddingProvider

_REGISTRY: dict[str, type[EmbeddingProvider]] = {}


def _ensure_registry() -> None:
    if _REGISTRY:
        return
    from ml_service.embedding.bge import BgeSmallProvider
    from ml_service.embedding.english import EnglishProvider
    from ml_service.embedding.multilingual import MultilingualProvider

    _REGISTRY["english"] = EnglishProvider
    _REGISTRY["multilingual"] = MultilingualProvider
    _REGISTRY["bge-small"] = BgeSmallProvider


def get_provider(name: str | None = None) -> EmbeddingProvider:
    """Instantiate an EmbeddingProvider by name.

    If *name* is None, reads from Settings.embedding_provider.
    """
    if name is None:
        from ml_service.config import get_settings

        name = get_settings().embedding_provider

    _ensure_registry()
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown embedding provider: {name!r}. Available: {list(_REGISTRY)}")
    return cls()
