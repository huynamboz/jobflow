"""Extract structured JD fields from crawled jobs using the LLM (LLMService /
llm_jd_extractor), writing data/extracted/<provider>/<date>.json.

Decouples extraction (the expensive LLM step) from the DB write: run this to
produce the extracted files, then `import_extracted` loads them with NO further
LLM call. Live dashboard shows each worker + the job title it's processing.

Usage:
    python manage.py extract_jobs                       # today, all providers
    python manage.py extract_jobs --provider remotive --workers 6
    python manage.py extract_jobs --provider jobspy --workers 2 --retries 3
"""
import glob
import json
import logging
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
        parser.add_argument("--workers", type=int, default=4, help="Parallel LLM calls")
        parser.add_argument("--retries", type=int, default=2, help="Retries on timeout/empty result per job")
        parser.add_argument("--desc-chars", type=int, default=6000, help="Truncate description per job (token cost)")
        parser.add_argument("--flush-every", type=int, default=10, help="Write the output file every N done jobs")
        parser.add_argument("--limit", type=int, default=0, help="Cap jobs per file (debug)")

    def handle(self, *args, **o):
        in_root = Path(o["in_dir"]) if o["in_dir"] else Path(settings.BASE_DIR) / "data" / "crawl"
        out_root = Path(o["out_dir"]) if o["out_dir"] else Path(settings.BASE_DIR) / "data" / "extracted"
        date = o["date"] or datetime.now().strftime("%Y-%m-%d")
        provider = o["provider"] or "*"
        files = sorted(glob.glob(str(in_root / provider / f"{date}.json")))
        if not files:
            self.stderr.write(self.style.WARNING(f"No crawl files under {in_root}/{provider}/{date}.json"))
            return

        self._console = Console() if _RICH else None
        total_ok = 0
        for f in files:
            total_ok += self._process_file(Path(f), out_root, date, o)

        msg = f"Done {date}. extracted {total_ok} jobs across {len(files)} file(s) -> {out_root}"
        if self._console:
            self._console.print(f"[bold green]✓ {msg}")
        else:
            self.stdout.write(self.style.SUCCESS(msg))

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
