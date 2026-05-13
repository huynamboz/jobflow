"""Playwright Chromium context manager.

Loads the saved auth state, yields a Page, and conditionally persists the
storage state on exit — never if the session lost ``li_at``. One context
per batch — the caller iterates URLs inside
``with open_browser_page(...) as page:``.

Spec: 002-job-date-posted-extraction (US3).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from ml_service.verifier.auth_guard import has_li_at, persist_state, read_state

logger = logging.getLogger(__name__)


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class AuthStateMissingError(RuntimeError):
    """Raised by :func:`open_browser_page` when the saved auth state has no
    ``li_at`` cookie. The operator must re-run ``linkedin_auth``.
    """


@contextmanager
def open_browser_page(
    storage_state_path: str,
    *,
    headless: bool = True,
    user_agent: str = _DEFAULT_UA,
    viewport: tuple[int, int] = (1280, 900),
) -> Iterator:
    """Yield ``(page, ctx)`` so callers can both navigate and re-check cookies.

    Verifies the auth-state invariant at entry: if the saved state lacks
    ``li_at``, raises :class:`AuthStateMissingError` before launching the
    browser (no I/O wasted, no chance of guest-rendered pages).

    On exit, persists the current cookie state only if ``li_at`` is still
    present; otherwise leaves the on-disk file untouched.
    """
    # Pre-flight invariant check — fail fast, no browser launch.
    state = read_state(storage_state_path)
    if state is None:
        raise AuthStateMissingError(
            "Auth state missing li_at — re-run "
            "`python -m ml_service.crawler.providers.linkedin_auth`"
        )

    # Use patchright (stealth Playwright fork) to bypass Google/LinkedIn
    # anti-automation detection. API is identical to playwright.sync_api.
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context(
                storage_state=storage_state_path,
                viewport={"width": viewport[0], "height": viewport[1]},
                user_agent=user_agent,
            )
            page = ctx.new_page()
            try:
                yield page, ctx
            finally:
                # Conditional persist — only if li_at survives.
                try:
                    current = ctx.storage_state()
                    persist_state(storage_state_path, current)
                except Exception:
                    logger.exception(
                        "Failed to evaluate storage state at exit; on-disk file unchanged"
                    )
        finally:
            browser.close()


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
