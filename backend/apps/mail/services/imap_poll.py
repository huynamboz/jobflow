"""Poll IMAP for replies to mail WE sent (026 FR-006/R2/R3/R6).

Privacy discipline: read each new message's headers only; fetch+store the body
ONLY when In-Reply-To/References intersects a known sent Message-ID. BODY.PEEK +
readonly SELECT → never marks the employee's mail as read.
"""
from __future__ import annotations

import email
import imaplib
import logging
import time
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from django.utils import timezone

from apps.mail.models import EmailLog, Notification
from apps.mail.services.probe import IMAP_HOST, IMAP_PORT

logger = logging.getLogger(__name__)
_BOUNCE_SENDERS = ("mailer-daemon@", "postmaster@")


def _decode(raw: str) -> str:
    """RFC2047 → unicode (Gmail encodes non-ASCII subjects as =?UTF-8?...?=)."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001
        return raw


def _refs(msg) -> set[str]:
    out: set[str] = set()
    for h in ("In-Reply-To", "References"):
        v = msg.get(h, "")
        out.update(t for t in v.replace(",", " ").split() if t.startswith("<"))
    return out


def poll_credential(credential) -> int:
    """Returns number of new reply/bounce EmailLog(in) rows created."""
    sent = dict(  # message_id -> EmailLog(out)
        EmailLog.objects.filter(employee=credential.employee, direction=EmailLog.OUT)
        .values_list("message_id", "id")
    )
    if not sent:
        return 0
    sent_ids = set(sent)

    # Gmail IMAP occasionally drops the TLS handshake (SSLEOFError) — a transient
    # blip must NOT flag the account as errored. Retry a couple of times first.
    m = None
    for attempt in range(3):
        try:
            m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            m.login(credential.gmail_address, credential.get_password())
            break
        except (imaplib.IMAP4.abort, OSError) as e:
            logger.warning("IMAP connect retry %d for %s: %s", attempt + 1, credential.gmail_address, e)
            try:
                if m: m.logout()
            except Exception:  # noqa: BLE001
                pass
            m = None
            if attempt == 2:
                raise
            time.sleep(2)
    created = 0
    try:
        m.select("INBOX", readonly=True)
        # SINCE window from the poll watermark (1-day back-buffer for safety),
        # not updated_at (which bumps on unrelated saves).
        watermark = credential.last_polled_at or (timezone.now() - timezone.timedelta(days=1))
        since = (watermark - timezone.timedelta(days=1)).strftime("%d-%b-%Y")
        typ, data = m.search(None, f'(SINCE {since})')
        if typ != "OK":
            return 0
        for uid in data[0].split():
            typ, hdr = m.fetch(uid, "(BODY.PEEK[HEADER])")
            if typ != "OK" or not hdr or not hdr[0]:
                continue
            head = email.message_from_bytes(hdr[0][1])
            matched = _refs(head) & sent_ids
            if not matched:
                continue  # not a reply to our mail — never fetch body
            in_reply_to = sorted(matched)[0]
            if EmailLog.objects.filter(employee=credential.employee, direction=EmailLog.IN,
                                       message_id=head.get("Message-ID", "")).exists():
                continue  # already recorded
            typ, full = m.fetch(uid, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            full_msg = email.message_from_bytes(full[0][1])
            body = _plain_body(full_msg)
            from_addr = email.utils.parseaddr(full_msg.get("From", ""))[1]
            is_bounce = any(b in from_addr.lower() for b in _BOUNCE_SENDERS)
            out_log = EmailLog.objects.filter(pk=sent[in_reply_to]).first()
            log = EmailLog.objects.create(
                employee=credential.employee,
                match=out_log.match if out_log else None,
                direction=EmailLog.IN, from_addr=from_addr,
                to_addr=credential.gmail_address,
                subject=_decode(full_msg.get("Subject", "")), body_text=body,
                message_id=full_msg.get("Message-ID", ""), in_reply_to=in_reply_to,
                is_bounce=is_bounce, status=EmailLog.RECEIVED,
            )
            emp = credential.employee
            link = f"/admin/employees/{emp.id}" + (f"?match={log.match_id}" if log.match_id else "")
            Notification.objects.create(
                type=Notification.MAIL_BOUNCE if is_bounce else Notification.MAIL_REPLY,
                title=("Delivery failed" if is_bounce else "Reply from recruiter")
                      + f" — {emp.full_name}",
                body_preview=(body or "")[:160], link_url=link, employee=emp,
            )
            created += 1
    finally:
        try:
            m.logout()
        except Exception:  # noqa: BLE001
            pass
    credential.last_polled_at = timezone.now()
    credential.save(update_fields=["last_polled_at"])
    return created


def _plain_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="replace")
                except Exception:  # noqa: BLE001
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(errors="replace")
    except Exception:  # noqa: BLE001
        return msg.get_payload() if isinstance(msg.get_payload(), str) else ""
