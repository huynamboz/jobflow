"""Validate a Gmail app-password by really logging in (026 FR-001/R5).

Both channels must work — a credential that can send but not be polled (or vice
versa) is useless. Failure raises ProbeError with the provider's message; the
caller stores nothing.
"""
from __future__ import annotations

import imaplib
import smtplib

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
IMAP_HOST, IMAP_PORT = "imap.gmail.com", 993


class ProbeError(Exception):
    pass


def probe(address: str, app_password: str) -> None:
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(address, app_password)
    except Exception as e:  # noqa: BLE001
        raise ProbeError(f"SMTP login failed: {e}") from e
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        try:
            m.login(address, app_password)
        finally:
            m.logout()
    except Exception as e:  # noqa: BLE001
        raise ProbeError(f"IMAP login failed: {e}") from e
