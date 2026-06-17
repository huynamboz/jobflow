"""Serialization for integrations — secrets are NEVER returned, only a
`secrets_set` list telling the FE which secret fields already have a value
(so it can show a "saved" placeholder)."""
from __future__ import annotations

from apps.integrations.models import Integration
from apps.integrations.registry import Platform


def serialize_platform(platform: Platform, row: Integration | None) -> dict:
    """One platform's public state. Non-secret config values are echoed back;
    secret values are replaced by a boolean presence flag."""
    cfg = row.get_config() if row else {}
    secret_keys = platform.secret_keys()
    public_config = {k: v for k, v in cfg.items() if k not in secret_keys}
    return {
        "platform": platform.id,
        "name": platform.name,
        "connected": row is not None,
        "status": row.status if row else None,
        "last_error": row.last_error if row else "",
        "last_sent_at": row.last_sent_at if row else None,
        "updated_at": row.updated_at if row else None,
        "config": public_config,
        # which secret fields already hold a value (lets the FE show "•••• saved")
        "secrets_set": sorted(k for k in secret_keys if cfg.get(k)),
    }
