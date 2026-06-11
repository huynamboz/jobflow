"""LLM-backed CV parser — same interface as CVParser but uses LLM for field extraction."""

from __future__ import annotations

import logging
from pathlib import Path

from ml_service.graph.schema import CVData, EducationLevel, SeniorityLevel

logger = logging.getLogger(__name__)

_SENIORITY_DEFAULT_YEARS: dict[int, float] = {
    2: 3.5,
    3: 6.5,
    4: 10.0,
    5: 14.0,
}


def _years_to_seniority(years: float) -> int:
    if years < 0.5:
        return 0
    if years < 2:
        return 1
    if years < 5:
        return 2
    if years < 8:
        return 3
    if years < 12:
        return 4
    return 5


class LLMCVParser:
    """Parse CV text/files using LLM extraction instead of rule-based parsing.

    Drop-in replacement for CVParser: same parse_text / parse_file interface,
    returns CVData compatible with InferenceEngine.
    """

    def __init__(self, normalizer) -> None:
        self._normalizer = normalizer

    def parse_file(self, path: str | Path, cv_id: int = 0) -> CVData:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = self._extract_pdf(path)
        elif suffix in (".docx", ".doc"):
            text = self._extract_docx(path)
        elif suffix == ".txt":
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported file type: {suffix}. Use .pdf, .docx, or .txt")
        return self.parse_text(text, cv_id=cv_id)

    def parse_text(self, text: str, cv_id: int = 0) -> CVData:
        from apps.cvs.services.llm_cv_extractor import extract as llm_extract

        result = llm_extract(text)

        seniority_int = result.seniority if result.seniority >= 0 else _years_to_seniority(result.experience_years)

        experience_years = result.experience_years
        if experience_years == 0 and seniority_int >= 2:
            experience_years = _SENIORITY_DEFAULT_YEARS.get(seniority_int, 0.0)

        skills: list[str] = []
        proficiencies: list[int] = []
        seen: set[str] = set()
        for s in result.skills:
            canonical = self._normalizer.normalize(s["name"])
            if canonical and canonical not in seen:
                seen.add(canonical)
                skills.append(canonical)
                proficiencies.append(max(1, min(5, int(s.get("proficiency") or 3))))

        words = text.split()
        embed_text = " ".join(words[:500]) if len(words) > 500 else text

        seniority = SeniorityLevel(seniority_int)
        education = EducationLevel(result.education)

        logger.info(
            "LLM CV parse: %d skills, seniority=%s, exp=%.1fy, edu=%s",
            len(skills), seniority.name, experience_years, education.name,
        )

        # 025: role decided once at parse time from the REAL CV text (title at
        # the top is a legitimate signal there) + skills.
        from ml_service.inference.role_classifier import infer_role

        return CVData(
            cv_id=cv_id,
            seniority=seniority,
            experience_years=experience_years,
            education=education,
            skills=tuple(skills),
            skill_proficiencies=tuple(proficiencies),
            text=embed_text,
            role_category=infer_role(tuple(skills), text),
        )

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        import pdfplumber
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n".join(pages)

    @staticmethod
    def _extract_docx(path: Path) -> str:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
