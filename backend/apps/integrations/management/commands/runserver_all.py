"""`runserver` + the project's dev background workers in one process group.

Drop-in for `manage.py runserver`. Alongside the dev server it boots:
  • the Zalo zca-js sidecar           (backend/zalo_sidecar)
  • the hourly scheduler              (schedule_runner — morning_refresh, …)
  • the mail-reply poller every 5 min (poll_mail_replies --interval 300)

All are started once in the autoreload parent (RUN_MAIN guard) so code reloads
don't spawn duplicates, and are torn down on exit.

    python manage.py runserver_all
    python manage.py runserver_all 0.0.0.0:8000

The mail poll interval is configurable via env MAIL_POLL_INTERVAL (seconds).
The Django helpers run with JOBFLOW_SKIP_ML_WARMUP=1 so they don't each hold a
full ML engine in RAM (the engine still lazy-loads on demand if ever needed).
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
from urllib.parse import urlparse

from django.conf import settings

try:  # keep static-file serving in dev
    from django.contrib.staticfiles.management.commands.runserver import Command as BaseRunserver
except Exception:  # noqa: BLE001
    from django.core.management.commands.runserver import Command as BaseRunserver


class Command(BaseRunserver):
    help = "Run the dev server together with the Zalo sidecar, scheduler, and mail poller."

    def handle(self, *args, **options):
        # Only the reloader parent (or --noreload) owns the workers, so they
        # survive child reloads instead of being respawned each time.
        if os.environ.get("RUN_MAIN") != "true":
            self._start_workers()
        super().handle(*args, **options)

    # --- workers -----------------------------------------------------------
    def _start_workers(self) -> None:
        self._start_sidecar()
        # Django helpers skip the ML pre-warm to save RAM.
        helper_env = {**os.environ, "JOBFLOW_SKIP_ML_WARMUP": "1"}
        # -u → unbuffered, so helper logs stream live instead of block-buffering.
        self._spawn(
            [sys.executable, "-u", "manage.py", "schedule_runner"],
            cwd=str(settings.BASE_DIR), env=helper_env, label="scheduler",
        )
        interval = os.environ.get("MAIL_POLL_INTERVAL", "300")
        self._spawn(
            [sys.executable, "-u", "manage.py", "poll_mail_replies", "--interval", interval],
            cwd=str(settings.BASE_DIR), env=helper_env,
            label=f"mail-poller (every {interval}s)",
        )

    def _start_sidecar(self) -> None:
        sidecar_dir = settings.BASE_DIR / "zalo_sidecar"
        if not (sidecar_dir / "node_modules").exists():
            self.stdout.write(self.style.WARNING(
                "[sidecar] node_modules missing — skipping Zalo sidecar. "
                "Run: cd zalo_sidecar && npm install"
            ))
            return
        port = urlparse(settings.ZALO_SIDECAR_URL).port or 3001
        env = {**os.environ, "PORT": str(port)}
        if settings.ZALO_SIDECAR_TOKEN:
            env["ZALO_SIDECAR_TOKEN"] = settings.ZALO_SIDECAR_TOKEN
        self._spawn(["npm", "start"], cwd=str(sidecar_dir), env=env,
                    label=f"Zalo sidecar (:{port})")

    def _spawn(self, cmd: list[str], cwd: str, env: dict, label: str) -> None:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING(f"[{label}] '{cmd[0]}' not found — skipped."))
            return
        self.stdout.write(self.style.SUCCESS(f"[{label}] started (pid {proc.pid})."))

        def _stop():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        atexit.register(_stop)
