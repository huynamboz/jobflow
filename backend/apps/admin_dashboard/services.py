"""Pure-function services backing each dashboard endpoint.

Each ``compute_*`` returns a dict matching the corresponding payload in
``specs/003-admin-dashboard-v2/data-model.md``. Views are thin shells —
they JSON-encode whatever the service returns.

Why pure functions: tested without HTTP / DRF; the same service can be
called by a CLI inspection helper later.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.db.models import Count, F, Q

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── KPI ─────────────────────────────────────────────────────────────────


def _freshness(started_at: datetime | None, now: datetime) -> str:
    if started_at is None:
        return "never"
    age_hours = (now - started_at).total_seconds() / 3600.0
    if age_hours <= 24:
        return "fresh"
    if age_hours <= 72:
        return "stale"
    return "very_stale"


def _last_run(command: str, now: datetime) -> dict:
    from apps.jobs.models import VerifierRunLog

    row = (
        VerifierRunLog.objects.filter(command=command, dry_run=False)
        .order_by("-started_at")
        .first()
    )
    return {
        "started_at": row.started_at.isoformat() if row else None,
        "command": command,
        "freshness": _freshness(row.started_at if row else None, now),
    }


def _auth_state() -> dict:
    from ml_service.crawler.providers.linkedin_auth import STATE_FILE
    from ml_service.verifier.auth_guard import has_li_at

    if not STATE_FILE.exists():
        return {"file_exists": False, "has_li_at": False}
    try:
        with STATE_FILE.open() as f:
            state = json.load(f)
        return {"file_exists": True, "has_li_at": has_li_at(state)}
    except Exception:
        return {"file_exists": True, "has_li_at": False}


def _model_meta() -> dict:
    """Active GNN checkpoint metadata. All-null if unreadable."""
    null_meta = {
        "checkpoint_name": None,
        "trained_at": None,
        "metrics": {
            "test_auc_roc": None,
            "ndcg_at_5": None,
            "mrr": None,
            "precision_at_5": None,
        },
        "calibration": None,
    }
    ckpt_dir = getattr(settings, "ML_CHECKPOINT_DIR", None)
    if not ckpt_dir:
        return null_meta
    meta_path = Path(ckpt_dir) / "meta.json"
    if not meta_path.exists():
        return null_meta
    try:
        with meta_path.open() as f:
            meta = json.load(f)
    except Exception:
        return null_meta
    metrics = meta.get("metrics", {}) or {}
    calib = meta.get("calibration") or None
    return {
        "checkpoint_name": meta.get("checkpoint_name") or Path(ckpt_dir).name,
        "trained_at": meta.get("trained_at"),
        "metrics": {
            "test_auc_roc": metrics.get("test_auc_roc"),
            "ndcg_at_5": metrics.get("ndcg_at_5"),
            "mrr": metrics.get("mrr"),
            "precision_at_5": metrics.get("precision_at_5"),
        },
        "calibration": calib,
    }


def compute_kpi(now: datetime | None = None) -> dict:
    from apps.cvs.models import CV
    from apps.jobs.models import Job

    now = now or _utcnow()

    job_totals = Job.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(lifecycle=Job.LIFECYCLE_ACTIVE)),
        stale=Count("id", filter=Q(lifecycle=Job.LIFECYCLE_STALE)),
        expired=Count("id", filter=Q(lifecycle=Job.LIFECYCLE_EXPIRED)),
        unverified=Count("id", filter=Q(lifecycle=Job.LIFECYCLE_UNVERIFIED)),
    )

    cv_total = CV.objects.count()
    cv_recent = CV.objects.filter(created_at__gte=now - timedelta(days=7)).count()

    return {
        "jobs_total": job_totals["total"] or 0,
        "jobs_by_lifecycle": {
            "active": job_totals["active"] or 0,
            "stale": job_totals["stale"] or 0,
            "expired": job_totals["expired"] or 0,
            "unverified": job_totals["unverified"] or 0,
        },
        "cv_total": cv_total,
        "cv_uploads_last_7d": cv_recent,
        "verifier_last_run": _last_run("verify_job_status", now),
        "extractor_last_run": _last_run("extract_job_dates", now),
        "auth_state": _auth_state(),
        "model": _model_meta(),
    }


# ─── Catalog composition ─────────────────────────────────────────────────


_SENIORITY_LABELS = {0: "Intern", 1: "Junior", 2: "Mid", 3: "Senior", 4: "Lead", 5: "Manager"}


def compute_catalog(now: datetime | None = None) -> dict:
    from apps.jobs.models import Job

    by_platform = list(
        Job.objects.values(key=F("platform__name"))
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    by_platform = [
        {"key": r["key"] or "Unknown", "count": r["count"]}
        for r in by_platform
        if r["count"] > 0
    ]

    by_lifecycle = list(
        Job.objects.values("lifecycle")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    by_lifecycle = [{"key": r["lifecycle"], "count": r["count"]} for r in by_lifecycle]

    by_role = list(
        Job.objects.exclude(role_category="")
        .values("role_category")
        .annotate(count=Count("id"))
        .order_by("-count")[:20]
    )
    by_role = [{"key": r["role_category"], "count": r["count"]} for r in by_role]

    by_sen_raw = list(
        Job.objects.values("seniority")
        .annotate(count=Count("id"))
        .order_by("seniority")
    )
    by_seniority = [
        {
            "key": r["seniority"],
            "label": _SENIORITY_LABELS.get(r["seniority"], f"L{r['seniority']}"),
            "count": r["count"],
        }
        for r in by_sen_raw
    ]

    return {
        "by_platform": by_platform,
        "by_lifecycle": by_lifecycle,
        "by_role_category": by_role,
        "by_seniority": by_seniority,
    }


# ─── Freshness & activity ────────────────────────────────────────────────


def compute_freshness(
    *,
    days_added: int = 30,
    days_outcomes: int = 14,
    now: datetime | None = None,
) -> dict:
    from django.db.models.functions import TruncDay

    from apps.jobs.models import Job, VerifierRunLog

    now = now or _utcnow()
    days_added = max(1, min(int(days_added), 90))
    days_outcomes = max(1, min(int(days_outcomes), 60))

    added_rows = (
        Job.objects.filter(created_at__gte=now - timedelta(days=days_added))
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    jobs_added = [
        {"day": r["day"].date().isoformat(), "count": r["count"]}
        for r in added_rows
        if r["day"] is not None
    ]

    runs = (
        VerifierRunLog.objects.filter(
            command=VerifierRunLog.COMMAND_VERIFY,
            dry_run=False,
            started_at__gte=now - timedelta(days=days_outcomes),
        )
        .annotate(day=TruncDay("started_at"))
        .values("day", "counts_by_outcome")
        .order_by("day")
    )

    by_day: dict[str, dict[str, int]] = {}
    for row in runs:
        if row["day"] is None:
            continue
        day = row["day"].date().isoformat()
        counts = row["counts_by_outcome"] or {}
        entry = by_day.setdefault(
            day,
            {"active": 0, "expired": 0, "unknown": 0, "error": 0, "session_expired": 0},
        )
        for k in entry.keys():
            entry[k] += int(counts.get(k) or 0)

    verifier_per_day = [{"day": d, **counts} for d, counts in sorted(by_day.items())]

    return {
        "jobs_added_per_day": jobs_added,
        "verifier_outcomes_per_day": verifier_per_day,
    }


# ─── Ops health ──────────────────────────────────────────────────────────


def compute_ops(
    *,
    recent_runs_limit: int = 20,
    now: datetime | None = None,
) -> dict:
    from apps.jobs.models import Job, VerifierRunLog

    now = now or _utcnow()
    recent_runs_limit = max(1, min(int(recent_runs_limit), 100))

    linkedin_qs = Job.objects.filter(platform__name__iexact="linkedin")
    totals = linkedin_qs.aggregate(
        total=Count("id"),
        with_date=Count("id", filter=Q(date_posted__isnull=False)),
        recent_verified=Count(
            "id", filter=Q(last_verified_at__gte=now - timedelta(days=30))
        ),
    )
    total = totals["total"] or 0
    with_date_pct = (totals["with_date"] / total) if total else 0.0
    recent_pct = (totals["recent_verified"] / total) if total else 0.0

    rows = list(
        VerifierRunLog.objects.order_by("-started_at").values(
            "id",
            "command",
            "started_at",
            "finished_at",
            "total_examined",
            "counts_by_outcome",
            "dry_run",
        )[:recent_runs_limit]
    )
    recent = []
    for r in rows:
        wall = 0.0
        if r["started_at"] and r["finished_at"]:
            wall = (r["finished_at"] - r["started_at"]).total_seconds()
        recent.append({
            "id": r["id"],
            "command": r["command"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "wall_clock_s": round(wall, 3),
            "total_examined": r["total_examined"],
            "counts_by_outcome": r["counts_by_outcome"] or {},
            "dry_run": r["dry_run"],
        })

    return {
        "coverage": {
            "linkedin_with_date_posted_pct": round(with_date_pct, 4),
            "linkedin_verified_last_30d_pct": round(recent_pct, 4),
        },
        "recent_runs": recent,
    }


# ─── Labeling ────────────────────────────────────────────────────────────


def compute_labeling(now: datetime | None = None) -> dict:
    """Mirror the existing /api/labeling/stats/ payload exactly."""
    from apps.labeling.models import PairQueue, PairStatus, SelectionReason

    total = PairQueue.objects.count()
    labeled = PairQueue.objects.filter(status=PairStatus.LABELED).count()
    skipped = PairQueue.objects.filter(status=PairStatus.SKIPPED).count()

    by_reason: dict[str, dict[str, int]] = {}
    for reason in SelectionReason.values:
        t = PairQueue.objects.filter(selection_reason=reason).count()
        ln = PairQueue.objects.filter(
            selection_reason=reason, status=PairStatus.LABELED
        ).count()
        by_reason[reason] = {"labeled": ln, "total": t}

    by_split: dict[str, dict[str, int]] = {}
    for split in ["train", "val", "test"]:
        t = PairQueue.objects.filter(split=split).count()
        ln = PairQueue.objects.filter(
            split=split, status=PairStatus.LABELED
        ).count()
        by_split[split] = {"labeled": ln, "total": t}

    return {
        "total_pairs": total,
        "labeled": labeled,
        "skipped": skipped,
        "pending": total - labeled - skipped,
        "by_reason": by_reason,
        "by_split": by_split,
    }


# ─── Model ───────────────────────────────────────────────────────────────


def compute_model(now: datetime | None = None) -> dict:
    return _model_meta()


# ─── Jobs overview (job-centric dashboard) ────────────────────────────────


def compute_jobs_overview(days: int = 30) -> dict:
    """Job-centric metrics for the main dashboard: stat cards + chart series.

    stats: total/active/inactive jobs, new today, jobs already applied, and
    suitable jobs found today (a match scored > 0.80 = >80%). per_day: new jobs
    created per day over the last ``days`` (default 30). by_provider: job count
    per platform.
    """
    from datetime import timedelta

    from django.db.models.functions import TruncDate
    from django.utils import timezone as dj_tz

    from apps.employees.models import EmployeeJobMatch
    from apps.jobs.models import Job

    days = max(1, min(int(days or 30), 90))
    today = dj_tz.localdate()

    total = Job.objects.count()
    active = Job.objects.filter(is_active=True).count()
    inactive = total - active
    new_today = Job.objects.filter(created_at__date=today).count()
    applied = (EmployeeJobMatch.objects
               .filter(status__in=EmployeeJobMatch.APPLIED_STATUSES)
               .values("job").distinct().count())
    suitable_today = (EmployeeJobMatch.objects
                      .filter(created_at__date=today, match_score__gt=0.8)
                      .values("job").distinct().count())

    # new jobs per day over the window (gap-filled so the chart has every day)
    since = today - timedelta(days=days - 1)
    rows = (Job.objects.filter(created_at__date__gte=since)
            .annotate(d=TruncDate("created_at")).values("d")
            .annotate(c=Count("id")))
    by_date = {r["d"]: r["c"] for r in rows}
    per_day = [
        {"day": (since + timedelta(days=i)).isoformat(), "count": by_date.get(since + timedelta(days=i), 0)}
        for i in range(days)
    ]

    prov = (Job.objects.values("platform__name", "platform__logo_url")
            .annotate(c=Count("id")).order_by("-c"))
    by_provider = [
        {
            "key": (r["platform__name"] or "Unknown"),
            "count": r["c"],
            "logo_url": r["platform__logo_url"] or "",
        }
        for r in prov
    ]

    return {
        "stats": {
            "total": total, "active": active, "inactive": inactive,
            "new_today": new_today, "applied": applied, "suitable_today": suitable_today,
        },
        "per_day": per_day,
        "by_provider": by_provider,
        "active_inactive": [
            {"key": "active", "count": active},
            {"key": "inactive", "count": inactive},
        ],
    }
