"""Unit tests for ml_service.verifier.auth_guard.

Spec: 002-job-date-posted-extraction (US3).

These tests never touch Playwright. They exercise the pure invariant and
the file-persist guard via tempfiles.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml_service.verifier.auth_guard import has_li_at, persist_state, read_state


# ─── has_li_at ────────────────────────────────────────────────────────────


def test_has_li_at_true_when_cookie_present():
    state = {"cookies": [
        {"name": "li_at", "value": "AQE...", "domain": ".linkedin.com"},
        {"name": "other", "value": "x", "domain": ".linkedin.com"},
    ]}
    assert has_li_at(state) is True


def test_has_li_at_false_when_cookies_empty():
    assert has_li_at({"cookies": []}) is False


def test_has_li_at_false_when_no_li_at_cookie():
    state = {"cookies": [
        {"name": "bcookie", "value": "x", "domain": ".linkedin.com"},
        {"name": "JSESSIONID", "value": "y", "domain": ".www.linkedin.com"},
    ]}
    assert has_li_at(state) is False


def test_has_li_at_false_when_li_at_on_wrong_domain():
    state = {"cookies": [
        {"name": "li_at", "value": "x", "domain": ".facebook.com"},
    ]}
    assert has_li_at(state) is False


def test_has_li_at_false_on_none_or_garbage():
    assert has_li_at(None) is False
    assert has_li_at({}) is False
    assert has_li_at({"cookies": "not-a-list"}) is False
    assert has_li_at({"cookies": [None, "junk"]}) is False


# ─── read_state ───────────────────────────────────────────────────────────


def _write(tmp: Path, payload):
    path = tmp / "state.json"
    path.write_text(json.dumps(payload))
    return path


def test_read_state_returns_none_when_invariant_broken(tmp_path):
    """T005: tempfile lacks li_at → read_state returns None."""
    path = _write(tmp_path, {"cookies": [{"name": "lidc", "domain": ".linkedin.com"}]})
    assert read_state(path) is None


def test_read_state_returns_state_when_invariant_holds(tmp_path):
    path = _write(tmp_path, {"cookies": [{"name": "li_at", "domain": ".linkedin.com"}]})
    state = read_state(path)
    assert state is not None
    assert state["cookies"][0]["name"] == "li_at"


def test_read_state_returns_none_when_file_missing(tmp_path):
    assert read_state(tmp_path / "does-not-exist.json") is None


def test_read_state_returns_none_on_broken_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json}")
    assert read_state(path) is None


# ─── persist_state ────────────────────────────────────────────────────────


def test_persist_state_skipped_when_invariant_broken(tmp_path):
    """T006: file with valid li_at is preserved when current state has no li_at."""
    saved_path = _write(
        tmp_path,
        {"cookies": [{"name": "li_at", "domain": ".linkedin.com", "value": "ORIGINAL"}]},
    )
    original = saved_path.read_text()
    # Simulate: browser session ended without li_at (the bug we're fixing).
    new_state = {"cookies": [{"name": "lidc", "domain": ".linkedin.com"}]}
    written = persist_state(saved_path, new_state)
    assert written is False
    # File is byte-identical.
    assert saved_path.read_text() == original


def test_persist_state_writes_when_invariant_holds(tmp_path):
    """T007: file is updated when current state still has li_at."""
    saved_path = _write(
        tmp_path,
        {"cookies": [{"name": "li_at", "domain": ".linkedin.com", "value": "ORIGINAL"}]},
    )
    new_state = {
        "cookies": [
            {"name": "li_at", "domain": ".linkedin.com", "value": "ROTATED"},
            {"name": "JSESSIONID", "domain": ".www.linkedin.com", "value": "new"},
        ]
    }
    written = persist_state(saved_path, new_state)
    assert written is True
    loaded = json.loads(saved_path.read_text())
    li_at = next(c for c in loaded["cookies"] if c["name"] == "li_at")
    assert li_at["value"] == "ROTATED"


def test_persist_state_returns_false_on_unwritable_path(tmp_path):
    state = {"cookies": [{"name": "li_at", "domain": ".linkedin.com"}]}
    # Path under a non-existent dir → write fails
    bad = tmp_path / "does-not-exist-dir" / "state.json"
    assert persist_state(bad, state) is False
