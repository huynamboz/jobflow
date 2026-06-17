"""Normalize raw salary values to a common unit: USD annual.

Salary numbers arrive from many providers in different pay PERIODS (hourly,
monthly, yearly, …). We keep the raw number + its period for honest display, and
ALSO compute a USD-annual equivalent so salaries are comparable across postings.
"""

from __future__ import annotations

# Approximate rates to USD (1 unit of currency = N USD)
_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "VND": 1 / 25_000,
    "EUR": 1.08,
    "GBP": 1.27,
    "SGD": 0.74,
    "JPY": 1 / 150,
    "KRW": 1 / 1_300,
    "AUD": 0.65,
    "CAD": 0.74,
    "INR": 1 / 83,
    "THB": 1 / 35,
    "MYR": 1 / 4.7,
    "PHP": 1 / 56,
    "IDR": 1 / 15_700,
}

# Canonical pay periods (single source of truth — mirrored by Job.SalaryPeriod).
CANONICAL_PERIODS = ("hourly", "daily", "weekly", "monthly", "annual", "unknown")

# Multiplier to convert one period → annual
_TO_ANNUAL: dict[str, float] = {
    "annual":  1.0,
    "monthly": 12.0,
    "weekly":  52.0,
    "daily":   260.0,        # 52 weeks × 5 work days
    "hourly":  52.0 * 40.0,  # 52 weeks × 40 hrs
    "unknown": 12.0,         # assume monthly when unclear
}

# Map the many provider/LLM spellings → a canonical period.
_PERIOD_ALIASES: dict[str, str] = {
    "year": "annual", "yearly": "annual", "annual": "annual", "annually": "annual", "yr": "annual", "annum": "annual",
    "month": "monthly", "monthly": "monthly", "mo": "monthly", "mth": "monthly",
    "week": "weekly", "weekly": "weekly", "wk": "weekly",
    "day": "daily", "daily": "daily",
    "hour": "hourly", "hourly": "hourly", "hr": "hourly",
}


def canonical_period(raw: str | None) -> str:
    """Map a free-form interval string (e.g. 'yearly', 'per hour') → canonical
    period. Returns 'unknown' when it can't be matched."""
    if not raw:
        return "unknown"
    key = str(raw).strip().lower()
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    # tolerate phrases like "per year", "/hr", "an hour"
    for alias, canon in _PERIOD_ALIASES.items():
        if alias in key:
            return canon
    return "unknown"


def to_usd_annual(amount: int, currency: str, period: str) -> int:
    """Convert a raw salary value to USD annual equivalent.

    Returns 0 if amount is 0 or conversion is not possible.
    """
    if amount <= 0:
        return 0
    rate = _TO_USD.get(currency.upper(), 1.0)
    multiplier = _TO_ANNUAL.get(canonical_period(period), 12.0)
    return int(amount * rate * multiplier)


def normalize_salary_range(
    salary_min: int,
    salary_max: int,
    currency: str,
    period: str,
) -> tuple[int, int]:
    """Return (usd_annual_min, usd_annual_max)."""
    usd_min = to_usd_annual(salary_min, currency, period)
    usd_max = to_usd_annual(salary_max, currency, period)
    # If only one bound given, mirror it
    if usd_min > 0 and usd_max == 0:
        usd_max = usd_min
    if usd_max > 0 and usd_min == 0:
        usd_min = usd_max
    return usd_min, usd_max
