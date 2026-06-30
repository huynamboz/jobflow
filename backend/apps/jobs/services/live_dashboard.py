"""Full-terminal live dashboards for long-running crawl / verify commands.

A single reusable ``LiveDashboard`` renders a pinned overview panel on top
(aggregate status — counts, totals, elapsed) and a live-scrolling table of the
individual requests below, inside rich's alternate-screen ``Live``. The crawl
and verify commands share it via thin config (columns + an overview formatter).

Only use it on a real terminal — callers gate on ``console.is_terminal`` /
``isatty`` and fall back to the plain line output for pipes / cron / JSON.
"""

from __future__ import annotations

import threading
import time
from collections import deque


def fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class LiveDashboard:
    """Overview panel + live-scrolling request table, full-terminal.

    ``columns`` is a list of dicts: ``{header, justify?, style?, width?, ratio?}``.
    ``overview`` is ``callable(state: dict, elapsed: float) -> str`` (rich markup)
    rendered inside the top panel; ``overview_height`` is its line count (used to
    reserve space so the table fills the rest of the screen without overflowing).
    """

    def __init__(self, *, title, columns, overview, overview_height=2,
                 console=None, border_style="cyan", refresh=8, screen=True):
        self.title = title
        self.columns = columns
        self._overview = overview
        self._overview_h = overview_height
        self._border = border_style
        self._refresh = refresh
        self._screen = screen
        self._state: dict = {}
        self._rows: deque = deque(maxlen=2000)
        self._start = time.monotonic()
        self._lock = threading.Lock()
        from rich.console import Console
        self._console = console or Console()
        self._live = None

    # ── state mutation ──────────────────────────────────────────────────────
    def set(self, **kw) -> None:
        with self._lock:
            self._state.update(kw)
        self._touch()

    def inc(self, key: str, by: int = 1) -> None:
        with self._lock:
            self._state[key] = self._state.get(key, 0) + by
        self._touch()

    def row(self, *cells, style=None) -> None:
        with self._lock:
            self._rows.append((tuple("" if c is None else str(c) for c in cells), style))
        self._touch()

    def get(self, key: str, default=0):
        return self._state.get(key, default)

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    # ── lifecycle ───────────────────────────────────────────────────────────
    def open(self) -> "LiveDashboard":
        from rich.live import Live
        self._live = Live(
            self, console=self._console, screen=self._screen,
            refresh_per_second=self._refresh, transient=False,
        )
        self._live.start()
        return self

    def close(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def _touch(self) -> None:
        if self._live is not None:
            try:
                self._live.refresh()
            except Exception:
                pass

    # ── rendering ───────────────────────────────────────────────────────────
    def __rich__(self):
        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table
        from rich import box

        el = self.elapsed()
        with self._lock:
            overview = self._overview(dict(self._state), el)
            rows = list(self._rows)

        panel = Panel(
            overview, title=f"[bold]{self.title}[/]", title_align="left",
            border_style=self._border, box=box.ROUNDED, padding=(0, 1),
        )

        table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
        for col in self.columns:
            table.add_column(
                col["header"], justify=col.get("justify", "left"),
                style=col.get("style"), width=col.get("width"),
                ratio=col.get("ratio"), no_wrap=True, overflow="ellipsis",
            )

        try:
            height = self._console.size.height
        except Exception:
            height = 40
        # panel (2 borders + title + padding) + table header + safety margin
        reserve = self._overview_h + 7
        visible = max(3, height - reserve)
        if len(rows) > visible:
            rows = rows[-visible:]
        for cells, style in rows:
            table.add_row(*cells, style=style)

        return Group(panel, table)


# ── crawl config ────────────────────────────────────────────────────────────

def _crawl_overview(s: dict, el: float) -> str:
    return (
        f"provider [cyan]{s.get('provider', '-')}[/]     "
        f"keyword [bold]{s.get('kw_i', 0)}/{s.get('kw_n', 0)}[/]  ⟳ [dim]{s.get('kw', '')}[/]"
        f"     elapsed {fmt_elapsed(el)}\n"
        f"[green]found {s.get('found', 0)}[/]     [green]+new {s.get('new', 0)}[/]"
        f"     [blue]🖼 logo {s.get('logos', 0)}[/]     [magenta]⚠ fail {s.get('fails', 0)}[/]"
    )


_CRAWL_COLUMNS = [
    {"header": "#", "justify": "right", "width": 5, "style": "dim"},
    {"header": "title", "ratio": 3},
    {"header": "company", "ratio": 2},
    {"header": "location", "ratio": 2, "style": "dim"},
    {"header": "logo", "justify": "center", "width": 5},
]


class CrawlDashboard(LiveDashboard):
    """Full-terminal crawl dashboard. Exposes the ``_RichProgress`` hook
    interface (``start``/``tick``/``live``/``finish``/``close``) so ``run_crawl``
    can drive it unchanged, while rendering each scraped job as a table row."""

    def __init__(self, console, providers, kw_total: int, title="Crawl"):
        super().__init__(
            title=title, columns=_CRAWL_COLUMNS, overview=_crawl_overview,
            overview_height=2, console=console,
        )
        self._seq = 0
        self.set(kw_n=kw_total)
        self.open()

    # run_crawl hooks ─────────────────────────────────────────────────────
    def start(self, provider: str, total: int) -> None:  # noqa: A003 — hook name
        self.set(provider=provider, kw_n=total)

    def tick(self, provider: str, found_total: int, keyword: str) -> None:
        self.set(provider=provider, kw_i=self.get("kw_i", 0) + 1,
                 found=found_total, kw=keyword)

    def live(self, provider: str, found_running: int, keyword: str, job=None) -> None:
        self.set(provider=provider, kw=keyword, found=found_running)
        if job is not None:
            self._seq += 1
            has_logo = bool(getattr(job, "company_logo_url", ""))
            if has_logo:
                self.inc("logos")
            self.row(
                self._seq,
                getattr(job, "title", ""),
                getattr(job, "company", ""),
                getattr(job, "location", ""),
                "🖼" if has_logo else "[dim]-[/]",
            )

    def finish(self, provider: str, res: dict) -> None:
        if res.get("error"):
            self.set(kw=f"[red]ERROR {str(res['error'])[:40]}[/]")
        else:
            self.set(new=res.get("added", 0), found=res.get("crawled", 0),
                     fails=res.get("fails", 0), kw="[green]done ✓[/]")


# ── verify config ───────────────────────────────────────────────────────────

def _verify_overview(s: dict, el: float) -> str:
    return (
        f"platform [cyan]{s.get('platform', '-')}[/]     "
        f"[bold]{s.get('done', 0)}/{s.get('total', 0)}[/]     elapsed {fmt_elapsed(el)}\n"
        f"[green]✓ active {s.get('active', 0)}[/]   [red]✗ expired {s.get('expired', 0)}[/]   "
        f"[yellow]? unknown {s.get('unknown', 0)}[/]   [magenta]! error {s.get('error', 0)}[/]   "
        f"[blue]🖼 logos {s.get('logos', 0)}[/]"
    )


_VERIFY_COLUMNS = [
    {"header": "#", "justify": "right", "width": 5, "style": "dim"},
    {"header": "job", "justify": "right", "width": 8},
    {"header": "status", "width": 16},
    {"header": "url", "ratio": 1, "style": "dim"},
    {"header": "logo", "justify": "center", "width": 5},
]


def make_verify_dashboard(console, platform: str, total: int) -> LiveDashboard:
    dash = LiveDashboard(
        title="Verify job status", columns=_VERIFY_COLUMNS,
        overview=_verify_overview, overview_height=2, console=console,
    )
    dash.set(platform=platform, total=total, done=0,
             active=0, expired=0, unknown=0, error=0, logos=0)
    return dash
