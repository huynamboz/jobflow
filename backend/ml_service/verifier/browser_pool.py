"""Playwright Chromium context manager.

Loads the saved auth state, yields a Page, and persists the (possibly
refreshed) storage state on exit. One context per batch — the caller
iterates URLs inside ``with PlaywrightBrowserPool(...) as page:``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@contextmanager
def open_browser_page(
    storage_state_path: str,
    *,
    headless: bool = True,
    user_agent: str = _DEFAULT_UA,
    viewport: tuple[int, int] = (1280, 900),
) -> Iterator:
    """Yield a Playwright Page backed by a Chromium browser context loaded
    with the given storage state. Refreshes storage state on exit.
    """
    from playwright.sync_api import sync_playwright

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
                yield page
            finally:
                # Persist cookies that may have rotated during the session.
                try:
                    ctx.storage_state(path=storage_state_path)
                except Exception:
                    logger.exception("Failed to persist storage state to %s", storage_state_path)
        finally:
            browser.close()
