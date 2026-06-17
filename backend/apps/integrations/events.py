"""Notification event types a channel can subscribe to.

Each connected integration stores an on/off flag per event (see Integration.events).
Missing keys default to ON, so older rows keep receiving everything.
"""
from __future__ import annotations

# event key -> stable identifier used in the events JSON + API
MAIL_REPLY = "mail_reply"   # an incoming email reply was detected
MAIL_SENT = "mail_sent"     # an apply email was sent
NEW_MATCH = "new_match"     # morning digest / new matching jobs

EVENT_KEYS = [MAIL_REPLY, MAIL_SENT, NEW_MATCH]

DEFAULT_EVENTS = {k: True for k in EVENT_KEYS}


def normalize_events(events: dict | None) -> dict:
    """Return a dict with every known key present (missing → True)."""
    events = events or {}
    return {k: bool(events.get(k, True)) for k in EVENT_KEYS}
