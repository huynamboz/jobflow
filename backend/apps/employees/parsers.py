"""Adapter for parsing a CV file into structured fields.

Wraps whatever the production CV pipeline exposes — currently we look for a
public callable in apps.cvs first, falling back to a no-op stub so dev
environments without the ML deps can still run.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_cv_file(file_obj: Any) -> dict:
    """Parse an uploaded CV file. Returns {skills, seniority, experience_years}.

    Returns an empty dict (caller should set ``is_parse_failed=True``) if the
    parser is unavailable or fails.
    """
    try:
        # Preferred public adapter — wire if/when apps.cvs exposes one.
        from apps.cvs.services import parse_cv  # type: ignore

        return parse_cv(file_obj)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CV parser unavailable, returning empty: %s", exc)
        return {}
