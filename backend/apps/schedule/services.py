"""Schedule run lifecycle — spawn, observe, stop, tail log."""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from apps.schedule.models import VerifierSchedule

logger = logging.getLogger(__name__)

# Log files live here. backend/logs/runs/ is gitignored.
LOG_DIR = Path(settings.BASE_DIR) / "logs" / "runs"


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _is_process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    # Best-effort zombie reap. Only works when the caller is the spawner's
    # parent (e.g. schedule_runner that did the Popen). Ignored otherwise.
    try:
        wpid, _ = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            return False
    except ChildProcessError:
        pass  # not our child — fall back to kill(0)
    except OSError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False


def get_or_create_schedule(command: str) -> VerifierSchedule:
    row, _ = VerifierSchedule.objects.get_or_create(command=command)
    return row


def refresh_active_run_state(row: VerifierSchedule) -> VerifierSchedule:
    """Clear active-run fields if the recorded PID is no longer alive."""
    if row.current_run_pid and not _is_process_alive(row.current_run_pid):
        row.current_run_pid = None
        row.save(update_fields=["current_run_pid"])
    return row


def is_active_run(row: VerifierSchedule) -> bool:
    return bool(row.current_run_pid and _is_process_alive(row.current_run_pid))


def start_run(row: VerifierSchedule, *, force: bool = False) -> tuple[bool, str]:
    """Spawn the subprocess. Returns (ok, message).

    force=True bypasses the "already running" guard.
    """
    if not force and is_active_run(row):
        return False, f"Already running (pid={row.current_run_pid})"

    _ensure_log_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{row.command}_{ts}.log"

    cmd: list[str] = [
        sys.executable, "manage.py", row.command,
        "--platform", row.platform,
        "--batch", str(row.batch_size),
    ]
    if row.use_no_auth_check:
        cmd.append("--no-auth-check")
    if not row.headless:
        cmd.append("--headed")

    logger.info("Spawning schedule run: %s → %s", shlex.join(cmd), log_path)
    # Open log file, redirect stdout+stderr.
    log_fp = open(log_path, "wb")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(settings.BASE_DIR),
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,   # so SIGTERM to leader hits the group
        )
    except Exception as exc:
        log_fp.close()
        logger.exception("Failed to spawn schedule run")
        return False, f"Spawn failed: {exc!r}"
    # NOTE: We intentionally don't close log_fp — the subprocess inherits it.
    # GC will close our handle; the kernel keeps the fd alive via the child.

    row.current_run_pid = proc.pid
    row.current_run_started_at = datetime.now(timezone.utc)
    row.current_run_log_path = str(log_path)
    row.save(update_fields=[
        "current_run_pid", "current_run_started_at", "current_run_log_path",
    ])
    return True, f"Started pid={proc.pid}"


def stop_run(row: VerifierSchedule, *, grace_seconds: float = 3.0) -> tuple[bool, str]:
    """Stop the active subprocess group: SIGTERM, then SIGKILL after grace.

    LinkedIn verifier/extractor loops have per-URL ``except Exception``
    blocks that swallow Playwright's TargetClosedError. SIGTERM alone may
    let Python continue iterating with every page.goto failing — so we
    escalate to SIGKILL after ``grace_seconds`` if the process is still
    alive. SIGKILL is uncatchable, guaranteeing the Stop button works.
    """
    pid = row.current_run_pid
    if not pid or not _is_process_alive(pid):
        row.current_run_pid = None
        row.save(update_fields=["current_run_pid"])
        return False, "No active run"
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        row.current_run_pid = None
        row.save(update_fields=["current_run_pid"])
        return False, "Process gone"

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as exc:
        return False, f"SIGTERM failed: {exc!r}"

    deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            row.current_run_pid = None
            row.save(update_fields=["current_run_pid"])
            return True, f"SIGTERM stopped pid={pid}"
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    # SIGKILL is uncatchable — the PID is dead (or a zombie when this
    # web process isn't the spawner's parent). Either way the run is
    # over. Proactively clear the active-run pointer so UI flips state
    # immediately instead of waiting for the zombie to be reaped.
    row.current_run_pid = None
    row.save(update_fields=["current_run_pid"])
    return True, f"SIGKILL sent to pid={pid} after {grace_seconds:.1f}s grace"


def tail_live_log(row: VerifierSchedule, since_bytes: int = 0) -> tuple[bytes, int]:
    """Read the active log file from ``since_bytes`` to EOF.

    Returns (new_bytes, new_offset). If no log yet, returns (b"", since_bytes).
    """
    path = row.current_run_log_path
    if not path:
        return b"", since_bytes
    p = Path(path)
    if not p.exists():
        return b"", since_bytes
    try:
        with p.open("rb") as f:
            f.seek(since_bytes)
            data = f.read()
        return data, since_bytes + len(data)
    except Exception:
        logger.exception("tail_live_log failed for %s", path)
        return b"", since_bytes


def list_run_logs(command: str, limit: int = 20) -> list[dict]:
    """List the most-recent log files on disk for a given command."""
    if not LOG_DIR.exists():
        return []
    files = sorted(
        LOG_DIR.glob(f"{command}_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out = []
    for f in files:
        stat = f.stat()
        out.append({
            "name": f.name,
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return out


def read_log_file(command: str, name: str) -> bytes | None:
    """Safely read a log file by basename. Returns None if path traversal."""
    if "/" in name or ".." in name or not name.startswith(command):
        return None
    path = LOG_DIR / name
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None
