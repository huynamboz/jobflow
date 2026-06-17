"""Integration models — one row per connected delivery channel.

The whole config dict (which holds secrets like webhook URLs, bot tokens,
SMTP passwords) is stored as a single Fernet-encrypted JSON blob. We reuse
apps.mail.crypto, which is keyed off MAIL_CRED_KEY (fail-loud if missing) —
so secrets are encrypted at rest with the same guarantees as mail creds.
"""
from __future__ import annotations

import json

from django.db import models

from apps.mail import crypto


class Integration(models.Model):
    STATUS_CONNECTED = "connected"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [(STATUS_CONNECTED, "Connected"), (STATUS_ERROR, "Error")]

    # Platform slug (slack/telegram/discord/whatsapp/zalo/gmail/email).
    # One integration per platform — see registry.PLATFORMS.
    platform = models.CharField(max_length=20, unique=True)
    # Fernet ciphertext of json.dumps(config). NEVER serialize this column raw.
    config_encrypted = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_CONNECTED)
    last_error = models.TextField(blank=True, default="")
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integrations"
        ordering = ["platform"]

    # --- config (encrypted JSON) helpers ---
    def set_config(self, config: dict) -> None:
        self.config_encrypted = crypto.encrypt(json.dumps(config))

    def get_config(self) -> dict:
        if not self.config_encrypted:
            return {}
        return json.loads(crypto.decrypt(self.config_encrypted))

    def __repr__(self) -> str:  # never leak the secret blob
        return f"<Integration {self.platform} [{self.status}]>"

    __str__ = __repr__
