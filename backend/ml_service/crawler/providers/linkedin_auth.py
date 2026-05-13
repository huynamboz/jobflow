"""LinkedIn auth — open browser for manual login, save session state.

Usage:
    cd backend
    .venv/bin/python -m ml_service.crawler.providers.linkedin_auth

Opens Chromium → you login manually → saves cookies/state to auth/linkedin_state.json
Next crawl loads this state automatically (no login needed).
"""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

AUTH_DIR = Path(__file__).resolve().parent.parent.parent.parent / "auth"
STATE_FILE = AUTH_DIR / "linkedin_state.json"


def login_and_save() -> None:
    """Open browser for manual LinkedIn login, save auth state."""
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  LinkedIn Login")
    print("=" * 60)
    print(f"  State will be saved to: {STATE_FILE}")
    print("  1. Browser will open LinkedIn login page")
    print("  2. Login with your account")
    print("  3. Close the browser when done (or press Enter here)")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")

        print("\n>>> Waiting for you to login... Press Enter here when done.")
        input()

        # Save auth state (cookies + localStorage)
        context.storage_state(path=str(STATE_FILE))
        print(f"\n✅ Auth state saved to {STATE_FILE}")

        browser.close()


def load_state_path() -> str | None:
    """Return path to saved auth state, or None if it doesn't exist OR
    fails the auth invariant (no li_at cookie).

    Delegates to ml_service.verifier.auth_guard.read_state — see spec
    002-job-date-posted-extraction (US3, FR-013).
    """
    if not STATE_FILE.exists():
        return None
    from ml_service.verifier.auth_guard import read_state
    if read_state(STATE_FILE) is None:
        return None
    return str(STATE_FILE)


if __name__ == "__main__":
    login_and_save()
