"""Load real CV data from HuggingFace datasets.

Supports two datasets:
  - datasetmaster/resumes: 4.817 IT resumes, structured JSON (skills, experience, education)
  - Suriyaganesh/54k-resume: 54.933 resumes, relational CSV (6 tables)

Both are MIT license, IT-heavy, English.

Skills are extracted from BOTH structured fields AND full text (summary,
responsibilities, technical_environment, projects) to maximize coverage.
"""

from __future__ import annotations

import logging
import re

from ml_benchmark.data.skill_normalization import SkillNormalizer
from ml_benchmark.graph.schema import CVData, EducationLevel, SeniorityLevel

logger = logging.getLogger(__name__)

# Map dataset level strings to SeniorityLevel
_LEVEL_MAP: dict[str, SeniorityLevel] = {
    "intern": SeniorityLevel.INTERN,
    "entry": SeniorityLevel.JUNIOR,
    "entry-level": SeniorityLevel.JUNIOR,
    "junior": SeniorityLevel.JUNIOR,
    "mid": SeniorityLevel.MID,
    "mid-level": SeniorityLevel.MID,
    "mid-senior": SeniorityLevel.SENIOR,
    "senior": SeniorityLevel.SENIOR,
    "manager": SeniorityLevel.MANAGER,
    "professional": SeniorityLevel.MID,
}

# Map dataset degree strings to EducationLevel
_DEGREE_MAP: dict[str, EducationLevel] = {
    "bachelor": EducationLevel.BACHELOR,
    "bachelors": EducationLevel.BACHELOR,
    "be": EducationLevel.BACHELOR,
    "btech": EducationLevel.BACHELOR,
    "b.tech": EducationLevel.BACHELOR,
    "bsc": EducationLevel.BACHELOR,
    "b.sc": EducationLevel.BACHELOR,
    "bca": EducationLevel.BACHELOR,
    "bs": EducationLevel.BACHELOR,
    "master": EducationLevel.MASTER,
    "masters": EducationLevel.MASTER,
    "mtech": EducationLevel.MASTER,
    "m.tech": EducationLevel.MASTER,
    "msc": EducationLevel.MASTER,
    "m.sc": EducationLevel.MASTER,
    "me": EducationLevel.MASTER,
    "mba": EducationLevel.MASTER,
    "ms": EducationLevel.MASTER,
    "phd": EducationLevel.PHD,
    "doctorate": EducationLevel.PHD,
    "diploma": EducationLevel.COLLEGE,
    "associate": EducationLevel.COLLEGE,
    "college": EducationLevel.COLLEGE,
}


def load_kaggle_resumes(
    normalizer: SkillNormalizer,
    max_resumes: int | None = None,
) -> list[CVData]:
    """Load IT resumes from HuggingFace and convert to CVData.

    Downloads datasetmaster/resumes (4.817 IT resumes, MIT license).
    Extracts skills via normalizer, infers seniority and education.
    """
    from datasets import load_dataset

    logger.info("Loading datasetmaster/resumes from HuggingFace...")
    ds = load_dataset("datasetmaster/resumes", split="train")
    logger.info("Loaded %d raw resumes", len(ds))

    cvs: list[CVData] = []
    skipped = 0

    for i, row in enumerate(ds):
        if max_resumes and len(cvs) >= max_resumes:
            break

        cv = _parse_resume(row, cv_id=len(cvs), normalizer=normalizer)
        if cv and len(cv.skills) >= 2:
            cvs.append(cv)
        else:
            skipped += 1

    logger.info(
        "Parsed %d CVs (skipped %d with < 2 skills)",
        len(cvs),
        skipped,
    )
    return cvs


