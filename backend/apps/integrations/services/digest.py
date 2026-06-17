"""Build + broadcast the morning staffing bulletin to connected integrations.

`build_digest()` produces both a plain-text body (Telegram/Discord/WhatsApp/Zalo/
Email) and a Slack Block Kit layout (rich) from the live match catalog — the top
suggestions by calibrated score, plus a short stats line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from apps.integrations.models import Integration
from apps.integrations.services.delivery import DeliveryError, deliver


@dataclass
class DigestPayload:
    subject: str
    text: str
    slack_blocks: list = field(default_factory=list)


def _pct(score: float | None) -> int:
    return round((score or 0) * 100)


def build_digest(top_n: int = 5, new_matches: int | None = None) -> DigestPayload:
    """Assemble the morning bulletin from the current match catalog."""
    from apps.employees.models import EmployeeJobMatch

    today = timezone.localdate()
    date_str = today.strftime("%d/%m/%Y")

    suggested = (
        EmployeeJobMatch.objects
        .filter(status=EmployeeJobMatch.Status.SUGGESTED)
        .select_related("employee", "job", "job__company")
        .order_by("-match_score")
    )
    top = list(suggested[:top_n])
    suggested_total = suggested.count()

    new_jobs_today = 0
    try:
        from apps.jobs.models import Job

        new_jobs_today = Job.objects.filter(created_at__date=today).count()
    except Exception:  # noqa: BLE001
        pass

    base = settings.FRONTEND_BASE_URL.rstrip("/")

    def _row(m) -> tuple[str, str, str, int, str]:
        emp = m.employee.full_name if m.employee_id else "?"
        job = m.job.title if m.job_id else "?"
        company = m.job.company.name if (m.job_id and m.job.company_id) else ""
        # Deep-link to the employee's match view (same convention as mail).
        url = f"{base}/admin/employees/{m.employee_id}?match={m.id}" if m.employee_id else f"{base}/admin"
        return emp, job, company, _pct(m.match_score), url

    # --- stats lines (shared) ---
    stats = [f"• Việc làm mới hôm nay: *{new_jobs_today}*",
             f"• Gợi ý đang chờ xử lý: *{suggested_total}*"]
    if new_matches is not None:
        stats.insert(0, f"• Cặp ứng viên–việc làm mới sáng nay: *{new_matches}*")

    # --- plain text (markdown-ish, safe for all channels) ---
    text_lines = [f"📰 JobFlow — Bản tin tuyển dụng sáng {date_str}", ""]
    text_lines += [s.replace("*", "") for s in stats]
    text_lines.append("")
    if top:
        text_lines.append(f"🔝 Top {len(top)} gợi ý điểm cao:")
        for i, m in enumerate(top, 1):
            emp, job, company, pct, url = _row(m)
            at = f" @ {company}" if company else ""
            # Raw URL on its own line — auto-links in every client (Discord/
            # WhatsApp don't render markdown links, so no <text|url> here).
            text_lines.append(f"{i}. {emp} → {job}{at} · {pct}%")
            text_lines.append(f"   👉 {url}")
    else:
        text_lines.append("Chưa có gợi ý mới đang chờ xử lý.")
    text_lines += ["", f"Mở dashboard: {base}/admin"]
    text = "\n".join(text_lines)

    # --- Slack Block Kit ---
    blocks: list = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"📰 Bản tin tuyển dụng sáng {date_str}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(stats)}},
        {"type": "divider"},
    ]
    if top:
        lines = []
        for i, m in enumerate(top, 1):
            emp, job, company, pct, url = _row(m)
            at = f"  ·  _{company}_" if company else ""
            # Slack mrkdwn hyperlink: <url|text> — job title is the clickable bit.
            lines.append(f"*{i}. {emp}*  →  <{url}|{job}>{at}   `{pct}%`")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": f"*🔝 Top {len(top)} gợi ý điểm cao*\n" + "\n".join(lines)}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": "_Chưa có gợi ý mới đang chờ xử lý._"}})
    blocks.append({"type": "context", "elements": [
        {"type": "mrkdwn", "text": f"<{base}/admin|Mở dashboard JobFlow> để xem chi tiết các gợi ý phù hợp."}]})

    return DigestPayload(subject=f"JobFlow — Bản tin sáng {date_str}", text=text, slack_blocks=blocks)


def deliver_to_all(text: str, subject: str = "JobFlow", slack_blocks: list | None = None) -> dict:
    """Send `text` to all connected integrations. Returns a per-platform result
    summary; flags failing integrations as errored (does not raise)."""
    results: dict[str, str] = {}
    for row in Integration.objects.all():
        try:
            deliver(row.platform, row.get_config(), text, subject=subject, slack_blocks=slack_blocks)
        except DeliveryError as e:
            row.status = Integration.STATUS_ERROR
            row.last_error = str(e)[:500]
            row.save(update_fields=["status", "last_error"])
            results[row.platform] = f"error: {e}"
            continue
        row.status = Integration.STATUS_CONNECTED
        row.last_error = ""
        row.last_sent_at = timezone.now()
        row.save(update_fields=["status", "last_error", "last_sent_at"])
        results[row.platform] = "sent"
    return results


def deliver_digest(top_n: int = 5, new_matches: int | None = None) -> dict:
    """Build the morning digest and broadcast it to every connected channel."""
    payload = build_digest(top_n=top_n, new_matches=new_matches)
    return deliver_to_all(payload.text, subject=payload.subject, slack_blocks=payload.slack_blocks)
