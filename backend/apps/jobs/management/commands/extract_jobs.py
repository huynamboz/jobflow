"""Extract structured JD fields from crawled jobs, writing
data/extracted/<provider>/<date>.json.

Decouples extraction (the expensive step) from the DB write: run this to produce
the extracted files, then `import_extracted` loads them with NO further LLM call.

Two engines (--engine):
  llm   (default) — LLMService / llm_jd_extractor over a thread pool. The
                    production path; works headless / in cron. Live dashboard
                    shows each worker + the job title it's processing.
  agent           — drive an interactive `claude` session (poc_tell_claude.sh):
                    host slices the file → parallel subagents extract → host
                    merges. Subscription-billed, needs a TTY/tmux, DEV/MANUAL
                    only (do NOT schedule). Lets you extract without spending
                    LLM-API credits for a one-off.

Usage:
    python manage.py extract_jobs                       # today, all providers (llm)
    python manage.py extract_jobs --provider remotive --workers 6
    python manage.py extract_jobs --provider jobspy --workers 2 --retries 3
    python manage.py extract_jobs --provider remotive --engine agent  # via claude
"""
import glob
import json
import logging
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich import box
    _RICH = True
except ImportError:  # pragma: no cover
    _RICH = False

logger = logging.getLogger(__name__)


def _to_extracted(r) -> dict:
    """JDExtractResult → the dict shape save_raw_job/import_extracted expect."""
    return {
        "seniority": r.seniority,
        "role_category": r.role_category,
        "job_type": r.job_type,
        "experience_min": r.experience_min,
        "experience_max": r.experience_max,
        "degree_requirement": getattr(r, "degree_requirement", 0),
        "salary_min": r.salary_min,
        "salary_max": r.salary_max,
        "skills": r.skills,
    }


class _Dashboard:
    """Live view: header progress + one row per worker (current job title)."""

    _STATE = {
        "working": "[yellow]● run",
        "retry": "[dark_orange]↻ retry",
        "done": "[green]✓ done",
        "idle": "[dim]· idle",
    }

    def __init__(self, provider: str, total: int, pre_done: int = 0) -> None:
        self.provider, self.total = provider, total
        self.done = self.ok = pre_done
        self.fail = 0
        self._workers: dict[str, tuple[str, str, int]] = {}   # tname -> (title, state, attempt)
        self._lock = threading.Lock()

    def set_worker(self, tname: str, title: str, state: str, attempt: int = 0) -> None:
        with self._lock:
            self._workers[tname] = (title, state, attempt)

    def tick(self, ok: bool) -> None:
        with self._lock:
            self.done += 1
            if ok:
                self.ok += 1
            else:
                self.fail += 1

    def idle_all(self) -> None:
        with self._lock:
            self._workers = {n: ("—", "idle", 0) for n in self._workers}

    def __rich__(self):
        with self._lock:
            done, ok, fail = self.done, self.ok, self.fail
            snap = dict(self._workers)
        pct = int(100 * done / self.total) if self.total else 0
        filled = int(24 * done / self.total) if self.total else 0
        bar = "[green]" + "━" * filled + "[grey37]" + "━" * (24 - filled)
        head = Text.from_markup(
            f"[bold cyan]{self.provider:<11}[/] {bar} [white]{done}/{self.total}[/] "
            f"[green]✓{ok}[/] [red]✗{fail}[/] [dim]{pct}%[/]"
        )
        t = Table(box=box.SIMPLE_HEAD, expand=False, show_edge=False, pad_edge=False)
        t.add_column("worker", style="cyan", no_wrap=True)
        t.add_column("state", no_wrap=True)
        t.add_column("job đang xử lý", overflow="ellipsis", max_width=64)
        for name in sorted(snap):
            title, state, attempt = snap[name]
            label = self._STATE.get(state, state)
            if state == "retry":
                label += str(attempt)
            t.add_row(name, label, title or "—")
        return Group(head, t)


