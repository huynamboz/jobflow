"""Send an application email AS the employee (026 FR-004/R4).

smtplib STARTTLS gmail; From = employee's linked address; CV attached from
Employee.cv_file; self-generated Message-ID is stored so replies can be matched.
"""
from __future__ import annotations

import mimetypes
import smtplib
import uuid
from email.message import EmailMessage

from apps.mail.models import EmailLog
from apps.mail.services.probe import SMTP_HOST, SMTP_PORT


def _new_message_id() -> str:
    return f"<{uuid.uuid4().hex}@jobflow.local>"


def send_apply_email(*, credential, employee, match, to_addr, subject, body,
                     cv_override=None, attach_cv=True) -> EmailLog:
    """Send + persist EmailLog(out). Raises on SMTP failure (caller flags cred,
    does NOT mark the match applied).

    Attachment: ``cv_override`` (an uploaded file) wins; else the employee's
    active CV is attached when ``attach_cv`` is True; ``attach_cv=False`` sends
    with no CV (HR removed it on the compose screen)."""
    msg = EmailMessage()
    message_id = _new_message_id()
    msg["Message-ID"] = message_id
    msg["From"] = credential.gmail_address
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    cv_attached = False
    if cv_override is not None:
        # HR uploaded a replacement file on the compose screen.
        try:
            data = cv_override.read()
            fname = (getattr(cv_override, "name", "") or "cv.pdf").split("/")[-1]
            ctype = (getattr(cv_override, "content_type", None)
                     or mimetypes.guess_type(fname)[0] or "application/octet-stream")
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)
            cv_attached = True
        except Exception:  # noqa: BLE001
            cv_attached = False
    elif attach_cv:
        cv = getattr(employee, "cv_file", None)
        if cv:
            try:
                cv.open("rb")
                data = cv.read()
                cv.close()
                ctype, _ = mimetypes.guess_type(cv.name)
                maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
                fname = cv.name.split("/")[-1]
                msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)
                cv_attached = True
            except Exception:  # noqa: BLE001 — missing/broken CV → send without it
                cv_attached = False

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(credential.gmail_address, credential.get_password())
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        EmailLog.objects.create(
            employee=employee, match=match, direction=EmailLog.OUT,
            from_addr=credential.gmail_address, to_addr=to_addr, subject=subject,
            body_text=body, message_id=message_id, cv_attached=cv_attached,
            status=EmailLog.FAILED, error=str(e),
        )
        raise

    log = EmailLog.objects.create(
        employee=employee, match=match, direction=EmailLog.OUT,
        from_addr=credential.gmail_address, to_addr=to_addr, subject=subject,
        body_text=body, message_id=message_id, cv_attached=cv_attached,
        status=EmailLog.SENT,
    )
    _notify_sent(employee, to_addr, subject)
    return log


def _notify_sent(employee, to_addr: str, subject: str) -> None:
    """Push a 'mail_sent' notification to subscribed integration channels."""
    try:
        from apps.integrations.events import MAIL_SENT
        from apps.integrations.services.digest import notify_event

        text = (f"📤 Đã gửi email ứng tuyển cho {employee.full_name}\n"
                f"Tới: {to_addr}\nTiêu đề: {subject}")
        notify_event(MAIL_SENT, text, subject="JobFlow — Mail sent")
    except Exception:  # noqa: BLE001 — never let notify break sending
        pass
