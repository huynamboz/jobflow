"""Schedule REST API — config CRUD, start/stop, live log, history."""

from __future__ import annotations

from datetime import datetime, timezone

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job, VerifierRunLog
from apps.schedule import services
from apps.schedule.models import VerifierSchedule

ALLOWED_COMMANDS = {
    VerifierSchedule.COMMAND_VERIFY,
    VerifierSchedule.COMMAND_EXTRACT,
    VerifierSchedule.COMMAND_MORNING,
}


def _pending_counts(platform: str) -> dict[str, int]:
    """Cheap counts for the two operations, mirroring the repository selection.

    - verify  : active|stale ∩ (backoff null or expired)
    - extract : the same set ∩ date_posted IS NULL
    """
    now = datetime.now(timezone.utc)
    base = (
        Job.objects
        .filter(platform__name__iexact=platform)
        .filter(lifecycle__in=[Job.LIFECYCLE_ACTIVE, Job.LIFECYCLE_STALE])
        .filter(Q(verification_backoff_until__isnull=True) | Q(verification_backoff_until__lte=now))
    )
    return {
        "verify": base.count(),
        "extract": base.filter(date_posted__isnull=True).count(),
    }


def _serialize_schedule(row: VerifierSchedule) -> dict:
    services.refresh_active_run_state(row)
    return {
        "command": row.command,
        "enabled": row.enabled,
        "batch_size": row.batch_size,
        "batches_per_day": row.batches_per_day,
        "hours_utc": row.hours_utc,
        "use_no_auth_check": row.use_no_auth_check,
        "headless": row.headless,
        "platform": row.platform,
        "active_run": {
            "pid": row.current_run_pid,
            "started_at": row.current_run_started_at.isoformat() if row.current_run_started_at else None,
            "log_path": row.current_run_log_path or None,
            "is_alive": services.is_active_run(row),
        },
        "last_fired_at": row.last_fired_at.isoformat() if row.last_fired_at else None,
        "updated_at": row.updated_at.isoformat(),
        "pending": _pending_counts(row.platform),
    }


def _serialize_run_log(r: VerifierRunLog) -> dict:
    return {
        "id": r.id,
        "command": r.command,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "wall_clock_s": round(r.wall_clock_seconds, 3),
        "total_examined": r.total_examined,
        "counts_by_outcome": r.counts_by_outcome or {},
        "dry_run": r.dry_run,
    }


def _err(code: str, message: str, status_code: int) -> Response:
    return Response(
        {"success": False, "error": {"code": code, "message": message, "status": status_code}},
        status=status_code,
    )


def _bad_command(cmd: str) -> Response:
    return _err("INVALID_COMMAND", f"Unknown command {cmd!r}", status.HTTP_400_BAD_REQUEST)


class ScheduleConfigView(APIView):
    """GET/PUT /api/admin/schedule/<command>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        row = services.get_or_create_schedule(command)
        return Response({"success": True, "data": _serialize_schedule(row)})

    def put(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        row = services.get_or_create_schedule(command)

        payload = request.data or {}
        for key in ("enabled", "batch_size", "batches_per_day", "hours_utc",
                    "use_no_auth_check", "headless", "platform"):
            if key in payload:
                setattr(row, key, payload[key])

        if not isinstance(row.batch_size, int) or row.batch_size < 1 or row.batch_size > 1000:
            return _err("INVALID_BATCH", "batch_size must be 1..1000", 400)
        if not isinstance(row.hours_utc, list) or not all(
            isinstance(h, int) and 0 <= h <= 23 for h in row.hours_utc
        ):
            return _err("INVALID_HOURS", "hours_utc must be a list of 0..23", 400)
        if row.platform not in ("linkedin",):
            return _err("INVALID_PLATFORM", "v1 supports only platform=linkedin", 400)

        row.save()
        return Response({"success": True, "data": _serialize_schedule(row)})


class ScheduleStartView(APIView):
    """POST /api/admin/schedule/<command>/start/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        row = services.get_or_create_schedule(command)
        services.refresh_active_run_state(row)
        ok, msg = services.start_run(row)
        if not ok:
            return _err("START_FAILED", msg, 409)
        return Response({"success": True, "data": _serialize_schedule(row), "message": msg})


class ScheduleStopView(APIView):
    """POST /api/admin/schedule/<command>/stop/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        row = services.get_or_create_schedule(command)
        ok, msg = services.stop_run(row)
        services.refresh_active_run_state(row)
        return Response({"success": ok, "data": _serialize_schedule(row), "message": msg})


class ScheduleLiveLogView(APIView):
    """GET /api/admin/schedule/<command>/live-log/?since=<bytes>"""
    permission_classes = [IsAuthenticated]

    def get(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        row = services.get_or_create_schedule(command)
        try:
            since = int(request.query_params.get("since", 0))
        except (TypeError, ValueError):
            since = 0
        data, new_offset = services.tail_live_log(row, since_bytes=since)
        return Response({
            "success": True,
            "data": {
                "since": since,
                "offset": new_offset,
                "text": data.decode("utf-8", errors="replace"),
                "is_alive": services.is_active_run(row),
                "log_path": row.current_run_log_path or None,
            },
        })


class ScheduleHistoryView(APIView):
    """GET /api/admin/schedule/<command>/history/?limit=20"""
    permission_classes = [IsAuthenticated]

    def get(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        try:
            limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
        except (TypeError, ValueError):
            limit = 20
        rows = (
            VerifierRunLog.objects
            .filter(command=command)
            .order_by("-started_at")[:limit]
        )
        return Response({
            "success": True,
            "data": {
                "runs": [_serialize_run_log(r) for r in rows],
                "logs": services.list_run_logs(command, limit=limit),
            },
        })


class ScheduleLogFileView(APIView):
    """GET /api/admin/schedule/<command>/log-file/?name=<file>"""
    permission_classes = [IsAuthenticated]

    def get(self, request, command: str):
        if command not in ALLOWED_COMMANDS:
            return _bad_command(command)
        name = request.query_params.get("name", "")
        if not name:
            return _err("MISSING_NAME", "?name=<file> is required", 400)
        data = services.read_log_file(command, name)
        if data is None:
            return _err("NOT_FOUND", "Log file not found", 404)
        return Response({
            "success": True,
            "data": {"name": name, "text": data.decode("utf-8", errors="replace"), "size_bytes": len(data)},
        })
