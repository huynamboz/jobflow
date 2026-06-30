"""Mail-link API (026). HR-only. Password never returned."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.employees.models import Employee, EmployeeJobMatch
from apps.employees.permissions import IsHRStaff
from apps.mail.models import EmailLog, EmployeeMailCredential, Notification
from apps.mail.serializers import (
    CredentialStatusSerializer, EmailLogListSerializer, EmailLogSerializer, NotificationSerializer,
)
from apps.mail.services.probe import ProbeError, probe
from apps.mail.services.send import send_apply_email

HR = [IsAuthenticated, IsHRStaff]


class CredentialView(APIView):
    permission_classes = HR

    def get(self, request):
        cred = EmployeeMailCredential.objects.filter(employee_id=request.query_params.get("employee")).first()
        if not cred:
            return Response({"linked": False})
        return Response(CredentialStatusSerializer(cred).data)

    def post(self, request):
        emp = get_object_or_404(Employee, pk=request.data.get("employee"))
        address = (request.data.get("gmail_address") or "").strip()
        pw = (request.data.get("app_password") or "").replace(" ", "")
        if not address or not pw:
            return Response({"success": False, "error": {"code": "BAD_REQUEST", "message": "address + app_password required"}}, status=400)
        # gmail_address is unique — surface a clear conflict instead of a 500
        conflict = (EmployeeMailCredential.objects.filter(gmail_address=address)
                    .exclude(employee=emp).select_related("employee").first())
        if conflict:
            return Response({"success": False, "error": {"code": "EMAIL_IN_USE",
                "message": f"Gmail {address} đã được liên kết với nhân viên {conflict.employee.full_name}. "
                           f"Hãy gỡ liên kết ở nhân viên đó trước, hoặc dùng địa chỉ khác."}}, status=400)
        try:
            probe(address, pw)
        except ProbeError as e:
            return Response({"success": False, "error": {"code": "PROBE_FAILED", "message": str(e)}}, status=400)
        cred, _ = EmployeeMailCredential.objects.get_or_create(employee=emp, defaults={"gmail_address": address})
        cred.gmail_address = address
        cred.set_password(pw)
        cred.status = EmployeeMailCredential.STATUS_ACTIVE
        cred.last_error = ""
        cred.save()
        return Response(CredentialStatusSerializer(cred).data)


class CredentialUnlinkView(APIView):
    permission_classes = HR

    def delete(self, request, employee_id):
        EmployeeMailCredential.objects.filter(employee_id=employee_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes(HR)
def send_apply(request):
    match = get_object_or_404(EmployeeJobMatch, pk=request.data.get("match"))
    emp = match.employee
    cred = EmployeeMailCredential.objects.filter(employee=emp, status=EmployeeMailCredential.STATUS_ACTIVE).first()
    if not cred:
        return Response({"success": False, "error": {"code": "NO_CREDENTIAL", "message": "Employee has no linked email account."}}, status=400)
    # Optional attachment override from the compose screen: a replacement file
    # (multipart `cv`) or `no_cv` to send without any CV.
    cv_override = request.FILES.get("cv")
    attach_cv = str(request.data.get("no_cv", "")).lower() not in ("1", "true", "yes")
    try:
        log = send_apply_email(
            credential=cred, employee=emp, match=match,
            to_addr=request.data.get("to"), subject=request.data.get("subject", ""),
            body=request.data.get("body", ""),
            cv_override=cv_override, attach_cv=attach_cv,
        )
    except Exception as e:  # noqa: BLE001
        cred.status = EmployeeMailCredential.STATUS_ERROR
        cred.last_error = str(e)[:500]
        cred.save(update_fields=["status", "last_error"])
        return Response({"success": False, "error": {"code": "SEND_FAILED", "message": str(e)}}, status=400)
    # success → mark applied (existing pipeline status)
    if match.status == EmployeeJobMatch.Status.SUGGESTED:
        match.status = EmployeeJobMatch.Status.APPLIED
        match.applied_at = timezone.now()
        match.save(update_fields=["status", "applied_at"])
    return Response({"ok": True, "email_log": log.id, "match_status": match.status, "cv_attached": log.cv_attached})


@api_view(["POST"])
@permission_classes(HR)
def reply(request):
    """Send a threaded reply within an existing conversation (same match).

    Unlike send-apply this attaches NO CV, does NOT change the match status,
    and sets In-Reply-To/References so it lands in the same Gmail thread and our
    EmailLog chains to the conversation."""
    match = get_object_or_404(EmployeeJobMatch, pk=request.data.get("match"))
    emp = match.employee
    cred = EmployeeMailCredential.objects.filter(
        employee=emp, status=EmployeeMailCredential.STATUS_ACTIVE
    ).first()
    if not cred:
        return Response({"success": False, "error": {"code": "NO_CREDENTIAL", "message": "Employee has no linked email account."}}, status=400)
    body = (request.data.get("body") or "").strip()
    if not body:
        return Response({"success": False, "error": {"code": "EMPTY_BODY", "message": "Reply body is required."}}, status=400)

    chain = list(EmailLog.objects.filter(match=match).order_by("created_at"))
    if not chain:
        return Response({"success": False, "error": {"code": "NO_THREAD", "message": "No conversation to reply to."}}, status=400)

    # Reply to the most recent inbound message if any (the company replied),
    # else to the original outbound. Address the company, not ourselves.
    inbound = [m for m in chain if m.direction == EmailLog.IN and not m.is_bounce]
    parent = inbound[-1] if inbound else chain[-1]
    to_addr = (inbound[-1].from_addr if inbound else chain[0].to_addr) or request.data.get("to", "")
    references = " ".join(m.message_id for m in chain if m.message_id)
    base_subject = chain[0].subject or ""
    subject = base_subject if base_subject.lower().startswith("re:") else f"Re: {base_subject}".strip()

    try:
        log = send_apply_email(
            credential=cred, employee=emp, match=match,
            to_addr=to_addr, subject=subject, body=body,
            attach_cv=False, in_reply_to=parent.message_id, references=references,
        )
    except Exception as e:  # noqa: BLE001
        cred.status = EmployeeMailCredential.STATUS_ERROR
        cred.last_error = str(e)[:500]
        cred.save(update_fields=["status", "last_error"])
        return Response({"success": False, "error": {"code": "SEND_FAILED", "message": str(e)}}, status=400)

    return Response({"ok": True, "email_log": log.id})


@api_view(["GET"])
@permission_classes(HR)
def thread(request):
    qs = EmailLog.objects.filter(match_id=request.query_params.get("match")).order_by("created_at")
    return Response(EmailLogSerializer(qs, many=True).data)


class NotificationListView(APIView):
    permission_classes = HR

    def get(self, request):
        from django.db.models import F

        # unread first (NULL read_at), then newest-first within each group
        qs = Notification.objects.all().order_by(F("read_at").asc(nulls_first=True), "-created_at")
        unread = Notification.objects.filter(read_at__isnull=True).count()
        page = int(request.query_params.get("page", 1))
        size = 20
        rows = qs[(page - 1) * size: page * size]
        return Response({"count": qs.count(), "unread": unread, "results": NotificationSerializer(rows, many=True).data})


@api_view(["GET"])
@permission_classes(HR)
def unread_count(request):
    return Response({"unread": Notification.objects.filter(read_at__isnull=True).count()})


@api_view(["POST"])
@permission_classes(HR)
def mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return Response({"id": n.id, "read_at": n.read_at})


@api_view(["POST"])
@permission_classes(HR)
def sync_now(request):
    """Run the IMAP poller on demand for all active mailboxes; return new count
    + the latest sync time (026 UI sync button)."""
    from apps.mail.services.imap_poll import poll_credential
    total = 0
    for cred in EmployeeMailCredential.objects.filter(status=EmployeeMailCredential.STATUS_ACTIVE):
        try:
            total += poll_credential(cred)
        except Exception as e:  # noqa: BLE001
            cred.status = EmployeeMailCredential.STATUS_ERROR
            cred.last_error = str(e)[:500]
            cred.save(update_fields=["status", "last_error"])
    return Response(_sync_status_payload(new=total))


@api_view(["GET"])
@permission_classes(HR)
def sync_status(request):
    return Response(_sync_status_payload())


def _sync_status_payload(new: int | None = None):
    latest = (EmployeeMailCredential.objects
              .filter(last_polled_at__isnull=False).order_by("-last_polled_at")
              .values_list("last_polled_at", flat=True).first())
    active = EmployeeMailCredential.objects.filter(status=EmployeeMailCredential.STATUS_ACTIVE).count()
    errored = EmployeeMailCredential.objects.filter(status=EmployeeMailCredential.STATUS_ERROR).count()
    return {"last_synced": latest, "active_accounts": active, "errored_accounts": errored,
            **({"new": new} if new is not None else {})}


@api_view(["GET"])
@permission_classes(HR)
def email_log_list(request):
    """All emails, newest first, filterable. ?direction=out|in &status= &is_bounce=
    &employee= &page= — for the central Mail management page."""
    qs = EmailLog.objects.select_related("employee", "match__job__company").order_by("-created_at")
    p = request.query_params
    if p.get("direction"):
        qs = qs.filter(direction=p["direction"])
    if p.get("status"):
        qs = qs.filter(status=p["status"])
    if p.get("is_bounce") in ("1", "true"):
        qs = qs.filter(is_bounce=True)
    if p.get("employee"):
        qs = qs.filter(employee_id=p["employee"])
    total = qs.count()
    page = int(p.get("page", 1)); size = 30
    rows = qs[(page - 1) * size: page * size]
    return Response({"count": total, "page": page, "results": EmailLogListSerializer(rows, many=True).data})


@api_view(["GET"])
@permission_classes(HR)
def email_log_detail(request, pk):
    """One email with its candidate, job, match context + the full thread for
    its match (026 mail detail page)."""
    log = get_object_or_404(
        EmailLog.objects.select_related("employee", "match__job__company"), pk=pk
    )
    emp = log.employee
    match = log.match
    job = match.job if match and match.job_id else None

    emp_data = None
    if emp:
        cred = EmployeeMailCredential.objects.filter(employee=emp).first()
        emp_data = {
            "id": emp.id, "full_name": emp.full_name, "position": emp.position,
            "email": emp.email, "phone": emp.phone, "seniority": emp.seniority,
            "experience_years": emp.experience_years, "skills": emp.skills or [],
            # linked Gmail (the address mail is sent FROM) — never the password
            "linked_email": cred.gmail_address if cred else "",
            "linked_status": cred.status if cred else "",
        }
    job_data = None
    if job:
        job_data = {
            "id": job.id, "title": job.title,
            "company": job.company.name if job.company_id else "",
            "company_logo": (job.company.logo_url or "") if job.company_id else "",
            "location": job.location, "job_type": job.job_type,
            "source_url": job.source_url,
        }
    match_data = None
    if match:
        match_data = {
            "id": match.id, "status": match.status, "match_score": match.match_score,
            "matched_skills": match.matched_skills or [], "missing_skills": match.missing_skills or [],
        }
    thread_qs = (EmailLog.objects.filter(match=match).order_by("created_at")
                 if match else EmailLog.objects.filter(pk=log.pk))
    return Response({
        "log": EmailLogListSerializer(log).data,
        "employee": emp_data, "job": job_data, "match": match_data,
        "thread": EmailLogSerializer(thread_qs, many=True).data,
    })


@api_view(["GET"])
@permission_classes(HR)
def credential_list(request):
    """All linked email accounts — for the Mail page 'Accounts' tab."""
    out = []
    for c in EmployeeMailCredential.objects.select_related("employee").order_by("-linked_at"):
        out.append({
            "employee": {"id": c.employee_id, "name": c.employee.full_name},
            "gmail_address": c.gmail_address, "status": c.status,
            "last_error": c.last_error, "linked_at": c.linked_at,
        })
    return Response(out)


@api_view(["GET"])
@permission_classes(HR)
def recent_replies(request):
    qs = Notification.objects.filter(type=Notification.MAIL_REPLY).select_related("employee")[:10]
    out = [{
        "employee": {"id": n.employee_id, "name": n.employee.full_name if n.employee else ""},
        "title": n.title, "snippet": n.body_preview, "created_at": n.created_at, "link_url": n.link_url,
    } for n in qs]
    return Response(out)
