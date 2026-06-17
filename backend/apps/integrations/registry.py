"""Platform registry — the single source of truth for which channels exist,
what config each needs, and which fields are secret (never returned to the FE).

The FE has its own copy of labels/placeholders for the form UI; the backend
only cares about: field keys, which are required, and which are secret.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    required: bool = False
    secret: bool = False  # masked on read; preserved on update when left blank


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    fields: tuple[Field, ...]

    def secret_keys(self) -> set[str]:
        return {f.key for f in self.fields if f.secret}

    def required_keys(self) -> list[str]:
        return [f.key for f in self.fields if f.required]

    def allowed_keys(self) -> set[str]:
        return {f.key for f in self.fields}


PLATFORMS: dict[str, Platform] = {
    p.id: p
    for p in [
        Platform("slack", "Slack", (
            Field("webhook_url", required=True, secret=True),
            Field("channel"),
        )),
        Platform("telegram", "Telegram", (
            Field("bot_token", required=True, secret=True),
            Field("chat_id", required=True),
        )),
        Platform("discord", "Discord", (
            Field("webhook_url", required=True, secret=True),
        )),
        Platform("whatsapp", "WhatsApp", (
            Field("phone_number_id", required=True),
            Field("access_token", required=True, secret=True),
            Field("recipient", required=True),
        )),
        # Zalo uses the personal-account sidecar (zca-js); the session lives in
        # the sidecar, so here we only need WHO to send to.
        Platform("zalo", "Zalo", (
            Field("recipient", required=True),
            Field("thread_type"),
        )),
        Platform("gmail", "Gmail", (
            Field("email", required=True),
            Field("app_password", required=True, secret=True),
        )),
        Platform("email", "Email (SMTP)", (
            Field("host", required=True),
            Field("port", required=True),
            Field("username", required=True),
            Field("password", required=True, secret=True),
            Field("from_address", required=True),
        )),
    ]
}


def get_platform(platform_id: str) -> Platform | None:
    return PLATFORMS.get(platform_id)
