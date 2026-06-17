"""Per-platform message delivery.

Each sender takes the decrypted config dict + a plain-text message and performs
a real outbound call. Raises DeliveryError (with a human message) on failure so
views/commands can surface a clear reason and flag the integration as errored.
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests

TIMEOUT = 12


class DeliveryError(Exception):
    """Human-readable delivery failure."""


# --- HTTP webhook / bot senders -------------------------------------------------

def _post_json(url: str, payload: dict) -> None:
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:  # network/DNS/timeout
        raise DeliveryError(f"Network error: {e}") from e
    if r.status_code >= 300:
        raise DeliveryError(f"HTTP {r.status_code}: {r.text[:300]}")


def _send_slack(cfg: dict, text: str, blocks: list | None = None) -> None:
    # `text` is kept as the notification fallback even when blocks are present.
    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    _post_json(cfg["webhook_url"], payload)


def _send_discord(cfg: dict, text: str) -> None:
    _post_json(cfg["webhook_url"], {"content": text})


def _send_telegram(cfg: dict, text: str) -> None:
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": cfg["chat_id"], "text": text}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DeliveryError(f"Network error: {e}") from e
    if r.status_code >= 300:
        # Telegram returns a JSON {description: ...} on error
        try:
            desc = r.json().get("description", r.text[:300])
        except ValueError:
            desc = r.text[:300]
        raise DeliveryError(f"Telegram error: {desc}")


def _send_whatsapp(cfg: dict, text: str) -> None:
    url = f"https://graph.facebook.com/v18.0/{cfg['phone_number_id']}/messages"
    headers = {"Authorization": f"Bearer {cfg['access_token']}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": cfg["recipient"],
        "type": "text",
        "text": {"body": text},
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DeliveryError(f"Network error: {e}") from e
    if r.status_code >= 300:
        raise DeliveryError(f"WhatsApp API HTTP {r.status_code}: {r.text[:300]}")


def _send_zalo(cfg: dict, text: str) -> None:
    """Send via the personal-account Zalo sidecar (zca-js). The sidecar holds
    the session; we only pass the recipient threadId + message."""
    from django.conf import settings

    recipient = (cfg.get("recipient") or "").strip()
    if not recipient:
        raise DeliveryError(
            "Zalo cần 'recipient' (threadId của user/nhóm) để gửi tin. "
            "Xem backend/zalo_sidecar/README.md để lấy threadId."
        )
    base = (settings.ZALO_SIDECAR_URL or "").rstrip("/")
    if not base:
        raise DeliveryError("ZALO_SIDECAR_URL chưa được cấu hình.")
    headers = {}
    if settings.ZALO_SIDECAR_TOKEN:
        headers["x-sidecar-token"] = settings.ZALO_SIDECAR_TOKEN
    payload = {"threadId": recipient, "threadType": cfg.get("thread_type", "user"), "message": text}
    try:
        r = requests.post(f"{base}/send", json=payload, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DeliveryError(f"Không kết nối được Zalo sidecar ({base}): {e}") from e
    if r.status_code >= 300:
        try:
            err = r.json().get("error", r.text[:300])
        except ValueError:
            err = r.text[:300]
        raise DeliveryError(f"Zalo sidecar error (HTTP {r.status_code}): {err}")


# --- SMTP senders ---------------------------------------------------------------

def _smtp_send(host: str, port: int, user: str, password: str,
               from_addr: str, to_addr: str, subject: str, text: str) -> None:
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, port, timeout=TIMEOUT) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass  # server without STARTTLS (rare); proceed plaintext
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise DeliveryError(f"Auth failed: {e.smtp_error.decode(errors='ignore') if hasattr(e, 'smtp_error') else e}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise DeliveryError(f"SMTP error: {e}") from e


def _send_gmail(cfg: dict, text: str, subject: str) -> None:
    addr = cfg["email"]
    _smtp_send("smtp.gmail.com", 587, addr, (cfg["app_password"] or "").replace(" ", ""),
               addr, addr, subject, text)


def _send_email(cfg: dict, text: str, subject: str) -> None:
    _smtp_send(cfg["host"], int(cfg["port"]), cfg.get("username", ""), cfg.get("password", ""),
               cfg["from_address"], cfg["from_address"], subject, text)


# --- dispatch -------------------------------------------------------------------

def deliver(platform: str, config: dict, text: str, subject: str = "JobFlow",
            slack_blocks: list | None = None) -> None:
    """Send `text` to one platform using its config. Raises DeliveryError on failure.

    `slack_blocks` (Block Kit) is used only by Slack for rich formatting; every
    other platform falls back to the plain-text `text`."""
    if platform == "slack":
        _send_slack(config, text, slack_blocks)
    elif platform == "discord":
        _send_discord(config, text)
    elif platform == "telegram":
        _send_telegram(config, text)
    elif platform == "whatsapp":
        _send_whatsapp(config, text)
    elif platform == "zalo":
        _send_zalo(config, text)
    elif platform == "gmail":
        _send_gmail(config, text, subject)
    elif platform == "email":
        _send_email(config, text, subject)
    else:
        raise DeliveryError(f"Unknown platform: {platform}")
