"""CV service: parse + save to DB."""

from __future__ import annotations

import logging
from pathlib import Path

from django.db import transaction

from apps.cvs.models import CV, CVSkill
from apps.skills.services import SkillService

logger = logging.getLogger(__name__)

# When LLM cannot determine experience_years (returns 0) but seniority is known,
# use these mid-point defaults to avoid a misleading 0 in training data.
_SENIORITY_DEFAULT_YEARS: dict[int, float] = {
    2: 3.5,   # Mid
    3: 6.5,   # Senior
    4: 10.0,  # Lead
    5: 14.0,  # Manager
}


class CVService:
    """Parse CV files and save structured data to DB."""

    def __init__(self):
        from ml_service.cv_parser import CVParser
        from ml_service.data.skill_normalization import SkillNormalizer

        self._normalizer = SkillNormalizer()
        self._parser = CVParser(self._normalizer)
        self._skill_service = SkillService()

    def save_from_upload_with_llm(self, file_path: str, user=None) -> CV:
        """Parse PDF → LLM extract → save to DB. Falls back to rule-based if LLM unavailable."""
        raw_text = self._extract_raw_text(file_path)

        from apps.cvs.services.llm_cv_extractor import extract as llm_extract
        result = llm_extract(raw_text)

        if not result.skills and not result.work_experience:
            logger.info("LLM extraction empty, falling back to rule-based parser")
            return self.save_from_file(file_path, user=user, source="upload")

        # Resolve seniority: prefer LLM-inferred value, fall back to years-based rule
        if result.seniority >= 0:
            seniority = result.seniority
        else:
            seniority = self._years_to_seniority(result.experience_years)

        # Fix: when experience_years=0 and seniority implies real experience, use default
        experience_years = result.experience_years
        if experience_years == 0 and seniority >= 2:
            experience_years = _SENIORITY_DEFAULT_YEARS.get(seniority, 0.0)
            logger.info(
                "Corrected experience_years 0 → %.1f based on seniority=%d",
                experience_years, seniority,
            )

        normalized_skills: list[tuple[str, int]] = []
        for s in result.skills:
            canonical = self._normalizer.normalize(s["name"])
            if canonical:
                proficiency = max(1, min(5, int(s.get("proficiency") or 3)))
                normalized_skills.append((canonical, proficiency))

        with transaction.atomic():
            cv = CV.objects.create(
                user=user,
                file_name=Path(file_path).name,
                raw_text=raw_text,
                parsed_text=raw_text,
                candidate_name=result.name,
                seniority=seniority,
                experience_years=experience_years,
                education=result.education,
                role_category=result.role_category,
                work_experience=result.work_experience,
                source="upload",
            )
            for skill_name, proficiency in normalized_skills:
                skill = self._skill_service.get_or_create(skill_name)
                if skill:
                    CVSkill.objects.get_or_create(
                        cv=cv, skill=skill,
                        defaults={"proficiency": proficiency},
                    )

        logger.info(
            "LLM CV #%d: name=%r exp=%.1f seniority=%d role=%s edu=%d skills=%d",
            cv.id, result.name, experience_years, seniority,
            result.role_category, result.education, len(normalized_skills),
        )
        return cv

    @staticmethod
    def _extract_raw_text(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            import pdfplumber
            pages = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
            return "\n".join(pages)
        if suffix == ".docx":
            import docx
            doc = docx.Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        return Path(file_path).read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _years_to_seniority(years: float) -> int:
        """Canonical seniority mapping — mirrors the rule table in cv_extraction.md."""
        if years < 0.5:
            return 0   # Intern
        if years < 2:
            return 1   # Junior
        if years < 5:
            return 2   # Mid
        if years < 8:
            return 3   # Senior
        if years < 12:
            return 4   # Lead
        return 5       # Manager

    def save_from_extracted(self, data: dict, user=None) -> CV:
        """Save CV from pre-extracted (and user-edited) JSON data."""
        skills_data = data.get("skills") or []

        seniority = int(data.get("seniority", 2))
        experience_years = float(data.get("experience_years", 0))
        if experience_years == 0 and seniority >= 2:
            experience_years = _SENIORITY_DEFAULT_YEARS.get(seniority, 0.0)

        with transaction.atomic():
            cv = CV.objects.create(
                user=user,
                file_name=data.get("file_name", ""),
                raw_text=data.get("raw_text", ""),
                parsed_text=data.get("raw_text", ""),
                candidate_name=data.get("candidate_name", ""),
                seniority=seniority,
                experience_years=experience_years,
                education=int(data.get("education", 2)),
                role_category=data.get("role_category", "other"),
                work_experience=data.get("work_experience") or [],
                source="upload",
            )
            for skill in skills_data:
                canonical = self._normalizer.normalize(skill.get("name", ""))
                if canonical:
                    skill_obj = self._skill_service.get_or_create(canonical)
                    if skill_obj:
                        CVSkill.objects.get_or_create(
                            cv=cv, skill=skill_obj,
                            defaults={"proficiency": max(1, min(5, int(skill.get("proficiency") or 3)))},
                        )
        logger.info("Saved extracted CV #%d: %d skills", cv.id, len(skills_data))
        return cv

    def save_from_file(self, file_path: str, user=None, source: str = "upload") -> CV:
        cv_data = self._parser.parse_file(file_path)
        return self._save_cv(cv_data, file_path=file_path, user=user, source=source)

    def _save_cv(self, cv_data, file_path=None, raw_text=None, user=None, source="upload", source_category="") -> CV:
        with transaction.atomic():
            cv = CV.objects.create(
                user=user,
                file_name=Path(file_path).name if file_path else "",
                raw_text=raw_text or cv_data.text,
                parsed_text=cv_data.text,
                seniority=cv_data.seniority,
                experience_years=cv_data.experience_years,
                education=cv_data.education,
                source=source,
                source_category=source_category,
            )
            for skill_name, proficiency in zip(cv_data.skills, cv_data.skill_proficiencies):
                skill = self._skill_service.get_or_create(skill_name)
                if skill:
                    CVSkill.objects.get_or_create(
                        cv=cv, skill=skill,
                        defaults={"proficiency": proficiency},
                    )
        logger.info("Saved CV #%d: %d skills, seniority=%s", cv.id, len(cv_data.skills), cv_data.seniority.name)
        return cv

    @staticmethod
    def get_all_cv_data() -> list:
        from ml_service.graph.schema import CVData, EducationLevel, SeniorityLevel
        cvs = CV.objects.filter(is_active=True).prefetch_related("cv_skills__skill")
        result = []
        for cv in cvs:
            skills = tuple(cs.skill.canonical_name for cs in cv.cv_skills.all())
            proficiencies = tuple(cs.proficiency for cs in cv.cv_skills.all())
            if len(skills) >= 2:
                result.append(CVData(
                    cv_id=cv.id,
                    seniority=SeniorityLevel(cv.seniority),
                    experience_years=cv.experience_years,
                    education=EducationLevel(cv.education),
                    skills=skills,
                    skill_proficiencies=proficiencies,
                    text=cv.parsed_text or cv.raw_text,
                ))
        return result
