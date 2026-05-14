"""LinkedIn auth-state invariant.

The saved Playwright storage_state file ``backend/auth/linkedin_state.json``
must contain a ``li_at`` cookie scoped to a ``linkedin.com`` domain. Without
it the session is anonymous and pages render the guest layout, which
silently degrades every downstream verifier/extractor decision.

This module owns the invariant. Every code path that loads or persists
the auth state MUST go through one of:

- :func:`has_li_at` (pure check on a state dict)
- :func:`read_state` (load + invariant check)
- :func:`persist_state` (write only if invariant holds)

Spec: 002-job-date-posted-extraction (US3, FR-012/013).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def has_li_at(state: dict[str, Any] | None) -> bool:
    """Return True iff ``state`` contains a ``li_at`` cookie on a
    ``linkedin.com`` domain.

    Pure; no I/O, no logging at WARN+.
    """
    if not state or not isinstance(state, dict):
        return False
    cookies = state.get("cookies") or []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        if c.get("name") != "li_at":
            continue
        domain = (c.get("domain") or "").lower()
        if "linkedin.com" in domain:
            return True
    return False


def read_state(path: str | Path) -> dict[str, Any] | None:
    """Load the storage_state file. Return the parsed dict iff
    :func:`has_li_at` is True. Otherwise return None and log WARNING.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open() as f:
            state = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to read auth state from %s: %s", p, e)
        return None
    if not has_li_at(state):
        logger.warning(
            "Auth state at %s is missing the li_at cookie — re-run "
            "`python -m ml_service.crawler.providers.linkedin_auth`",
            p,
        )
        return None
    return state


def persist_state(path: str | Path, state: dict[str, Any]) -> bool:
    """Write ``state`` to ``path`` iff it still contains ``li_at``.

    Returns True if the file was written. Returns False (no write) if the
    invariant fails — protects the on-disk file from being silently
    overwritten with anonymous cookies.
    """
    if not has_li_at(state):
        logger.warning(
            "Refusing to persist auth state to %s: current session lacks "
            "li_at cookie. The saved file is preserved.",
            path,
        )
        return False
    try:
        Path(path).write_text(json.dumps(state))
        return True
    except Exception:
        logger.exception("Failed to persist auth state to %s", path)
        return False
