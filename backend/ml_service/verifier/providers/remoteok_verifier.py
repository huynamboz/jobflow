"""RemoteOK job-status verifier — HTTP presence (no browser, no auth).

Removed RemoteOK listings return HTTP 404 (or redirect off the slug, which ends
in the numeric job id); live ones serve the job page at 200. So a plain GET
classifies the listing — see ``ml_service.verifier.http_presence.HttpPresenceVerifier``.

The expired-text markers are a secondary net only; they were verified absent
from a live RemoteOK page so they never false-positive an active listing.
"""

from __future__ import annotations

from ml_service.verifier.http_presence import HttpPresenceVerifier


class RemoteOKVerifier(HttpPresenceVerifier):
    _NAME = "remoteok"
    _URL_PATTERNS = ("remoteok.com", "remoteok.io")
    _EXPIRED_MARKERS = (
        "this job is no longer",
        "no longer available",
        "no longer accepting applications",
        "position has been filled",
        "this job post has expired",
    )
    # RemoteOK lazy-loads the company logo: the real URL sits in data-src of the
    # itemprop=image avatar (src is a pixel.gif placeholder).
    _LOGO_SELECTOR = "img[itemprop='image']"
    _LOGO_ATTR = "data-src"
