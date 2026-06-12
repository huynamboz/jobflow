"""Fernet encryption for employee mail credentials (026).

Single symmetric key in env MAIL_CRED_KEY. Fail-loud if missing — a silent
empty key would mean unprotected secrets at rest.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("MAIL_CRED_KEY", "")
    if not key:
        raise RuntimeError(
            "MAIL_CRED_KEY is not set — cannot encrypt/decrypt mail credentials. "
            "Generate one: python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
