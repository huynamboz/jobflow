"""Adapter for parsing a CV file into structured fields.

Wires the Employee upload flow to the production CV parser used by the public
matching endpoints (``apps.matching.services.parse_cv_file``). Returns an empty
dict (caller sets ``is_parse_failed=True``) when the parser is unavailable or
fails, so dev environments without the ML deps still run.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Engine seniority enum names → Employee.seniority int (Job.Seniority choices).
_SENIORITY_NAME_TO_INT = {
    "INTERN": 0,
    "JUNIOR": 1,
    "MID": 2,
    "MIDDLE": 2,
    "SENIOR": 3,
    "LEAD": 4,
    "MANAGER": 5,
}


def _seniority_to_int(value: Any) -> int | None:
    """Map the parser's seniority (enum name like ``"MID"`` or an int) to int."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return _SENIORITY_NAME_TO_INT.get(str(value).strip().upper())


def parse_cv_file(file_obj: Any) -> dict:
    """Parse an uploaded CV file. Returns ``{skills, seniority, experience_years}``.

    ``file_obj`` is a Django ``FieldFile``; the production parser takes a local
    filesystem path. Returns an empty dict on any failure.
    """
    try:
        from apps.matching.services import parse_cv_file as _parse_cv_file  # type: ignore

        # FieldFile.path raises for non-local storages — fall back to str().
        path = getattr(file_obj, "path", None) or str(file_obj)
        raw = _parse_cv_file(path)

        out: dict = {}
        skills = raw.get("skills")
        if skills:
            out["skills"] = list(skills)
        seniority = _seniority_to_int(raw.get("seniority"))
        if seniority is not None:
            out["seniority"] = seniority
        if raw.get("experience_years") is not None:
            out["experience_years"] = raw["experience_years"]
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("CV parser unavailable for %s, returning empty: %s", file_obj, exc)
        return {}
