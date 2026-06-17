"""`runserver` + the Zalo zca-js sidecar in one process group.

Drop-in for `manage.py runserver`: it boots the Node sidecar (backend/zalo_sidecar)
alongside the dev server and tears it down on exit. Use it instead of runserver:

    python manage.py runserver_all
    python manage.py runserver_all 0.0.0.0:8000

The sidecar is started once in the autoreload parent (RUN_MAIN guard) so code
reloads don't spawn duplicates. Skipped automatically if node_modules is missing
(run `npm install` in backend/zalo_sidecar first) — the dev server still starts.
"""
from __future__ import annotations

import atexit
import os
import subprocess
from urllib.parse import urlparse

from django.conf import settings

try:  # keep static-file serving in dev
    from django.contrib.staticfiles.management.commands.runserver import Command as BaseRunserver
except Exception:  # noqa: BLE001
    from django.core.management.commands.runserver import Command as BaseRunserver


class Command(BaseRunserver):
    help = "Run the dev server together with the Zalo zca-js sidecar."

    def handle(self, *args, **options):
        # Only the reloader parent (or --noreload) should own the sidecar, so it
        # survives child reloads instead of being respawned each time.
        if os.environ.get("RUN_MAIN") != "true":
            self._start_sidecar()
        super().handle(*args, **options)

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

        try:
            proc = subprocess.Popen(["npm", "start"], cwd=str(sidecar_dir), env=env)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("[sidecar] npm not found — skipping Zalo sidecar."))
            return

        self.stdout.write(self.style.SUCCESS(f"[sidecar] Zalo sidecar started on :{port} (pid {proc.pid})."))

        def _stop():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        atexit.register(_stop)