def _parse_resume(row: dict, cv_id: int, normalizer: SkillNormalizer) -> CVData | None:
    """Convert a single HuggingFace dataset row to CVData.

    Skills are extracted from TWO sources:
    1. Structured skill fields (programming_languages, frameworks, etc.)
    2. Full text scan (summary, responsibilities, technical_environment, projects)
    This ensures skills mentioned in text but not in structured fields are captured.
    """
    # --- Extract skills from structured fields ---
    raw_skills = _extract_raw_skills(row.get("skills"))
    canonical_skills: list[str] = []
    seen: set[str] = set()
    for raw in raw_skills:
        canonical = normalizer.normalize(raw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            canonical_skills.append(canonical)

    # --- Enrich: extract additional skills from full text ---
    full_text = _collect_all_text(row)
    text_skills = _extract_skills_from_text(full_text, normalizer)
    for skill in text_skills:
        if skill not in seen:
            seen.add(skill)
            canonical_skills.append(skill)

    if not canonical_skills:
        return None

    # --- Infer seniority ---
    seniority = _infer_seniority(row.get("experience"))

    # --- Infer experience years ---
    experience_years = _infer_experience_years(row.get("experience"))

    # --- Infer education ---
    education = _infer_education(row.get("education"))

    # --- Build text ---
    text = _build_text(row, canonical_skills)

    # Default proficiency = 3 for all skills (dataset has level but inconsistent)
    proficiencies = tuple(3 for _ in canonical_skills)

    return CVData(
        cv_id=cv_id,
        seniority=seniority,
        experience_years=experience_years,
        education=education,
        skills=tuple(canonical_skills),
        skill_proficiencies=proficiencies,
        text=text,
    )


def _collect_all_text(row: dict) -> str:
    """Collect ALL text from a resume row for skill extraction.

    Scans: summary, experience titles + responsibilities + technical_environment,
    projects descriptions, certifications, internships.
    """
    parts: list[str] = []

    # Summary
    personal = row.get("personal_info")
    if isinstance(personal, dict):
        summary = personal.get("summary", "")
        if summary and summary != "Unknown":
            parts.append(summary)

    # Experience: titles + responsibilities + technical environment
    for exp in (row.get("experience") or []):
        if not isinstance(exp, dict):
            continue
        title = exp.get("title", "")
        if title and title != "Unknown":
            parts.append(title)
        for resp in (exp.get("responsibilities") or []):
            if resp and resp != "Unknown":
                parts.append(resp)
        tech_env = exp.get("technical_environment", {})
        if isinstance(tech_env, dict):
            for key in ("technologies", "methodologies", "tools"):
                items = tech_env.get(key, [])
                if items:
                    parts.append(" ".join(str(t) for t in items))

    # Projects
    for proj in (row.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        desc = proj.get("description", "")
        if desc and desc != "Unknown":
            parts.append(desc)
        techs = proj.get("technologies", [])
        if techs:
            parts.append(" ".join(str(t) for t in techs))

    # Certifications
    for cert in (row.get("certifications") or []):
        if isinstance(cert, dict):
            name = cert.get("name", "")
            if name and name != "Unknown":
                parts.append(name)
        elif isinstance(cert, str) and cert != "Unknown":
            parts.append(cert)

    return " ".join(parts)


def _extract_skills_from_text(text: str, normalizer: SkillNormalizer) -> list[str]:
    """Extract canonical skills from free text using n-gram matching.

    Same strategy as SkillExtractor._extract_skills but for CV text.
    Skips single-char tokens to avoid false positives.
    """
    if not text:
        return []

    seen: set[str] = set()
    result: list[str] = []

    words = [w.rstrip(".,;:") for w in re.findall(r"[\w#+.]+", text)]
    candidates: list[str] = [w for w in words if len(w) > 1]

    # Bigrams and trigrams
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            candidates.append(" ".join(words[i: i + n]))

    for candidate in candidates:
        canonical = normalizer.normalize(candidate)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)

    return result


def _extract_raw_skills(skills_obj) -> list[str]:
    """Pull all skill names from the nested skills structure."""
    if not skills_obj:
        return []

    result: list[str] = []
    tech = skills_obj.get("technical") if isinstance(skills_obj, dict) else None
    if not tech:
        return result

    for key in ["programming_languages", "frameworks", "databases", "tools", "platforms"]:
        items = tech.get(key, [])
        if not items:
            continue
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                result.append(item["name"])
            elif isinstance(item, str):
                result.append(item)

    # Also check soft skills
    soft = skills_obj.get("soft_skills", [])
    if soft:
        for item in soft:
            if isinstance(item, str):
                result.append(item)

    return result


def _infer_seniority(experience) -> SeniorityLevel:
    """Infer seniority from experience entries."""
    if not experience:
        return SeniorityLevel.JUNIOR

    for exp in experience:
        if not isinstance(exp, dict):
            continue
        level = (exp.get("level") or "").lower().strip()
        if level in _LEVEL_MAP:
            return _LEVEL_MAP[level]

    return SeniorityLevel.MID


def _infer_experience_years(experience) -> float:
    """Estimate total experience years from duration strings."""
    if not experience:
        return 0.0

    total_months = 0.0
    for exp in experience:
        if not isinstance(exp, dict):
            continue
        dates = exp.get("dates", {})
        if not isinstance(dates, dict):
            continue
        duration = (dates.get("duration") or "").lower()
        total_months += _parse_duration(duration)

    return round(total_months / 12.0, 1)


def _parse_duration(duration: str) -> float:
    """Parse '2 years 3 months' or '6 months' into total months."""
    months = 0.0
    year_match = re.search(r"(\d+)\s*year", duration)
    month_match = re.search(r"(\d+)\s*month", duration)
    if year_match:
        months += int(year_match.group(1)) * 12
    if month_match:
        months += int(month_match.group(1))
    return months


def _infer_education(education) -> EducationLevel:
    """Infer education level from education entries."""
    if not education:
        return EducationLevel.BACHELOR

    best = EducationLevel.NONE
    for edu in education:
        if not isinstance(edu, dict):
            continue
        degree = edu.get("degree", {})
        if not isinstance(degree, dict):
            continue
        level_str = (degree.get("level") or "").lower().strip()
        for key, val in _DEGREE_MAP.items():
            if key in level_str:
                if val > best:
                    best = val
                break

    return best if best != EducationLevel.NONE else EducationLevel.BACHELOR


def _build_text(row: dict, skills: list[str]) -> str:
    """Build rich embedding text from resume fields.

    Includes summary, all experience titles + responsibilities, projects,
    and skills. Truncated to ~500 words to stay within embedding model limits.
    """
    parts: list[str] = []

    # Summary
    personal = row.get("personal_info")
    if isinstance(personal, dict):
        summary = personal.get("summary", "")
        if summary and summary != "Unknown":
            parts.append(summary)

    # Experience titles + ALL responsibilities (not just first)
    for exp in (row.get("experience") or []):
        if not isinstance(exp, dict):
            continue
        title = exp.get("title", "")
        if title and title != "Unknown":
            parts.append(title)
        for resp in (exp.get("responsibilities") or []):
            if resp and resp != "Unknown":
                parts.append(resp)
        # Technical environment
        tech_env = exp.get("technical_environment", {})
        if isinstance(tech_env, dict):
            techs = tech_env.get("technologies", [])
            if techs:
                parts.append("Technologies: " + ", ".join(str(t) for t in techs[:10]))

    # Projects
    for proj in (row.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        name = proj.get("name", "")
        desc = proj.get("description", "")
        if name and name != "Unknown":
            parts.append(f"Project: {name}")
        if desc and desc != "Unknown":
            parts.append(desc)

    # Skills
    if skills:
        parts.append("Skills: " + ", ".join(skills))

    text = ". ".join(parts) if parts else "Software developer"
    # Truncate to ~500 words (embedding model limit)
    words = text.split()
    if len(words) > 500:
        text = " ".join(words[:500])
    return text


# =========================================================================
# Dataset #2: Suriyaganesh/54k-resume (54.933 resumes, relational CSV)
# =========================================================================

# IT-related title keywords for filtering
_IT_TITLE_KEYWORDS = {
    "developer", "engineer", "programmer", "architect", "devops",
    "administrator", "analyst", "consultant", "specialist",
    "java", "python", "frontend", "front end", "front-end",
    "backend", "back end", "back-end", "full stack", "fullstack",
    "web", "software", "data", "database", "cloud", "network",
    "security", "system", "systems", "ui", "ux", "mobile",
    "android", "ios", "qa", "test", "automation", "machine learning",
    "ml", "ai", "bi", "etl", "scrum", "agile", "it ",
}


def load_54k_resumes(
    normalizer: SkillNormalizer,
    max_resumes: int | None = None,
) -> list[CVData]:
    """Load IT resumes from Suriyaganesh/54k-resume (HuggingFace).

    54.933 resumes in 6 relational CSV tables. Filters to IT titles only.
    https://huggingface.co/datasets/Suriyaganesh/54k-resume
    """
    from datasets import load_dataset

    logger.info("Loading Suriyaganesh/54k-resume from HuggingFace (6 tables)...")

    people = load_dataset("Suriyaganesh/54k-resume", data_files="01_people.csv", split="train")
    experience = load_dataset("Suriyaganesh/54k-resume", data_files="04_experience.csv", split="train")
    person_skills = load_dataset("Suriyaganesh/54k-resume", data_files="05_person_skills.csv", split="train")
    education = load_dataset("Suriyaganesh/54k-resume", data_files="03_education.csv", split="train")

    logger.info(
        "Loaded: %d people, %d experience rows, %d person_skills, %d education",
        len(people), len(experience), len(person_skills), len(education),
    )

    # Build lookup maps
    # person_id → list of titles
    exp_by_person: dict[int, list[str]] = {}
    for row in experience:
        pid = row.get("person_id")
        title = (row.get("title") or "").strip()
        if pid and title:
            exp_by_person.setdefault(pid, []).append(title)

    # person_id → list of raw skills
    skills_by_person: dict[int, list[str]] = {}
    for row in person_skills:
        pid = row.get("person_id")
        skill = (row.get("skill") or "").strip()
        if pid and skill:
            skills_by_person.setdefault(pid, []).append(skill)

    # person_id → education programs
    edu_by_person: dict[int, list[str]] = {}
    for row in education:
        pid = row.get("person_id")
        prog = (row.get("program") or "").strip()
        if pid and prog:
            edu_by_person.setdefault(pid, []).append(prog)

    # Filter to IT people
    cvs: list[CVData] = []
    skipped_no_it = 0
    skipped_no_skills = 0

    for row in people:
        if max_resumes and len(cvs) >= max_resumes:
            break

        pid = row.get("person_id")
        if not pid:
            continue

        titles = exp_by_person.get(pid, [])
        if not _is_it_person(titles):
            skipped_no_it += 1
            continue

        raw_skills = skills_by_person.get(pid, [])
        canonical_skills = _normalize_skills_list(raw_skills, normalizer)

        # Enrich: also extract skills from titles (often contain tech names)
        title_text = " ".join(titles)
        title_skills = _extract_skills_from_text(title_text, normalizer)
        seen = set(canonical_skills)
        for sk in title_skills:
            if sk not in seen:
                seen.add(sk)
                canonical_skills.append(sk)

        if len(canonical_skills) < 2:
            skipped_no_skills += 1
            continue

        seniority = _infer_seniority_from_titles(titles)
        education_level = _infer_education_from_programs(edu_by_person.get(pid, []))
        experience_years = _estimate_years_from_title_count(len(titles))

        title_str = titles[0] if titles else "Software Developer"
        skills_str = ", ".join(canonical_skills)
        text = f"{title_str}. Skills: {skills_str}."

        proficiencies = tuple(3 for _ in canonical_skills)

        cvs.append(CVData(
            cv_id=len(cvs),
            seniority=seniority,
            experience_years=experience_years,
            education=education_level,
            skills=tuple(canonical_skills),
            skill_proficiencies=proficiencies,
            text=text,
        ))

    logger.info(
        "Parsed %d IT CVs (skipped: %d non-IT, %d no skills)",
        len(cvs), skipped_no_it, skipped_no_skills,
    )
    return cvs


def _is_it_person(titles: list[str]) -> bool:
    """Check if any title contains IT-related keywords."""
    for title in titles:
        lower = title.lower()
        for kw in _IT_TITLE_KEYWORDS:
            if kw in lower:
                return True
    return False


def _normalize_skills_list(raw_skills: list[str], normalizer: SkillNormalizer) -> list[str]:
    """Normalize a list of raw skill strings to canonical names."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_skills:
        canonical = normalizer.normalize(raw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def _infer_seniority_from_titles(titles: list[str]) -> SeniorityLevel:
    """Infer seniority from job title prefixes."""
    for title in titles:
        lower = title.lower()
        if any(k in lower for k in ("sr.", "sr ", "senior", "lead", "principal", "staff")):
            return SeniorityLevel.SENIOR
        if any(k in lower for k in ("manager", "director", "head", "vp")):
            return SeniorityLevel.MANAGER
        if any(k in lower for k in ("jr.", "jr ", "junior", "intern", "entry")):
            return SeniorityLevel.JUNIOR
    return SeniorityLevel.MID


def _infer_education_from_programs(programs: list[str]) -> EducationLevel:
    """Infer education level from program/degree strings."""
    best = EducationLevel.BACHELOR
    for prog in programs:
        lower = prog.lower()
        if any(k in lower for k in ("phd", "doctorate", "ph.d")):
            return EducationLevel.PHD
        if any(k in lower for k in ("master", "mba", "m.s.", "m.tech", "msc")):
            best = max(best, EducationLevel.MASTER)
    return best


def _estimate_years_from_title_count(num_positions: int) -> float:
    """Rough estimate: ~2 years per position."""
    return round(min(num_positions * 2.0, 20.0), 1)


# =========================================================================
# Unified loader
# =========================================================================


def load_resumes(
    normalizer: SkillNormalizer,
    source: str = "datasetmaster",
    max_resumes: int | None = None,
) -> list[CVData]:
    """Load resumes from specified source.

    Args:
        source: "datasetmaster" (4.8K, structured) or "54k" (54K, relational)
    """
    if source == "datasetmaster":
        return load_kaggle_resumes(normalizer, max_resumes=max_resumes)
    elif source == "54k":
        return load_54k_resumes(normalizer, max_resumes=max_resumes)
    else:
        raise ValueError(f"Unknown resume source: {source}. Use 'datasetmaster' or '54k'.")
