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
    CredentialStatusSerializer, EmailLogSerializer, NotificationSerializer,
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
    try:
        log = send_apply_email(
            credential=cred, employee=emp, match=match,
            to_addr=request.data.get("to"), subject=request.data.get("subject", ""),
            body=request.data.get("body", ""),
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


@api_view(["GET"])
@permission_classes(HR)
def thread(request):
    qs = EmailLog.objects.filter(match_id=request.query_params.get("match")).order_by("created_at")
    return Response(EmailLogSerializer(qs, many=True).data)


class NotificationListView(APIView):
    permission_classes = HR

    def get(self, request):
        qs = Notification.objects.all().order_by("read_at", "-created_at")
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


@api_view(["GET"])
@permission_classes(HR)
def recent_replies(request):
    qs = Notification.objects.filter(type=Notification.MAIL_REPLY).select_related("employee")[:10]
    out = [{
        "employee": {"id": n.employee_id, "name": n.employee.full_name if n.employee else ""},
        "title": n.title, "snippet": n.body_preview, "created_at": n.created_at, "link_url": n.link_url,
    } for n in qs]
    return Response(out)
