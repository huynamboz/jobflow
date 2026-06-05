"""Adapter for parsing a CV file into full Employee fields.

One LLM call (apps.cvs.services.llm_cv_extractor) yields name, seniority,
experience, role and skills; e-mail / phone are pulled from the raw text by
regex. Returns an empty dict (caller sets ``is_parse_failed=True``) when the
parser/LLM is unavailable or fails, so dev environments without ML deps still
run.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Phone: optional +, then 9–15 digits possibly split by spaces/()/-/.
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")

# Seniority default experience (years) when the CV doesn't state it explicitly.
_SENIORITY_DEFAULT_YEARS: dict[int, float] = {2: 3.5, 3: 6.5, 4: 10.0, 5: 14.0}

_ROLE_LABELS = {
    "backend": "Backend Developer",
    "frontend": "Frontend Developer",
    "fullstack": "Fullstack Developer",
    "mobile": "Mobile Developer",
    "devops": "DevOps Engineer",
    "data_ml": "ML / Data Scientist",
    "data_eng": "Data Engineer",
    "qa": "QA Engineer",
    "design": "Product Designer",
    "ba": "Business Analyst",
}

_normalizer = None


def _seniority_to_int(value: Any) -> int | None:
    """Map a seniority value (int already, or enum name like ``"MID"``) to int."""
    names = {"INTERN": 0, "JUNIOR": 1, "MID": 2, "MIDDLE": 2, "SENIOR": 3, "LEAD": 4, "MANAGER": 5}
    if value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return names.get(str(value).strip().upper())


def _first_email(text: str) -> str:
    m = _EMAIL_RE.search(text or "")
    return m.group(0).strip() if m else ""


def _first_phone(text: str) -> str:
    for m in _PHONE_RE.finditer(text or ""):
        token = m.group(0).strip()
        digits = re.sub(r"\D", "", token)
        # Require a + prefix or 9+ digits so years/GPAs aren't mistaken for phones.
        if (token.startswith("+") and 8 <= len(digits) <= 15) or 9 <= len(digits) <= 15:
            return token
    return ""


def _position_from(work_experience: list[dict], role_category: str) -> str:
    if work_experience:
        title = str(work_experience[0].get("title") or "").strip()
        if title:
            return title[:200]
    return _ROLE_LABELS.get(role_category, "")


def _get_normalizer():
    global _normalizer
    if _normalizer is None:
        from django.conf import settings
        from ml_service.data.skill_normalization import SkillNormalizer

        _normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
    return _normalizer


def _normalize_skills(raw_skills: list[dict]) -> list[str]:
    normalizer = _get_normalizer()
    out: list[str] = []
    seen: set[str] = set()
    for s in raw_skills:
        name = s.get("name") if isinstance(s, dict) else s
        if not name:
            continue
        canonical = normalizer.normalize(str(name))
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    if suffix in (".docx", ".doc"):
        from docx import Document

        return "\n".join(p.text for p in Document(str(path)).paragraphs if p.text.strip())
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {suffix}")


def parse_cv_file(file_obj: Any) -> dict:
    """Parse an uploaded CV into a full Employee field dict.

    Returns ``{full_name, email, phone, position, skills, seniority,
    experience_years}`` (only the fields that were found). Empty dict on failure.
    """
    try:
        from apps.cvs.services.llm_cv_extractor import extract as llm_extract

        path = Path(getattr(file_obj, "path", None) or str(file_obj))
        text = _extract_text(path)
        result = llm_extract(text)

        seniority = result.seniority if result.seniority is not None and result.seniority >= 0 else None
        experience_years = float(result.experience_years or 0)
        if seniority is None:
            from apps.matching.services.llm_cv_parser import _years_to_seniority

            seniority = _years_to_seniority(experience_years)
        if experience_years == 0 and seniority >= 2:
            experience_years = _SENIORITY_DEFAULT_YEARS.get(seniority, 0.0)

        out: dict = {
            "skills": _normalize_skills(result.skills),
            "seniority": seniority,
            "experience_years": experience_years,
        }
        if result.name:
            out["full_name"] = result.name[:200]
        email = _first_email(text)
        if email:
            out["email"] = email
        phone = _first_phone(text)
        if phone:
            out["phone"] = phone[:50]
        position = _position_from(result.work_experience, result.role_category)
        if position:
            out["position"] = position
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("CV parser unavailable for %s, returning empty: %s", file_obj, exc)
        return {}
