"""Backfill `salary_period` + `salary_usd_annual_*` for jobs ingested before the
period field existed.

The original pay period was DROPPED at crawl time, so it can't be recovered
exactly — this is a best-effort heuristic: convert the raw number to USD, then
guess the period from its magnitude (hourly rates are small, annual salaries are
large). New crawls carry the real provider interval and don't need this.

    python manage.py backfill_salary_period --dry-run   # preview the distribution
    python manage.py backfill_salary_period             # apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.jobs.models import Job
from apps.jobs.services.salary_normalizer import _TO_USD, normalize_salary_range

# USD-equivalent magnitude thresholds → guessed period.
_HOURLY_MAX = 200       # ≤ $200  → an hourly rate
_MONTHLY_MAX = 20_000   # ≤ $20k  → a monthly figure; above → annual


def _guess_period(amount: int, currency: str) -> str:
    usd = amount * _TO_USD.get((currency or "USD").upper(), 1.0)
    if usd <= _HOURLY_MAX:
        return "hourly"
    if usd <= _MONTHLY_MAX:
        return "monthly"
    return "annual"


class Command(BaseCommand):
    help = "Heuristically backfill salary_period + USD-annual for legacy jobs."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
        parser.add_argument("--all", action="store_true",
                            help="Re-evaluate every job (default: only period='unknown').")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        qs = Job.objects.exclude(salary_min=0, salary_max=0)
        if not opts["all"]:
            qs = qs.filter(salary_period=Job.SalaryPeriod.UNKNOWN)

        buckets: dict[str, int] = {}
        updated = 0
        for job in qs.iterator():
            ref = job.salary_max or job.salary_min  # bigger bound is the more stable signal
            period = _guess_period(ref, job.salary_currency)
            usd_min, usd_max = normalize_salary_range(
                job.salary_min, job.salary_max, job.salary_currency, period)
            buckets[period] = buckets.get(period, 0) + 1
            if not dry:
                Job.objects.filter(id=job.id).update(
                    salary_period=period,
                    salary_usd_annual_min=usd_min,
                    salary_usd_annual_max=usd_max,
                )
            updated += 1

        verb = "would set" if dry else "set"
        self.stdout.write(f"{verb} salary_period on {updated} jobs")
        for p, n in sorted(buckets.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {p:8s} {n}")
        if dry:
            self.stdout.write(self.style.WARNING("dry-run — nothing written. Re-run without --dry-run to apply."))
