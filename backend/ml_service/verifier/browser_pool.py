"""Playwright Chromium context manager — patchright stealth, persistent profile.

Background: LinkedIn detects automation in fresh ``launch + new_context``
sessions even with patchright's stealth patches. It responds by clearing
the ``li_at`` cookie after 1-2 page loads, ending the batch early.

Fix: use ``launch_persistent_context`` (patchright's strongest stealth
pattern), pointed at a *copy* of the operator's logged-in profile. Each
batch gets a fresh disposable copy so that whatever LinkedIn does to the
in-batch cookies cannot corrupt the source profile. The on-disk
``linkedin_state.json`` file is also exported on exit (guarded by the
``li_at`` invariant) so older code paths reading it continue to work.

Spec: 002-job-date-posted-extraction (US3) + post-impl stealth upgrade.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ml_service.verifier.auth_guard import has_li_at, persist_state, read_state

logger = logging.getLogger(__name__)


class AuthStateMissingError(RuntimeError):
    """Raised by :func:`open_browser_page` when the saved auth state has no
    ``li_at`` cookie. The operator must re-run ``linkedin_auth``.
    """


def _resolve_user_data_dir(storage_state_path: str) -> Path:
    """Look up the persistent profile directory alongside the storage_state
    file. By convention from ``linkedin_auth.py``:

        backend/auth/linkedin_state.json
        backend/auth/chromium_profile/
    """
    return Path(storage_state_path).parent / "chromium_profile"


@contextmanager
def open_browser_page(
    storage_state_path: str,
    *,
    headless: bool = True,
    viewport: tuple[int, int] | None = None,
) -> Iterator:
    """Yield ``(page, ctx)`` so callers can both navigate and re-check cookies.

    Lifecycle:
        1. Validate the saved auth state has ``li_at`` (raise
           :class:`AuthStateMissingError` if not).
        2. Copy ``backend/auth/chromium_profile/`` to a temp dir so the
           operator's source profile is untouchable by the batch.
        3. Launch a *persistent context* against the copy (patchright
           stealth recommendation).
        4. Yield ``(page, ctx)``.
        5. On exit, export the (potentially rotated) storage state to the
           on-disk file — but only if ``li_at`` survived; if it didn't, the
           on-disk file is preserved untouched.
        6. Delete the temp profile.
    """
    # ── 1. Auth invariant ────────────────────────────────────────────────
    state = read_state(storage_state_path)
    if state is None:
        raise AuthStateMissingError(
            "Auth state missing li_at — re-run "
            "`python -m ml_service.crawler.providers.linkedin_auth`"
        )

    source_profile = _resolve_user_data_dir(storage_state_path)
    if not source_profile.exists():
        raise AuthStateMissingError(
            f"Persistent profile not found at {source_profile} — "
            "re-run `python -m ml_service.crawler.providers.linkedin_auth`"
        )

    # ── 2. Disposable copy of the profile ────────────────────────────────
    tmp_root = Path(tempfile.mkdtemp(prefix="linkedin_batch_"))
    tmp_profile = tmp_root / "profile"
    try:
        shutil.copytree(source_profile, tmp_profile)
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise

    # ── 3. Launch persistent context ─────────────────────────────────────
    # Patchright stealth recommendation: launch_persistent_context, no
    # custom user_agent (let real Chromium UA through), no_viewport so the
    # browser picks its natural size.
    from patchright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            launch_kwargs: dict = {
                "user_data_dir": str(tmp_profile),
                "channel": "chromium",
                "headless": headless,
                "no_viewport": viewport is None,
            }
            if viewport is not None:
                launch_kwargs["viewport"] = {"width": viewport[0], "height": viewport[1]}

            ctx = p.chromium.launch_persistent_context(**launch_kwargs)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                try:
                    yield page, ctx
                finally:
                    # ── 5. Conditional persist back to source path ──────
                    try:
                        current = ctx.storage_state()
                        persist_state(storage_state_path, current)
                    except Exception:
                        logger.exception(
                            "Failed to evaluate storage state at exit; on-disk file unchanged"
                        )
            finally:
                ctx.close()
    finally:
        # ── 6. Discard the temp profile ──────────────────────────────────
        shutil.rmtree(tmp_root, ignore_errors=True)


def cookies_have_li_at(ctx) -> bool:
    """Helper for mid-batch session-loss detection. Pass a Playwright
    BrowserContext; returns True iff its current cookies contain ``li_at``
    on a linkedin.com domain.
    """
    try:
        cookies = ctx.cookies()
    except Exception:
        return False
    return has_li_at({"cookies": cookies})
