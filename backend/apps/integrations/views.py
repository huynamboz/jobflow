"""Integrations API (HR-only). Connect/disconnect delivery channels and send a
test message. Secrets are written but never read back."""
from __future__ import annotations

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.employees.permissions import IsAdminUserRole
from apps.integrations.events import DEFAULT_EVENTS, EVENT_KEYS
from apps.integrations.models import Integration
from apps.integrations.registry import PLATFORMS, get_platform
from apps.integrations.serializers import serialize_platform
from apps.integrations.services.delivery import DeliveryError, deliver

# Integrations are a SYSTEM-WIDE admin config (not per-recruiter) → admin only.
HR = [IsAuthenticated, IsAdminUserRole]

TEST_MESSAGE = "✅ JobFlow — kết nối thành công. Bản tin tuyển dụng buổi sáng sẽ được gửi tới kênh này."


def _rows_by_platform() -> dict[str, Integration]:
    return {r.platform: r for r in Integration.objects.all()}


class IntegrationListView(APIView):
    permission_classes = HR

    def get(self, request):
        rows = _rows_by_platform()
        data = [serialize_platform(p, rows.get(pid)) for pid, p in PLATFORMS.items()]
        return Response(data)


class IntegrationDetailView(APIView):
    permission_classes = HR

    def _merged_config(self, platform, incoming: dict, existing: dict) -> dict:
        """Build the config to persist: start from the saved config, overlay any
        non-blank incoming values. Secret fields left blank keep their saved value
        (so editing a non-secret field doesn't wipe a token)."""
        merged = dict(existing)
        for f in platform.fields:
            val = incoming.get(f.key)
            if val is None:
                continue
            val = str(val).strip()
            if val == "" and f.secret:
                continue  # blank secret on update → keep existing
            merged[f.key] = val
        return merged

    def post(self, request, platform_id):
        platform = get_platform(platform_id)
        if not platform:
            return Response({"success": False, "error": {"code": "UNKNOWN_PLATFORM",
                "message": f"Unknown platform '{platform_id}'."}}, status=400)

        row = Integration.objects.filter(platform=platform_id).first()
        existing = row.get_config() if row else {}
        incoming = request.data if isinstance(request.data, dict) else {}
        config = self._merged_config(platform, incoming, existing)

        missing = [k for k in platform.required_keys() if not str(config.get(k, "")).strip()]
        if missing:
            return Response({"success": False, "error": {"code": "MISSING_FIELDS",
                "message": f"Missing required field(s): {', '.join(missing)}",
                "fields": missing}}, status=400)

        if row is None:
            row = Integration(platform=platform_id)
            row.events = dict(DEFAULT_EVENTS)  # new channel → all notifications on
        row.set_config(config)
        row.status = Integration.STATUS_CONNECTED
        row.last_error = ""
        row.save()
        return Response(serialize_platform(platform, row))

    def delete(self, request, platform_id):
        Integration.objects.filter(platform=platform_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes(HR)
def test_integration(request, platform_id):
    """Send a real test message through the saved (or just-submitted) config."""
    platform = get_platform(platform_id)
    if not platform:
        return Response({"success": False, "error": {"code": "UNKNOWN_PLATFORM",
            "message": f"Unknown platform '{platform_id}'."}}, status=400)

    row = Integration.objects.filter(platform=platform_id).first()
    if not row:
        return Response({"success": False, "error": {"code": "NOT_CONNECTED",
            "message": "Connect this platform before sending a test."}}, status=400)

    config = row.get_config()
    try:
        deliver(platform_id, config, TEST_MESSAGE, subject="JobFlow — Test")
    except DeliveryError as e:
        row.status = Integration.STATUS_ERROR
        row.last_error = str(e)[:500]
        row.save(update_fields=["status", "last_error"])
        return Response({"success": False, "error": {"code": "DELIVERY_FAILED", "message": str(e)}}, status=400)

    row.status = Integration.STATUS_CONNECTED
    row.last_error = ""
    row.last_sent_at = timezone.now()
    row.save(update_fields=["status", "last_error", "last_sent_at"])
    return Response({"ok": True, "last_sent_at": row.last_sent_at})


@api_view(["POST"])
@permission_classes(HR)
def set_events(request, platform_id):
    """Update which notifications a connected channel receives.
    Body: {"events": {"mail_reply": true, "mail_sent": false, "new_match": true}}"""
    platform = get_platform(platform_id)
    if not platform:
        return Response({"success": False, "error": {"code": "UNKNOWN_PLATFORM",
            "message": f"Unknown platform '{platform_id}'."}}, status=400)
    row = Integration.objects.filter(platform=platform_id).first()
    if not row:
        return Response({"success": False, "error": {"code": "NOT_CONNECTED",
            "message": "Connect this platform first."}}, status=400)

    incoming = (request.data or {}).get("events", {})
    if not isinstance(incoming, dict):
        return Response({"success": False, "error": {"code": "BAD_REQUEST",
            "message": "events must be an object."}}, status=400)
    merged = {**(row.events or {})}
    for k in EVENT_KEYS:
        if k in incoming:
            merged[k] = bool(incoming[k])
    row.events = merged
    row.save(update_fields=["events"])
    return Response(serialize_platform(platform, row))


# --- Zalo QR login (proxied to the zca-js sidecar) ------------------------------

def _zalo_sidecar(method: str, path: str):
    """Call the Zalo sidecar; returns (payload, http_status)."""
    base = (settings.ZALO_SIDECAR_URL or "").rstrip("/")
    if not base:
        return {"success": False, "error": {"code": "NO_SIDECAR",
                "message": "ZALO_SIDECAR_URL chưa cấu hình."}}, 400
    headers = {}
    if settings.ZALO_SIDECAR_TOKEN:
        headers["x-sidecar-token"] = settings.ZALO_SIDECAR_TOKEN
    try:
        r = requests.request(method, f"{base}{path}", headers=headers, timeout=15)
    except requests.RequestException as e:
        return {"success": False, "error": {"code": "SIDECAR_DOWN",
                "message": f"Không kết nối được Zalo sidecar ({base}). "
                           f"Hãy chạy backend/zalo_sidecar (npm start). Chi tiết: {e}"}}, 502
    try:
        return r.json(), r.status_code
    except ValueError:
        return {"raw": r.text[:300]}, r.status_code


@api_view(["POST"])
@permission_classes(HR)
def zalo_login_start(request):
    payload, code = _zalo_sidecar("POST", "/login-qr/start")
    return Response(payload, status=code)


@api_view(["GET"])
@permission_classes(HR)
def zalo_login_status(request):
    payload, code = _zalo_sidecar("GET", "/login-qr/status")
    return Response(payload, status=code)
