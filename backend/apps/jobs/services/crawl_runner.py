"""Shared crawl runner — providers in parallel, per-provider dated JSON files.

`crawl_jobs` (ad-hoc) and `crawl_daily` (master IT/AI sweep) both call
`live_crawl`, which renders a live rich dashboard (one progress bar per provider)
and writes per-provider dated files. No DB write:

    <out-dir>/<provider>/<YYYY-MM-DD>.json   (JSON array, merge-dedup by url)
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from django.conf import settings

from ml_service.crawler import get_provider, list_providers
from ml_service.crawler.storage import _raw_job_to_dict

_print_lock = threading.Lock()

# Providers excluded from the "all"/daily default sweep:
#   linkedin — needs login + Playwright (heavy, rate-limited) → use crawl_linkedin
#   adzuna   — needs an API key (ADZUNA_APP_ID / ADZUNA_APP_KEY)
# Reach either explicitly via --providers / --provider.
DEFAULT_EXCLUDED = {"linkedin", "adzuna"}


def default_providers() -> list[str]:
    """Auto-discovered providers minus the ones excluded by default (see DEFAULT_EXCLUDED)."""
    return [p for p in list_providers() if p not in DEFAULT_EXCLUDED]


# Curated IT / Software / AI keyword sweep for the daily master crawl.
IT_AI_KEYWORDS: list[str] = [
    # Software engineering
    "software engineer", "backend developer", "frontend developer",
    "fullstack developer", "web developer", "mobile developer",
    "android developer", "ios developer", "react developer",
    "react native developer", "vue developer", "angular developer",
    "node.js developer", "python developer", "java developer",
    "golang developer", "php developer", "ruby developer",
    ".net developer", "c++ developer", "rust developer",
    "typescript developer", "flutter developer", "wordpress developer",
    # Data / AI / ML
    "data engineer", "data scientist", "data analyst",
    "machine learning engineer", "ai engineer", "ml engineer",
    "deep learning engineer", "nlp engineer", "computer vision engineer",
    "mlops engineer", "llm engineer", "generative ai engineer",
    "ai researcher", "prompt engineer",
    # DevOps / Cloud / Infra
    "devops engineer", "site reliability engineer", "cloud engineer",
    "aws engineer", "kubernetes engineer", "platform engineer",
    "infrastructure engineer",
    # QA / Security / Other IT
    "qa engineer", "automation test engineer", "security engineer",
    "cybersecurity engineer", "database administrator", "system administrator",
    "network engineer", "blockchain developer", "game developer",
    "embedded engineer", "solutions architect", "software architect",
]


# Curated, smaller role set for the LinkedIn master crawl — LinkedIn launches a
# browser per query and rate-limits hard, so keep this targeted (not the full
# IT_AI_KEYWORDS sweep).
LINKEDIN_ROLES: list[str] = [
    "frontend developer", "backend developer", "fullstack developer",
    "react developer", "python developer", "java developer",
    "nodejs developer", "software engineer", "mobile developer",
    "devops engineer", "data engineer", "data scientist",
    "machine learning engineer", "ai engineer", "cloud engineer", "qa engineer",
]


# ── core crawl (UI-agnostic) ──────────────────────────────────────────────────

def run_crawl(
    providers: list[str],
    queries: list[str],
    results_wanted: int = 50,
    location: str = "",
    out_dir: str = "",
    workers: int = 0,
    request_delay: float = 1.0,
    serial: bool = False,
    provider_kwargs: dict | None = None,
    log=print,
    progress=None,
) -> dict:
    """Crawl `queries` across `providers`, writing per-provider dated files.
    Parallel (thread per provider) by default; `serial=True` runs everything in
    the calling thread (needed for browser providers like LinkedIn, where
    Playwright is unreliable off the main thread). `request_delay` throttles each
    provider to ~1 request / `request_delay`s between keywords. `progress`
    (if given) receives start/tick/finish hooks for a live UI."""
    out_root = Path(out_dir) if out_dir else Path(settings.BASE_DIR) / "data" / "crawl"
    date_str = datetime.now().strftime("%Y-%m-%d")
    workers = workers or max(1, len(providers))

    def crawl_one(pname: str) -> dict:
        if progress:
            progress.start(pname, len(queries))
        try:
            p = get_provider(pname, **(provider_kwargs or {}))
            jobs, fails = [], 0
            for i, q in enumerate(queries):
                if i and request_delay:
                    time.sleep(request_delay)  # throttle between keywords
                try:
                    jobs.extend(p.fetch(q, location=location, results_wanted=results_wanted))
                except Exception as e:  # noqa: BLE001 — one query failing ≠ kill provider
                    fails += 1
                    if not progress:
                        with _print_lock:
                            log(f"  {pname} → {q!r}: FAILED ({e})")
                if progress:
                    progress.tick(pname, len(jobs), q)
            added, total = _merge_write(out_root / pname / f"{date_str}.json", jobs)
            res = {"provider": pname, "crawled": len(jobs), "added": added, "total": total, "fails": fails}
        except Exception as e:  # noqa: BLE001 — provider init/fetch crash
            res = {"provider": pname, "error": str(e)}
        if progress:
            progress.finish(pname, res)
        return res

    def _emit(r: dict) -> None:
        if progress:
            return
        with _print_lock:
            if r.get("error"):
                log(f"  ✗ {r['provider']}: {r['error']}")
            else:
                log(f"  ✓ {r['provider']}: crawled {r['crawled']} → +{r['added']} new ({r['total']} in {date_str}.json)")

    results: list[dict] = []
    if serial:
        for pn in providers:
            r = crawl_one(pn)
            results.append(r)
            _emit(r)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="crawl") as pool:
            futures = {pool.submit(crawl_one, pn): pn for pn in providers}
            for fut in as_completed(futures):
                r = fut.result()
                results.append(r)
                _emit(r)

    total_added = sum(r.get("added", 0) for r in results)
    return {"date": date_str, "out_root": str(out_root), "total_added": total_added, "results": results}


def _merge_write(path: Path, jobs: list) -> tuple[int, int]:
    """Merge RawJobs into the day's JSON array (dedup by source_url). Returns
    (added, total)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = []
    seen = {o.get("source_url") for o in existing if o.get("source_url")}
    added = 0
    for job in jobs:
        d = _raw_job_to_dict(job)
        url = d.get("source_url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        existing.append(d)
        added += 1
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return added, len(existing)


# ── live rich dashboard ───────────────────────────────────────────────────────

class _RichProgress:
    """One live progress bar per provider (thread-safe via rich's own lock)."""

    def __init__(self, console, providers: list[str]) -> None:
        from rich.progress import (
            Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn, TimeElapsedColumn,
        )
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.fields[prov]:<13}"),
            BarColumn(bar_width=24),
            MofNCompleteColumn(),
            TextColumn("[green]+{task.fields[new]} new"),
            TextColumn("[dim]{task.fields[found]} found"),
            TextColumn("[dim]{task.fields[kw]}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._tasks: dict[str, int] = {}
        self._lock = threading.Lock()
        self._progress.start()

    def start(self, provider: str, total: int) -> None:
        with self._lock:
            self._tasks[provider] = self._progress.add_task(
                "", total=total, prov=provider, new=0, found=0, kw="",
            )

    def tick(self, provider: str, found_total: int, keyword: str) -> None:
        tid = self._tasks.get(provider)
        if tid is not None:
            self._progress.update(tid, advance=1, found=found_total, kw=keyword[:26])

    def finish(self, provider: str, res: dict) -> None:
        tid = self._tasks.get(provider)
        if tid is None:
            return
        if res.get("error"):
            self._progress.update(tid, kw="[red]ERROR")
        else:
            self._progress.update(tid, new=res.get("added", 0), found=res.get("crawled", 0), kw="[green]done ✓")

    def close(self) -> None:
        self._progress.stop()


def live_crawl(
    providers: list[str],
    queries: list[str],
    results_wanted: int = 50,
    location: str = "",
    out_dir: str = "",
    workers: int = 0,
    request_delay: float = 1.0,
    serial: bool = False,
    provider_kwargs: dict | None = None,
    title: str = "Crawl",
) -> dict:
    """Run a crawl with a live rich dashboard (header panel → per-provider bars →
    summary table). Falls back to plain logging if rich is unavailable."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich import box
    except ImportError:
        print(f"{title}: {len(providers)} providers × {len(queries)} keywords × {results_wanted}")
        s = run_crawl(providers, queries, results_wanted, location, out_dir, workers, request_delay, serial,
                      provider_kwargs=provider_kwargs, log=print)
        print(f"Done {s['date']}. {s['total_added']} new → {s['out_root']}")
        return s

    console = Console()
    console.print(Panel.fit(
        f"[bold cyan]{title}[/]\n"
        f"[dim]{len(providers)} providers · {len(queries)} keywords · "
        f"{results_wanted} results/kw · {workers or len(providers)} workers · {request_delay}s/req[/]",
        border_style="cyan", box=box.ROUNDED,
    ))

    prog = _RichProgress(console, providers)
    summary = run_crawl(
        providers, queries, results_wanted=results_wanted, location=location,
        out_dir=out_dir, workers=workers, request_delay=request_delay, serial=serial,
        provider_kwargs=provider_kwargs, log=lambda *_: None, progress=prog,
    )
    prog.close()

    table = Table(box=box.SIMPLE_HEAD, title=f"[bold]✓ Done {summary['date']} — {summary['total_added']} new jobs[/]", title_justify="left")
    table.add_column("Provider", style="cyan")
    table.add_column("New", justify="right", style="green")
    table.add_column("In file", justify="right", style="dim")
    table.add_column("Status")
    for r in sorted(summary["results"], key=lambda x: x["provider"]):
        if r.get("error"):
            table.add_row(r["provider"], "—", "—", f"[red]✗ {str(r['error'])[:44]}")
        else:
            fail_note = f" [yellow]({r['fails']} kw failed)" if r.get("fails") else ""
            table.add_row(r["provider"], f"+{r['added']}", str(r["total"]), f"[green]✓{fail_note}")
    console.print(table)
    console.print(f"[dim]→ {summary['out_root']}[/]")
    return summary
