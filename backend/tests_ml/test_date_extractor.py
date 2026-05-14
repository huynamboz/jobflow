"""Unit tests for ml_service.verifier.date_extractor.

Spec: 002-job-date-posted-extraction (US1).
No Playwright runtime — tests use a FakePage shim that mimics the small
subset of the Playwright API the extractor uses (locator, count, nth,
get_attribute, inner_text, text_content, url).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ml_service.verifier.date_extractor import (
    DateExtractionResult,
    extract_date_posted,
    parse_relative,
)


# ─── FakePage / FakeLocator ──────────────────────────────────────────────


class FakeLocator:
    """Mimics Playwright Locator. Holds a list of dicts:
    each dict has 'attrs' (e.g. {'datetime': ...}), 'text', 'json' (string).
    """

    def __init__(self, items: list[dict]):
        self._items = items

    def count(self) -> int:
        return len(self._items)

    def nth(self, i: int) -> "FakeLocator":
        return FakeLocator([self._items[i]])

    @property
    def first(self) -> "FakeLocator":
        return FakeLocator([self._items[0]]) if self._items else FakeLocator([])

    def get_attribute(self, name: str) -> str | None:
        if not self._items:
            return None
        return self._items[0].get("attrs", {}).get(name)

    def inner_text(self) -> str:
        if not self._items:
            return ""
        return self._items[0].get("json") or self._items[0].get("text", "")

    def text_content(self, timeout: int | None = None) -> str:
        if not self._items:
            return ""
        return self._items[0].get("text", "")


class FakePage:
    """Routes locator(selector) calls to a pre-built mapping.

    ``evaluate(js)`` always returns ``treewalker_results`` (a list of text
    strings) so tests can simulate the TreeWalker fallback path without
    parsing JS. Defaults to an empty list — backward-compatible with
    existing tests.
    """

    def __init__(
        self,
        *,
        url: str = "https://www.linkedin.com/jobs/view/1/",
        routes: dict | None = None,
        treewalker_results: list[str] | None = None,
    ):
        self.url = url
        self._routes = routes or {}
        self._treewalker_results = treewalker_results or []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._routes.get(selector, []))

    def evaluate(self, js: str) -> list[str]:
        return self._treewalker_results


def _now():
    return datetime(2026, 5, 13, 12, 30, tzinfo=timezone.utc)


# ─── parse_relative ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,delta_days",
    [
        ("Posted today", 0),
        ("just now", 0),
        ("Yesterday", 1),
        ("1 hour ago", 0),
        ("5 minutes ago", 0),
        ("1 day ago", 1),
        ("3 days ago", 3),
        ("1 week ago", 7),
        ("2 weeks ago", 14),
        ("5 months ago", 150),
        ("1 year ago", 365),
        ("Posted 2 weeks ago", 14),
        ("Reposted 3 days ago", 3),
        ("POSTED 1 DAY AGO", 1),
    ],
)
def test_parse_relative_basic_units(text, delta_days):
    """T014, T015, T016: full parameter sweep of valid inputs."""
    now = _now()
    result = parse_relative(text, now)
    expected = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=delta_days)
    assert result == expected


@pytest.mark.parametrize(
    "text",
    ["", "no time here", "the year was 1999", "tomorrow", "before noon", "next week"],
)
def test_parse_relative_unmatched_returns_none(text):
    """T017"""
    assert parse_relative(text, _now()) is None


def test_parse_relative_handles_none_input():
    assert parse_relative(None, _now()) is None  # type: ignore[arg-type]


# ─── Guardrails ──────────────────────────────────────────────────────────


def test_guardrail_rejects_future_date():
    """T018: a datetime in the future via <time datetime> is discarded."""
    future = (_now() + timedelta(days=5)).date().isoformat()
    page = FakePage(routes={
        "div.job-details-jobs-unified-top-card__tertiary-description-container time[datetime]":
            [{"attrs": {"datetime": future}}]
    })
    result = extract_date_posted(page, now=_now())
    # No other source available → falls through to none
    assert result.source == "none"
    assert result.date is None


def test_guardrail_rejects_too_old_date():
    """T019: a datetime 3 years ago is rejected (> 730 day guardrail)."""
    too_old = (_now() - timedelta(days=3 * 365)).date().isoformat()
    page = FakePage(routes={
        "div.job-details-jobs-unified-top-card__tertiary-description-container time[datetime]":
            [{"attrs": {"datetime": too_old}}]
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "none"


# ─── Priority order ──────────────────────────────────────────────────────


def test_extract_priority_expired_redirect():
    """T020: trk=expired_jd_redirect short-circuits even with other content."""
    page = FakePage(
        url="https://www.linkedin.com/jobs/foo-jobs?trk=expired_jd_redirect",
        routes={
            "script[type=\"application/ld+json\"]": [
                {"json": json.dumps({"@type": "JobPosting", "datePosted": "2026-05-01"})},
            ],
        },
    )
    result = extract_date_posted(page, now=_now())
    assert result == DateExtractionResult(date=None, source="expired-redirect")


def test_extract_priority_json_ld_beats_datetime_and_relative():
    """T021"""
    page = FakePage(routes={
        "script[type=\"application/ld+json\"]": [
            {"json": json.dumps({"@type": "JobPosting", "datePosted": "2026-04-15"})},
        ],
        "div.job-details-jobs-unified-top-card__tertiary-description-container time[datetime]":
            [{"attrs": {"datetime": "2026-05-01"}}],
        "div.top-card-layout__second-subline":
            [{"text": "Posted 1 week ago"}],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "json-ld"
    assert result.date == datetime(2026, 4, 15, tzinfo=timezone.utc)


def test_extract_priority_datetime_beats_relative():
    """T022"""
    page = FakePage(routes={
        "script[type=\"application/ld+json\"]": [],
        "div.top-card-layout time[datetime]":
            [{"attrs": {"datetime": "2026-05-01"}}],
        "div.top-card-layout__second-subline":
            [{"text": "Posted 1 month ago"}],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "datetime-attribute"
    assert result.date == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_extract_falls_back_to_relative():
    """T023"""
    page = FakePage(routes={
        "div.top-card-layout__second-subline":
            [{"text": "Posted 1 week ago"}],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "relative-text"
    expected = _now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    assert result.date == expected


def test_extract_unscoped_time_in_more_jobs_panel_is_ignored():
    """T024: a <time datetime> on a non-allowed selector must NOT be picked."""
    # Route only an unallowed selector — no scoped match
    page = FakePage(routes={
        # NOT in _SCOPED_DATETIME_SELECTORS
        "div.people-also-viewed time[datetime]":
            [{"attrs": {"datetime": "2026-05-01"}}],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "none"


def test_extract_json_ld_picks_jobposting_among_many():
    """T025: page has multiple JSON-LD blocks; only JobPosting is selected."""
    page = FakePage(routes={
        "script[type=\"application/ld+json\"]": [
            {"json": json.dumps({"@type": "Organization", "name": "ACME"})},
            {"json": json.dumps({"@type": "BreadcrumbList"})},
            {"json": json.dumps({"@type": "JobPosting", "datePosted": "2026-04-20"})},
        ],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "json-ld"
    assert result.date == datetime(2026, 4, 20, tzinfo=timezone.utc)


def test_extract_returns_utc_midnight():
    """T026: the returned datetime is tz-aware UTC at midnight."""
    page = FakePage(routes={
        "script[type=\"application/ld+json\"]": [
            {"json": json.dumps({"@type": "JobPosting", "datePosted": "2026-04-15T14:23:00Z"})},
        ],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "json-ld"
    assert result.date.tzinfo == timezone.utc
    assert result.date.hour == 0
    assert result.date.minute == 0


def test_extract_does_not_raise_on_broken_json_ld():
    """T027: malformed JSON-LD is swallowed; fallback chain continues."""
    page = FakePage(routes={
        "script[type=\"application/ld+json\"]": [
            {"json": "{not-valid-json"},
            {"json": "another-broken-one"},
        ],
        "div.top-card-layout__second-subline":
            [{"text": "Posted 5 days ago"}],
    })
    result = extract_date_posted(page, now=_now())
    assert result.source == "relative-text"


def test_extract_returns_none_when_no_source_available():
    page = FakePage(routes={})
    result = extract_date_posted(page, now=_now())
    assert result == DateExtractionResult(date=None, source="none")


def test_extract_falls_back_to_treewalker_text():
    """When obfuscated CSS classes hide the date from scoped selectors, the
    TreeWalker fallback finds it inside <main>. This is the path LinkedIn's
    authenticated layout requires (class names like _47c88858).
    """
    page = FakePage(
        routes={},  # No scoped match
        treewalker_results=["Some unrelated text", "Reposted 6 days ago", "Singapore, Singapore"],
    )
    result = extract_date_posted(page, now=_now())
    assert result.source == "relative-text"
    expected = _now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    assert result.date == expected


# ─── Backfill orchestrator tests (US2) ────────────────────────────────────


from contextlib import contextmanager
from ml_service.verifier.backfill_service import DateBackfillService, BackfillReport
from ml_service.verifier.base import JobStatus, VerifyResult


class FakeRepo:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.date_writes: list[tuple[int, datetime]] = []
        self.result_writes: list[tuple[int, JobStatus]] = []

    def find_to_backfill_dates(self, *, platform, batch, now):
        return [r for r in self.rows if r.get("date_posted") is None][:batch]

    def apply_date(self, job_id, date, *, now):
        self.date_writes.append((job_id, date))

    def apply_result(self, job_id, result, *, now):
        self.result_writes.append((job_id, result.status))


class FakeCtx:
    def __init__(self, cookies_have_li_at: bool = True):
        self._cookies_have_li_at = cookies_have_li_at

    def cookies(self):
        if self._cookies_have_li_at:
            return [{"name": "li_at", "domain": ".linkedin.com"}]
        return [{"name": "lidc", "domain": ".linkedin.com"}]


class FakePageWithGoto:
    def __init__(self):
        self.url = ""
        self.visits: list[str] = []

    def goto(self, url, **kwargs):
        self.url = url
        self.visits.append(url)


def _fake_browser_factory(*, cookies_have_li_at=True, page=None):
    page = page or FakePageWithGoto()
    ctx = FakeCtx(cookies_have_li_at=cookies_have_li_at)

    @contextmanager
    def factory():
        yield page, ctx

    return factory, page, ctx


def _make_extractor(scripted):
    """scripted: dict[url -> DateExtractionResult OR Exception]"""
    def extractor(page, *, now=None):
        item = scripted.get(page.url)
        if isinstance(item, Exception):
            raise item
        if item is not None:
            return item
        return DateExtractionResult(date=None, source="none")
    return extractor


def _make_service(*, rows, scripted, browser_factory=None):
    if browser_factory is None:
        browser_factory, _, _ = _fake_browser_factory()
    repo = FakeRepo(rows)
    svc = DateBackfillService(
        extractor=_make_extractor(scripted),
        repository=repo,
        browser_factory=browser_factory,
        clock=lambda: datetime(2026, 5, 13, 12, tzinfo=timezone.utc),
        url_supports=lambda u: True,
    )
    return svc, repo


def test_backfill_orchestrator_writes_date_when_populated():
    """T030"""
    rows = [{"id": 1, "source_url": "https://www.linkedin.com/jobs/view/1/", "date_posted": None}]
    scripted = {"https://www.linkedin.com/jobs/view/1/":
                DateExtractionResult(date=datetime(2026, 4, 15, tzinfo=timezone.utc), source="json-ld")}
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=5, dry_run=False)
    assert report.populated_count == 1
    assert len(repo.date_writes) == 1
    assert repo.date_writes[0][1] == datetime(2026, 4, 15, tzinfo=timezone.utc)


def test_backfill_orchestrator_marks_expired_on_redirect():
    """T031"""
    rows = [{"id": 1, "source_url": "https://www.linkedin.com/jobs/view/1/", "date_posted": None}]
    scripted = {"https://www.linkedin.com/jobs/view/1/":
                DateExtractionResult(date=None, source="expired-redirect")}
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=5, dry_run=False)
    assert report.expired_marked_count == 1
    assert len(repo.date_writes) == 0
    assert (1, JobStatus.EXPIRED) in repo.result_writes


def test_backfill_orchestrator_increments_attempts_on_none():
    """T032"""
    rows = [{"id": 1, "source_url": "https://www.linkedin.com/jobs/view/1/", "date_posted": None}]
    scripted = {"https://www.linkedin.com/jobs/view/1/":
                DateExtractionResult(date=None, source="none")}
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=5, dry_run=False)
    assert report.none_count == 1
    assert (1, JobStatus.UNKNOWN) in repo.result_writes


def test_backfill_dry_run_skips_writes():
    """T033"""
    rows = [{"id": 1, "source_url": "https://www.linkedin.com/jobs/view/1/", "date_posted": None}]
    scripted = {"https://www.linkedin.com/jobs/view/1/":
                DateExtractionResult(date=datetime(2026, 4, 15, tzinfo=timezone.utc), source="json-ld")}
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=5, dry_run=True)
    assert report.populated_count == 1
    assert report.dry_run is True
    assert len(repo.date_writes) == 0
    assert len(repo.result_writes) == 0


def test_backfill_candidate_selection_skips_filled():
    """T034"""
    rows = [
        {"id": 1, "source_url": "url1", "date_posted": None},
        {"id": 2, "source_url": "url2", "date_posted": datetime(2026, 4, 1, tzinfo=timezone.utc)},
        {"id": 3, "source_url": "url3", "date_posted": None},
    ]
    scripted = {
        "url1": DateExtractionResult(date=datetime(2026, 4, 10, tzinfo=timezone.utc), source="json-ld"),
        "url3": DateExtractionResult(date=datetime(2026, 4, 11, tzinfo=timezone.utc), source="json-ld"),
    }
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=10, dry_run=False)
    assert report.total_examined == 2
    job_ids_visited = {jid for (jid, _) in repo.date_writes}
    assert job_ids_visited == {1, 3}


def test_backfill_continues_when_li_at_lost_mid_batch():
    """Updated semantic (post-investigation 2026-05-13): when LinkedIn drops
    li_at mid-batch, the verifier/extractor downgrades to guest layout but
    keeps walking URLs. The extractor's URL-pattern + guest-marker checks
    handle both layouts. We do NOT bail.
    """
    rows = [
        {"id": i, "source_url": f"https://www.linkedin.com/jobs/view/{i}/", "date_posted": None}
        for i in range(1, 6)
    ]
    page = FakePageWithGoto()

    class DroppingCtx:
        def __init__(self):
            self.visits = 0

        def cookies(self):
            self.visits += 1
            if self.visits >= 3:
                return [{"name": "lidc", "domain": ".linkedin.com"}]
            return [{"name": "li_at", "domain": ".linkedin.com"}]

    @contextmanager
    def factory():
        yield page, DroppingCtx()

    scripted = {
        f"https://www.linkedin.com/jobs/view/{i}/":
            DateExtractionResult(date=datetime(2026, 4, 10, tzinfo=timezone.utc), source="json-ld")
        for i in range(1, 6)
    }
    repo = FakeRepo(rows)
    svc = DateBackfillService(
        extractor=_make_extractor(scripted),
        repository=repo,
        browser_factory=factory,
        clock=lambda: datetime(2026, 5, 13, 12, tzinfo=timezone.utc),
        url_supports=lambda u: True,
        per_url_delay_s=0,
        per_url_jitter_s=0,
    )
    report = svc.run(platform="linkedin", batch=10, dry_run=False)
    # All 5 walked; no bail. li_at loss is a debug-log signal only.
    assert report.total_examined == 5
    assert report.populated_count == 5
    assert report.session_expired_count == 0


def test_backfill_service_isolates_per_url_exceptions():
    """T035b (C3 fix) — exception on one URL doesn't abort the batch."""
    rows = [
        {"id": i, "source_url": f"u{i}", "date_posted": None} for i in range(1, 6)
    ]
    scripted = {
        "u1": DateExtractionResult(date=datetime(2026, 4, 10, tzinfo=timezone.utc), source="json-ld"),
        "u2": DateExtractionResult(date=datetime(2026, 4, 11, tzinfo=timezone.utc), source="json-ld"),
        "u3": RuntimeError("simulated extractor failure"),
        "u4": DateExtractionResult(date=datetime(2026, 4, 13, tzinfo=timezone.utc), source="json-ld"),
        "u5": DateExtractionResult(date=datetime(2026, 4, 14, tzinfo=timezone.utc), source="json-ld"),
    }
    svc, repo = _make_service(rows=rows, scripted=scripted)
    report = svc.run(platform="linkedin", batch=10, dry_run=False)
    assert report.total_examined == 5
    assert report.error_count == 1
    assert report.populated_count == 4
