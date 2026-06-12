"""Parse CV from PDF/DOCX/text → CVData.

Section-based parsing with LinkedIn PDF format support:
  1. Detect LinkedIn format (has "Top Skills", "Contact" header)
  2. Extract skills from "Top Skills" section + body text
  3. Parse experience durations from "(N years M months)" patterns
  4. Parse education from Education section specifically
  5. Infer seniority from title line (first few lines)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ml_service.data.skill_normalization import SkillNormalizer
from ml_service.graph.schema import CVData, EducationLevel, SeniorityLevel

logger = logging.getLogger(__name__)

# Single-char skills ("c", "r") require a context pattern to avoid matching
# standalone letters. (Inlined from the removed rule-based SkillExtractor.)
_CONTEXT_REQUIRED: dict[str, re.Pattern] = {
    "c": re.compile(r"\bC(?:\s*[/+]|(?:\s+(?:programming|language|developer|code)))", re.I),
    "r": re.compile(r"\bR(?:\s+(?:programming|language|Studio|developer|statistical))", re.I),
}

_SENIORITY_PATTERNS: list[tuple[re.Pattern, SeniorityLevel]] = [
    (re.compile(r"\b(?:intern|internship|trainee)\b", re.I), SeniorityLevel.INTERN),
    (re.compile(r"\b(?:junior|jr\.?|entry.?level|graduate)\b", re.I), SeniorityLevel.JUNIOR),
    (re.compile(r"\b(?:senior|sr\.?)\b", re.I), SeniorityLevel.SENIOR),
    (re.compile(r"\b(?:lead|tech.?lead|principal|staff)\b", re.I), SeniorityLevel.LEAD),
    (re.compile(r"\b(?:engineering manager|project manager|product manager|director|head of|vp)\b", re.I), SeniorityLevel.MANAGER),
]

_EDUCATION_PATTERNS: list[tuple[re.Pattern, EducationLevel]] = [
    (re.compile(r"\b(?:ph\.?d|doctorate)\b", re.I), EducationLevel.PHD),
    (re.compile(r"\b(?:master(?:'?s)?\s+(?:degree|of)|mba|m\.s\.|m\.tech|msc)\b", re.I), EducationLevel.MASTER),
    (re.compile(r"\b(?:bachelor(?:'?s)?\s+(?:degree|of)|b\.s\.|b\.tech|bsc|b\.e\.?)\b", re.I), EducationLevel.BACHELOR),
    (re.compile(r"\b(?:diploma|associate|college)\b", re.I), EducationLevel.COLLEGE),
]

_YEARS_PATTERN = re.compile(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)?", re.I)

# LinkedIn duration pattern: "(2 years 6 months)" or "(1 year)" or "(6 months)"
_LINKEDIN_DURATION = re.compile(
    r"\((\d+)\s+years?\s*(?:(\d+)\s+months?)?\)|"
    r"\((\d+)\s+months?\)",
    re.I,
)

# Section header patterns (common CV section names)
_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "skills": re.compile(r"^(?:SKILLS?|TECHNICAL\s+SKILLS?|CORE\s+COMPETENC|TECHNOLOGIES|TECH\s+STACK|TOP\s+SKILLS)", re.I | re.M),
    "experience": re.compile(r"^(?:WORK\s+EXPERIENCE|EXPERIENCE|EMPLOYMENT|PROFESSIONAL\s+EXPERIENCE)", re.I | re.M),
    "projects": re.compile(r"^(?:PROJECTS?|PERSONAL\s+PROJECTS?|SIDE\s+PROJECTS?)", re.I | re.M),
    "education": re.compile(r"^(?:EDUCATION|ACADEMIC|QUALIFICATIONS)", re.I | re.M),
    "summary": re.compile(r"^(?:SUMMARY|OBJECTIVE|ABOUT|PROFILE)", re.I | re.M),
}

# Skills that should be excluded when found only in project/experience context
_CONTEXT_ONLY_SKILLS = {
    "security", "problem_solving", "communication", "teamwork",
    "leadership", "time_management", "agile",
}


class CVParser:
    """Parse CV files (PDF/DOCX/text) into CVData with section-based skill extraction."""

    def __init__(self, normalizer: SkillNormalizer) -> None:
        self._normalizer = normalizer

    def parse_file(self, path: str | Path, cv_id: int = 0) -> CVData:
        """Parse a CV file (PDF or DOCX) into CVData."""
        path = Path(path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            text = self._extract_pdf(path)
        elif suffix in (".docx", ".doc"):
            text = self._extract_docx(path)
        elif suffix == ".txt":
            text = path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file type: {suffix}. Use .pdf, .docx, or .txt")

        return self.parse_text(text, cv_id=cv_id)

    def parse_text(self, text: str, cv_id: int = 0) -> CVData:
        """Parse raw CV text into CVData using section-based extraction."""
        sections = self._split_sections(text)
        skills = self._extract_skills_sectioned(sections, text)
        seniority = self._infer_seniority(text)
        experience_years = self._infer_experience_years(text)
        education = self._infer_education(text, sections)

        proficiencies = tuple(3 for _ in skills)

        # Build embedding text: summary + experience + skills (skip volunteer/other)
        embed_parts = []
        for key in ("summary", "experience", "skills", "projects"):
            if sections.get(key):
                embed_parts.append(sections[key])
        embed_text = " ".join(embed_parts) if embed_parts else text
        words = embed_text.split()
        if len(words) > 500:
            embed_text = " ".join(words[:500])

        logger.info(
            "Parsed CV: %d skills, seniority=%s, exp=%.1fy, edu=%s",
            len(skills), seniority.name, experience_years, education.name,
        )

        return CVData(
            cv_id=cv_id,
            seniority=seniority,
            experience_years=experience_years,
            education=education,
            skills=tuple(skills),
            skill_proficiencies=proficiencies,
            text=embed_text,
        )

    # ------------------------------------------------------------------
    # Section splitting
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        """Split CV text into named sections.

        Returns dict like {"skills": "...", "experience": "...", "projects": "..."}.
        Unmatched text goes into "other".
        """
        # Find all section boundaries
        boundaries: list[tuple[int, str]] = []
        for section_name, pattern in _SECTION_PATTERNS.items():
            for match in pattern.finditer(text):
                boundaries.append((match.start(), section_name))

        if not boundaries:
            return {"other": text}

        boundaries.sort(key=lambda x: x[0])

        sections: dict[str, str] = {}
        # Text before first section → "header"
        if boundaries[0][0] > 0:
            sections["header"] = text[: boundaries[0][0]].strip()

        for i, (start, name) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            section_text = text[start:end].strip()
            # Remove the header line itself
            lines = section_text.split("\n", 1)
            sections[name] = lines[1].strip() if len(lines) > 1 else ""

        return sections

    # ------------------------------------------------------------------
    # Section-based skill extraction
    # ------------------------------------------------------------------

    def _extract_skills_sectioned(
        self, sections: dict[str, str], full_text: str,
    ) -> list[str]:
        """Extract skills from full text, filtering vague skills from non-skill sections.

        Strategy: always scan full text (robust for PDF), but remove
        context-only skills (security, problem_solving, etc.) unless
        they explicitly appear in the SKILLS section.
        """
        # Step 1: Scan full text for all skills
        all_skills = self._scan_text(full_text)

        # Step 2: Find which skills are explicitly in the SKILLS section
        skill_section = sections.get("skills", "")
        trusted_skills = set(self._scan_text(skill_section)) if skill_section else set()

        # Step 3: Filter — keep context-only skills ONLY if in SKILLS section
        result: list[str] = []
        for skill in all_skills:
            if skill in _CONTEXT_ONLY_SKILLS and skill not in trusted_skills:
                continue  # vague skill only in experience/project text → skip
            result.append(skill)

        return result

    def _scan_text(self, text: str) -> list[str]:
        """Extract canonical skills from text using n-gram matching."""
        if not text:
            return []

        seen: set[str] = set()
        result: list[str] = []

        words = [w.rstrip(".,;:") for w in re.findall(r"[\w#+.]+", text)]
        candidates: list[str] = [w for w in words if len(w) > 1]

        for n in (2, 3):
            for i in range(len(words) - n + 1):
                candidates.append(" ".join(words[i: i + n]))

        for candidate in candidates:
            canonical = self._normalizer.normalize(candidate)
            if canonical and canonical not in seen:
                seen.add(canonical)
                result.append(canonical)

        # Context-required skills (c, r)
        for canonical, pattern in _CONTEXT_REQUIRED.items():
            if canonical not in seen and pattern.search(text):
                seen.add(canonical)
                result.append(canonical)

        return result

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_seniority(text: str) -> SeniorityLevel:
        """Infer seniority from the title area of the CV.

        For LinkedIn PDFs, the job title appears in the first few lines.
        We scan only the first 500 chars (header/title area) to avoid
        matching "internship" in experience body text.
        """
        # Use only the title area (first ~500 chars) to avoid body text matches
        title_area = text[:500]

        for pattern, level in _SENIORITY_PATTERNS:
            if pattern.search(title_area):
                return level
        return SeniorityLevel.MID

    @staticmethod
    def _infer_experience_years(text: str) -> float:
        """Infer total experience years.

        Handles two patterns:
        1. Explicit: "5 years of experience", "3+ yrs experience"
        2. LinkedIn durations: "(2 years 6 months)", "(1 year)", "(6 months)"
           → sum all durations to get total experience
        """
        # Method 1: Explicit "N years experience" statements
        explicit_matches = _YEARS_PATTERN.findall(text)
        explicit_max = float(max(int(m) for m in explicit_matches)) if explicit_matches else 0.0

        # Method 2: Sum LinkedIn duration patterns "(N years M months)"
        total_months = 0.0
        for match in _LINKEDIN_DURATION.finditer(text):
            years_str, months_str, only_months_str = match.groups()
            if years_str:
                total_months += int(years_str) * 12
                if months_str:
                    total_months += int(months_str)
            elif only_months_str:
                total_months += int(only_months_str)

        linkedin_years = total_months / 12.0

        # Return the larger of the two methods
        result = max(explicit_max, linkedin_years)
        return round(result, 1)

    @staticmethod
    def _infer_education(text: str, sections: dict[str, str] | None = None) -> EducationLevel:
        """Infer education level.

        For LinkedIn PDFs, only search the Education section to avoid
        false positives (e.g. "Master CopyCat Nuke" matching "master").
        Falls back to full text if no Education section found.
        """
        # Prefer Education section to avoid false positives
        edu_text = ""
        if sections and sections.get("education"):
            edu_text = sections["education"]

        # If we have an education section, search it specifically
        if edu_text:
            for pattern, level in _EDUCATION_PATTERNS:
                if pattern.search(edu_text):
                    return level
            # LinkedIn format: "Master's degree", "Bachelor's degree", "Engineer's degree"
            if re.search(r"\bmaster'?s?\s+degree\b", edu_text, re.I):
                return EducationLevel.MASTER
            if re.search(r"\b(?:bachelor'?s?\s+degree|engineer'?s?\s+degree|bachelor\s+of|engineer\s+of)\b", edu_text, re.I):
                return EducationLevel.BACHELOR
            # If Education section mentions a University/Institute → assume BACHELOR
            if re.search(r"\b(?:university|institute|college of technology|polytechnic)\b", edu_text, re.I):
                return EducationLevel.BACHELOR
            # If education section exists but no degree/university found → COLLEGE
            return EducationLevel.COLLEGE

        # Fallback: scan full text (non-LinkedIn CVs)
        for pattern, level in _EDUCATION_PATTERNS:
            if pattern.search(text):
                return level
        return EducationLevel.BACHELOR

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts)

    @staticmethod
    def _extract_docx(path: Path) -> str:
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
