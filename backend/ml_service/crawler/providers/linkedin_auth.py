"""LinkedIn auth — open browser for manual login, save session state.

Uses patchright (stealth Playwright fork) with launch_persistent_context for
maximum anti-detection, so Google OAuth login is not flagged as automation.

Usage:
    cd backend
    .venv/bin/python -m ml_service.crawler.providers.linkedin_auth

Opens Chromium → you login (Google OAuth supported) → cookies/state saved to
auth/linkedin_state.json. Next crawl loads this state automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path

from patchright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

AUTH_DIR = Path(__file__).resolve().parent.parent.parent.parent / "auth"
STATE_FILE = AUTH_DIR / "linkedin_state.json"
USER_DATA_DIR = AUTH_DIR / "chromium_profile"


def login_and_save() -> None:
    """Open a persistent Chromium profile for manual LinkedIn login.

    Persistent context is patchright's recommended pattern for stealth: it
    keeps a real browser-like profile between runs and avoids the
    new_context fingerprints that Google's anti-bot pipeline flags.
    After login, the context's storage_state is exported to STATE_FILE so
    the verifier/extractor (which use launch + new_context with
    storage_state) can read it without changes.
    """
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  LinkedIn Login (patchright + persistent profile)")
    print("=" * 60)
    print(f"  Profile dir : {USER_DATA_DIR}")
    print(f"  State file  : {STATE_FILE}")
    print("  1. Browser opens LinkedIn login page (Google OAuth supported)")
    print("  2. Login with your account")
    print("  3. Press Enter here when done")
    print("=" * 60)

    with sync_playwright() as p:
        # Patchright stealth recommendation: persistent context, no custom
        # user_agent (let the real Chromium UA through), default viewport.
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chromium",
            headless=False,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/login")

        print("\n>>> Waiting for you to login... Press Enter here when done.")
        input()

        # Export storage state to JSON so the verifier/extractor pipeline
        # (which uses launch + new_context with storage_state=path) works
        # unchanged.
        context.storage_state(path=str(STATE_FILE))
        print(f"\n✅ Auth state saved to {STATE_FILE}")

        context.close()


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