class Command(BaseCommand):
    help = "Extract JD fields from crawled jobs via the LLM → data/extracted/*.json"

    def add_arguments(self, parser):
        parser.add_argument("--provider", type=str, default="", help="Only this provider folder")
        parser.add_argument("--date", type=str, default="", help="<date> file (default: today)")
        parser.add_argument("--in-dir", type=str, default="", help="Crawl root (default <BASE_DIR>/data/crawl)")
        parser.add_argument("--out-dir", type=str, default="", help="Output root (default <BASE_DIR>/data/extracted)")
        parser.add_argument("--engine", choices=["llm", "agent"], default="agent",
                            help="llm = LLMService API (default, headless/cron). "
                                 "agent = drive interactive claude (poc_tell_claude.sh; subscription, dev only)")
        parser.add_argument("--workers", type=int, default=10,
                            help="llm: parallel LLM calls · agent: subagents per wave (12-16 good for big files)")
        parser.add_argument("--retries", type=int, default=2, help="[llm] Retries on timeout/empty result per job")
        parser.add_argument("--desc-chars", type=int, default=6000, help="Truncate description per job (token cost)")
        parser.add_argument("--flush-every", type=int, default=10, help="[llm] Write the output file every N done jobs")
        parser.add_argument("--limit", type=int, default=0, help="[llm] Cap jobs per file (debug)")
        # agent-engine only
        parser.add_argument("--model", type=str, default="claude-sonnet-4-6",
                            help="[agent] claude model for the session + subagents")
        parser.add_argument("--per-shard", type=int, default=12, help="[agent] target jobs per subagent")
        parser.add_argument("--fresh", action="store_true",
                            help="[agent] re-slice shards from scratch (use after changing --workers/--per-shard)")

    def handle(self, *args, **o):
        in_root = Path(o["in_dir"]) if o["in_dir"] else Path(settings.BASE_DIR) / "data" / "crawl"
        out_root = Path(o["out_dir"]) if o["out_dir"] else Path(settings.BASE_DIR) / "data" / "extracted"
        date = o["date"] or datetime.now().strftime("%Y-%m-%d")
        provider = o["provider"] or "*"
        files = sorted(glob.glob(str(in_root / provider / f"{date}.json")))
        if not files:
            self.stderr.write(self.style.WARNING(f"No crawl files under {in_root}/{provider}/{date}.json"))
            return

        if o["engine"] == "agent":
            return self._run_agent_engine([Path(f) for f in files], date, o)

        self._console = Console() if _RICH else None
        total_ok = 0
        for f in files:
            total_ok += self._process_file(Path(f), out_root, date, o)

        msg = f"Done {date}. extracted {total_ok} jobs across {len(files)} file(s) -> {out_root}"
        if self._console:
            self._console.print(f"[bold green]✓ {msg}")
        else:
            self.stdout.write(self.style.SUCCESS(msg))

    def _run_agent_engine(self, files, date, o):
        """Extract by driving an interactive claude session via poc_tell_claude.sh,
        once per provider. The script slices/merges on the host; claude only runs
        the per-shard extraction. Writes the SAME data/extracted/<provider>/<date>.json
        the llm engine does, so import_extracted is unchanged.

        Dev/manual only — needs a TTY + tmux + a logged-in `claude`; subscription
        billed. Do NOT schedule this. --in-dir/--out-dir are ignored (the script
        uses the repo defaults)."""
        script = Path(settings.BASE_DIR).parent / "poc_tell_claude.sh"
        if not script.exists():
            self.stderr.write(self.style.ERROR(f"agent engine needs {script} (not found)"))
            return
        if os.environ.get("CLAUDECODE"):
            self.stderr.write(self.style.ERROR(
                "Refusing: CLAUDECODE is set — run --engine agent from a NORMAL terminal, "
                "not inside a Claude Code session (the script spawns its own claude)."))
            return

        env = {
            **os.environ,
            "MODEL": o["model"],
            "MAX_AGENTS": str(max(1, o["workers"])),
            "PER_SHARD": str(max(1, o["per_shard"])),
            "DESC": str(o["desc_chars"]),
            "FRESH": "1" if o["fresh"] else "0",
        }
        ok = 0
        for fpath in files:
            provider = fpath.parent.name
            self.stdout.write(self.style.NOTICE(
                f"[agent] {provider}/{date} → poc_tell_claude.sh "
                f"(model={o['model']}, ~{o['per_shard']} jobs/shard, {o['workers']} agents/wave)"))
            rc = subprocess.run(["bash", str(script), provider, date], env=env).returncode
            if rc == 0:
                ok += 1
            else:
                self.stderr.write(self.style.WARNING(f"[agent] {provider}: script exited {rc} (gaps may remain — re-run to resume)"))
        self.stdout.write(self.style.SUCCESS(
            f"Done {date}. agent engine processed {ok}/{len(files)} provider file(s). "
            f"Next: python manage.py import_extracted --date {date} --dry-run"))

    def _process_file(self, fpath, out_root, date, o):
        from apps.jobs.services.llm_jd_extractor import extract as llm_jd_extract
        from django.db import connection

        jobs = json.loads(fpath.read_text(encoding="utf-8"))
        if o["limit"]:
            jobs = jobs[: o["limit"]]
        provider = fpath.parent.name
        out_path = out_root / provider / f"{date}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Resume: keep jobs already extracted in a previous run of the same file.
        extracted_map: dict = {}
        if out_path.exists():
            try:
                for j in json.loads(out_path.read_text(encoding="utf-8")):
                    if j.get("extracted") is not None and j.get("source_url"):
                        extracted_map[j["source_url"]] = j["extracted"]
            except Exception:  # noqa: BLE001
                extracted_map = {}

        todo = [j for j in jobs if j.get("source_url") not in extracted_map]
        retries = max(0, o["retries"])
        dash = _Dashboard(provider, len(jobs), pre_done=len(extracted_map)) if _RICH else None

        def _flush():
            for j in jobs:
                j["extracted"] = extracted_map.get(j.get("source_url"))
            out_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

        def extract_one(job):
            tname = threading.current_thread().name
            url = job.get("source_url")
            title = (job.get("title") or "")[:64]
            text = f"{job.get('title','')}\n\n{(job.get('description') or '')[: o['desc_chars']]}".strip()
            ex, last_err, was_exc = None, None, False
            for attempt in range(retries + 1):
                if dash:
                    dash.set_worker(tname, title, "retry" if attempt else "working", attempt)
                try:
                    ex = _to_extracted(llm_jd_extract(text))
                    was_exc = False
                    if ex.get("skills"):
                        return url, ex, None
                    last_err = "empty (no skills)"
                except Exception as e:  # noqa: BLE001
                    ex, was_exc, last_err = None, True, str(e)[:200]
                finally:
                    connection.close()
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
            return url, (None if was_exc else ex), last_err

        def _run():
            ok, completed = len(extracted_map), 0
            flush_every = max(1, o["flush_every"])
            with ThreadPoolExecutor(max_workers=max(1, o["workers"]), thread_name_prefix="worker") as pool:
                futs = [pool.submit(extract_one, j) for j in todo]
                for fut in as_completed(futs):
                    url, ex, err = fut.result()
                    good = ex is not None and url
                    if good:
                        extracted_map[url] = ex
                        ok += 1
                    elif err:
                        logger.warning("extract failed: %s", err)
                    completed += 1
                    if completed % flush_every == 0:
                        _flush()
                    if dash:
                        dash.tick(bool(good))
                    elif completed % 10 == 0:
                        self.stdout.write(f"  {provider}: {completed}/{len(todo)}")
            if dash:
                dash.idle_all()
            _flush()
            return ok

        if dash:
            with Live(dash, console=self._console, refresh_per_second=8, transient=False):
                return _run()
        return _run()
