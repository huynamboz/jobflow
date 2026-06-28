"""Remotive job-status verifier — HTTP presence (no browser, no auth).

Removed Remotive listings 404 or redirect off the job URL; live ones serve the
job page. See ``ml_service.verifier.http_presence.HttpPresenceVerifier``.
"""

from __future__ import annotations

from ml_service.verifier.http_presence import HttpPresenceVerifier


class RemotiveVerifier(HttpPresenceVerifier):
    _NAME = "remotive"
    _URL_PATTERNS = ("remotive.com", "remotive.io")
    _EXPIRED_MARKERS = (
        "this job is no longer",
        "no longer available",
        "position has been filled",
        "job not found",
    )
