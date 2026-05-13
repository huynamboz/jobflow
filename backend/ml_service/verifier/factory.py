"""Verifier auto-discovery registry.

Scans ``ml_service/verifier/providers/`` at first call and registers every
non-abstract :class:`JobStatusVerifier` subclass keyed by its ``.name``.
Mirrors the structure of ``ml_service/crawler/factory.py`` so the codebase
stays consistent across the two domains.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from ml_service.verifier.base import JobStatusVerifier

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type[JobStatusVerifier]] = {}
_discovered = False


def _instantiate_for_name(cls: type[JobStatusVerifier]) -> str:
    """Resolve a verifier class's ``.name`` without running side-effecting
    construction. Falls back to the module-derived slug if the class can't
    be instantiated cheaply.
    """
    try:
        instance = cls()  # type: ignore[call-arg]
        return instance.name
    except TypeError:
        # Class requires constructor args — try the no-arg ``__new__`` trick.
        try:
            instance = cls.__new__(cls)
            return instance.name  # type: ignore[attr-defined]
        except Exception:
            return ""


def _discover_providers() -> None:
    global _discovered
    if _discovered:
        return

    providers_path = Path(__file__).parent / "providers"
    if not providers_path.exists():
        _discovered = True
        return

    package_name = "ml_service.verifier.providers"
    for _, module_name, _ in pkgutil.iter_modules([str(providers_path)]):
        try:
            module = importlib.import_module(f"{package_name}.{module_name}")
        except Exception as e:  # noqa: BLE001 — graceful skip per contract
            logger.warning("Failed to load verifier provider module %s: %s", module_name, e)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, JobStatusVerifier) or obj is JobStatusVerifier:
                continue
            if obj.__module__ != module.__name__:
                continue  # imported from elsewhere — skip
            name = _instantiate_for_name(obj) or module_name.replace("_verifier", "")
            if not name:
                logger.warning("Verifier %s has empty name; skipped", obj)
                continue
            if name in _REGISTRY and _REGISTRY[name] is not obj:
                raise ValueError(
                    f"Duplicate verifier name '{name}': "
                    f"{_REGISTRY[name].__name__} vs {obj.__name__}"
                )
            _REGISTRY[name] = obj
            logger.debug("Discovered verifier: %s → %s", name, obj.__name__)

    _discovered = True
    logger.info("Discovered %d job-status verifiers: %s", len(_REGISTRY), list(_REGISTRY.keys()))


def register_verifier(name: str, cls: type[JobStatusVerifier]) -> None:
    """Register a verifier class at runtime. Raises on duplicate name."""
    _discover_providers()
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(
            f"Duplicate verifier name '{name}': existing {_REGISTRY[name].__name__}"
        )
    _REGISTRY[name] = cls


def reset_registry_for_tests() -> None:
    """Clear discovery state. Tests only — never call from production code."""
    global _discovered
    _REGISTRY.clear()
    _discovered = False


def get_verifier(name: str, **kwargs) -> JobStatusVerifier:
    """Instantiate a verifier by name."""
    _discover_providers()
    cls = _REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown verifier '{name}'. Available: {available}")
    return cls(**kwargs)


def get_verifier_for_url(url: str) -> JobStatusVerifier | None:
    """Return the first verifier whose ``supports(url)`` is True, or None."""
    _discover_providers()
    for name, cls in _REGISTRY.items():
        try:
            instance = cls()  # type: ignore[call-arg]
        except TypeError:
            continue
        if instance.supports(url):
            return instance
    return None


def list_verifiers() -> dict[str, type[JobStatusVerifier]]:
    """Return a snapshot of the registry."""
    _discover_providers()
    return dict(_REGISTRY)
