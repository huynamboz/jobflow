"""Pure-Python lifecycle filter helper.

Separated from ``matching_service`` so the unit test can import it without
booting Django. ``matching_service`` re-exports the symbol for backward
compatibility.

Spec: 001-linkedin-job-verifier (US1, FR-008).
"""

from __future__ import annotations


_ALLOWED_LIFECYCLES = frozenset({"active", "stale", "unverified"})


def filter_active_jobs(
    ranked_ids: list[int],
    *,
    lifecycle_map: dict[int, str],
) -> list[int]:
    """Drop expired jobs from a ranked list, preserving original order.

    ``lifecycle_map`` maps job_id → lifecycle string. Unknown ids are
    treated as ``'unverified'`` (kept) so a missing mapping does not
    silently delete recommendations.
    """
    return [
        jid for jid in ranked_ids
        if lifecycle_map.get(jid, "unverified") in _ALLOWED_LIFECYCLES
    ]
