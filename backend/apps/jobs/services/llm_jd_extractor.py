"""LLM-based JD (Job Description) field extractor."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "jd_extraction.md"

VALID_JOB_TYPES = {"full-time", "part-time", "contract", "remote", "hybrid", "on-site"}
VALID_SALARY_TYPES = {"hourly", "monthly", "annual", "unknown"}
VALID_ROLE_CATEGORIES = {
    "backend", "frontend", "fullstack", "mobile", "devops",
    "data_ml", "data_eng", "qa", "design", "ba", "other",
}

# JSON schema for native structured output (response_format / forced tool-use).
# The provider returns valid JSON matching this — no more "non-JSON response".
_JD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "location": {"type": "string"},
        "is_remote": {"type": "boolean"},
        "seniority": {"type": ["integer", "null"]},
        "role_category": {"type": "string", "enum": sorted(VALID_ROLE_CATEGORIES)},
        "job_type": {"type": "string"},
        "salary_min": {"type": "number"},
        "salary_max": {"type": "number"},
        "salary_currency": {"type": "string"},
        "salary_type": {"type": "string"},
        "experience_min": {"type": "number"},
        "experience_max": {"type": ["number", "null"]},
        "degree_requirement": {"type": "integer"},
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "importance": {"type": "integer"}},
                "required": ["name", "importance"],
            },
        },
    },
    "required": ["seniority", "role_category", "skills"],
}

# Default experience_years when seniority is known but years = 0
SENIORITY_DEFAULT_YEARS = {2: 3.5, 3: 6.5, 4: 10.0, 5: 14.0}


@dataclass
class JDExtractResult:
    title: str = ""
    company: str = ""
    location: str = ""
    is_remote: bool = False
    seniority: int = 2
    role_category: str = "other"
    job_type: str = "full-time"
    salary_min: int = 0
    salary_max: int = 0
    salary_currency: str = "USD"
    salary_type: str = "unknown"
    salary_usd_annual_min: int = 0
    salary_usd_annual_max: int = 0
    experience_min: float = 0.0
    experience_max: Optional[float] = None
    degree_requirement: int = 0
    skills: list[dict] = field(default_factory=list)  # [{"name": str, "importance": int}]


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _strip_code_fence(text: str) -> str:
    # Strip <think>…</think> blocks emitted by reasoning models
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val or default)
    except (TypeError, ValueError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val or default)
    except (TypeError, ValueError):
        return default

def _years_to_seniority(years: float) -> int:
    """Map minimum experience years → seniority level (mirrors the prompt scale)."""
    if years < 0.5: return 0
    if years < 2:   return 1
    if years < 5:   return 2
    if years < 8:   return 3
    if years < 12:  return 4
    return 5



def extract(raw_text: str) -> JDExtractResult:
    """Call LLM to extract structured fields from raw job description text."""
    from apps.llm.service import LLMService
    from apps.jobs.services.salary_normalizer import normalize_salary_range

    system_prompt = _load_system_prompt()

    try:
        response = LLMService.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.0,
            max_tokens=8192,
            feature="jd_extraction",
            json_schema=_JD_SCHEMA,
        )
    except Exception as exc:
        logger.warning("LLM call failed during JD extraction: %s", exc)
        raise

    cleaned = _strip_code_fence(response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON response: %.200s", response)
        return JDExtractResult()

    # 023/3.3 (A12): "unknown" is now distinguishable — the prompt returns null
    # when the posting gives no signal. Infer from experience_min before falling
    # back to MID (the old blanket default put 46% of the catalog at MID).
    seniority_raw = data.get("seniority")
    experience_min_early = _safe_float(data.get("experience_min"), 0.0)
    if seniority_raw is None:
        if experience_min_early > 0:
            seniority = _years_to_seniority(experience_min_early)
        else:
            seniority = 2  # last-resort default, now rare
            logger.info("seniority unknown (no signal) — defaulted MID: %.80s",
                        str(data.get("title") or ""))
    else:
        seniority = max(0, min(5, _safe_int(seniority_raw, 2)))
    degree_requirement = max(0, min(5, _safe_int(data.get("degree_requirement"), 0)))

    salary_min = _safe_int(data.get("salary_min"), 0)
    salary_max = _safe_int(data.get("salary_max"), 0)
    salary_currency = str(data.get("salary_currency") or "USD").upper()

    salary_type = str(data.get("salary_type") or "").lower()
    if salary_type not in VALID_SALARY_TYPES:
        salary_type = "monthly" if salary_min > 0 else "unknown"

    job_type = str(data.get("job_type") or "full-time").lower()
    if job_type not in VALID_JOB_TYPES:
        job_type = "full-time"

    role_category = str(data.get("role_category") or "other").lower()
    if role_category not in VALID_ROLE_CATEGORIES:
        role_category = "other"

    is_remote = bool(data.get("is_remote", False))
    # Also set is_remote if job_type is explicitly remote
    if job_type == "remote":
        is_remote = True

    experience_min = _safe_float(data.get("experience_min"), 0.0)
    # 023/3.3 (A13): cross-check — seniority contradicting stated experience by
    # 2+ levels is an extraction smell worth surfacing.
    if experience_min > 0:
        implied = _years_to_seniority(experience_min)
        if abs(seniority - implied) >= 2:
            logger.warning(
                "seniority/experience mismatch: seniority=%d but experience_min=%.1fy "
                "(implies %d) — title: %.80s",
                seniority, experience_min, implied, str(data.get("title") or ""))
    exp_max_raw = data.get("experience_max")
    experience_max = _safe_float(exp_max_raw) if exp_max_raw is not None else None

    # Skills: LLM should already return canonical names; log anything unexpected
    skills = []
    for s in (data.get("skills") or []):
        if isinstance(s, dict) and s.get("name"):
            skills.append({
                "name": str(s["name"]).strip().lower(),
                "importance": max(1, min(5, _safe_int(s.get("importance"), 3))),
            })

    # Normalize salary to USD annual
    usd_annual_min, usd_annual_max = normalize_salary_range(
        salary_min, salary_max, salary_currency, salary_type
    )

    return JDExtractResult(
        title=str(data.get("title") or "").strip(),
        company=str(data.get("company") or "").strip(),
        location=str(data.get("location") or "").strip(),
        is_remote=is_remote,
        seniority=seniority,
        role_category=role_category,
        job_type=job_type,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_type=salary_type,
        salary_usd_annual_min=usd_annual_min,
        salary_usd_annual_max=usd_annual_max,
        experience_min=experience_min,
        experience_max=experience_max,
        degree_requirement=degree_requirement,
        skills=skills,
    )
