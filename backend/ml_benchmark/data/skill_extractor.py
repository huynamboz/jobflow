"""Extract structured fields from RawJob into JobData for the graph pipeline.

Uses SkillNormalizer to find canonical skills in job description text.
Infers seniority from title/description heuristics.
Computes TF-IDF skill importance when a corpus is provided.
"""

from __future__ import annotations

import math
import re

from ml_benchmark.crawler.base import RawJob
from ml_benchmark.data.skill_normalization import SkillNormalizer
from ml_benchmark.graph.schema import JobData, SeniorityLevel

# ---------------------------------------------------------------------------
# Seniority inference rules (applied to lowercased title + description)
# ---------------------------------------------------------------------------
_SENIORITY_PATTERNS: list[tuple[re.Pattern, SeniorityLevel]] = [
    (re.compile(r"\b(?:intern|internship|trainee)\b", re.I), SeniorityLevel.INTERN),
    (re.compile(r"\b(?:junior|jr\.?|entry.?level|associate|graduate)\b", re.I), SeniorityLevel.JUNIOR),
    (re.compile(r"\b(?:senior|sr\.?)\b", re.I), SeniorityLevel.SENIOR),
    (re.compile(r"\b(?:lead|tech.?lead|principal|staff)\b", re.I), SeniorityLevel.LEAD),
    (re.compile(r"\b(?:manager|director|head of|vp)\b", re.I), SeniorityLevel.MANAGER),
    # mid is the fallback — no explicit pattern
]

# Monthly salary normalization constant
_SALARY_NORM_ANNUAL_TO_MONTHLY = 12


class SkillExtractor:
    """Converts RawJob instances to JobData for the graph pipeline.

    When ``fit()`` is called with a corpus of job descriptions, skill importance
    is computed via TF-IDF: rare skills get higher importance (1-5 scale).
    Without ``fit()``, all skills default to importance=3.
    """

    def __init__(self, normalizer: SkillNormalizer) -> None:
        self._norm = normalizer
        self._idf: dict[str, float] = {}
        self._fitted = False

    def fit(self, raws: list[RawJob]) -> SkillExtractor:
        """Compute IDF from a corpus of job descriptions.

        After fitting, ``extract()`` uses TF-IDF to assign skill importance.
        """
        n = len(raws)
        if n == 0:
            self._fitted = True
            return self

        # doc_freq: how many JDs mention each skill
        doc_freq: dict[str, int] = {}
        for raw in raws:
            skills_in_doc = set(self._extract_skills(raw.description))
            for skill in skills_in_doc:
                doc_freq[skill] = doc_freq.get(skill, 0) + 1

        # IDF: log(N / df) — common skills get low IDF, rare skills high
        self._idf = {}
        for skill, df in doc_freq.items():
            self._idf[skill] = math.log(n / df)

        self._fitted = True
        return self

    def extract(self, raw: RawJob, job_id: int) -> JobData:
        """Extract structured fields from a single RawJob."""
        skills = self._extract_skills(raw.description)
        seniority = self._infer_seniority(raw.title, raw.description)
        sal_min, sal_max = self._normalize_salary(
            raw.salary_min, raw.salary_max, raw.salary_currency
        )
        importances = self._compute_per_jd_importances(
            skills, raw.title, raw.description
        )

        return JobData(
            job_id=job_id,
            seniority=seniority,
            skills=tuple(skills),
            skill_importances=importances,
            salary_min=sal_min,
            salary_max=sal_max,
            text=f"{raw.title}. {raw.description[:2000]}",
        )

    def extract_batch(self, raws: list[RawJob], start_id: int = 0) -> list[JobData]:
        """Extract a batch of RawJobs, assigning sequential IDs."""
        return [self.extract(raw, start_id + i) for i, raw in enumerate(raws)]

    # Patterns to detect "required" vs "nice-to-have" sections
    _REQUIRED_PATTERNS = re.compile(
        r"\b(?:required|must have|requirements?|mandatory|essential|minimum)\b", re.I
    )
    _NICE_TO_HAVE_PATTERNS = re.compile(
        r"\b(?:nice to have|preferred|bonus|plus|optional|desired|ideally)\b", re.I
    )

    def _compute_per_jd_importances(
        self, skills: list[str], title: str, description: str,
    ) -> tuple[int, ...]:
        """Compute skill importance per-JD based on context position.

        Priority:
          5 — skill appears in job title
          4 — skill in "required" / "must have" section
          2 — skill in "nice to have" / "preferred" section
          3 — skill in body (default)

        Then boost with TF-IDF if fitted (±1 level).
        """
        if not skills:
            return ()

        # Find skills in title
        title_skills = set(self._extract_skills(title))

        # Split description into required vs nice-to-have zones
        required_zone, nice_zone = self._split_zones(description)
        required_skills = set(self._extract_skills(required_zone)) if required_zone else set()
        nice_skills = set(self._extract_skills(nice_zone)) if nice_zone else set()

        importances: list[int] = []
        for skill in skills:
            if skill in title_skills:
                base = 5
            elif skill in required_skills:
                base = 4
            elif skill in nice_skills:
                base = 2
            else:
                base = 3

            # TF-IDF boost: rare skills +1, common skills -1
            if self._fitted and self._idf:
                idf = self._idf.get(skill, 0.0)
                median_idf = sorted(self._idf.values())[len(self._idf) // 2] if self._idf else 0
                if idf > median_idf * 1.3:
                    base = min(base + 1, 5)
                elif idf < median_idf * 0.7:
                    base = max(base - 1, 1)

            importances.append(base)

        return tuple(importances)

    @staticmethod
    def _split_zones(text: str) -> tuple[str, str]:
        """Split JD text into required zone and nice-to-have zone.

        Returns (required_text, nice_to_have_text). Either can be empty.
        """
        lines = text.split("\n")
        required_lines: list[str] = []
        nice_lines: list[str] = []
        current = required_lines  # default: everything is "required"

        req_pat = SkillExtractor._REQUIRED_PATTERNS
        nice_pat = SkillExtractor._NICE_TO_HAVE_PATTERNS

        for line in lines:
            if nice_pat.search(line):
                current = nice_lines
            elif req_pat.search(line):
                current = required_lines
            current.append(line)

        return "\n".join(required_lines), "\n".join(nice_lines)

    # ------------------------------------------------------------------
    # Skill extraction
    # ------------------------------------------------------------------

    # Single-char skills that need context to avoid false positives
    _CONTEXT_REQUIRED: dict[str, re.Pattern] = {
        "c": re.compile(r"\bC(?:\s*[/+]|(?:\s+(?:programming|language|developer|code)))", re.I),
        "r": re.compile(r"\bR(?:\s+(?:programming|language|Studio|developer|statistical))", re.I),
    }

    def _extract_skills(self, text: str) -> list[str]:
        """Find canonical skills mentioned in text.

        Strategy: split text into tokens/bigrams/trigrams,
        attempt to normalize each through the alias map.
        Deduplicate while preserving order.

        Single-char skills ("c", "r") require context patterns to avoid
        matching standalone letters in regular text.
        """
        seen: set[str] = set()
        result: list[str] = []

        # Tokenize, strip trailing punctuation
        words = [w.rstrip(".,;:") for w in re.findall(r"[\w#+.]+", text)]
        candidates: list[str] = []

        # Skip single-char tokens for unigrams (handled via context patterns)
        for w in words:
            if len(w) > 1:
                candidates.append(w)

        # Add bigrams and trigrams (these can capture "C++" "C#" etc.)
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                candidates.append(" ".join(words[i : i + n]))

        for candidate in candidates:
            canonical = self._norm.normalize(candidate)
            if canonical and canonical not in seen:
                seen.add(canonical)
                result.append(canonical)

        # Check context-required skills separately
        for canonical, pattern in self._CONTEXT_REQUIRED.items():
            if canonical not in seen and pattern.search(text):
                seen.add(canonical)
                result.append(canonical)

        return result

    # ------------------------------------------------------------------
    # Seniority inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_seniority(title: str, description: str) -> SeniorityLevel:
        """Infer seniority from title first, then description. Default: MID."""
        # Check title first (more reliable signal)
        for pattern, level in _SENIORITY_PATTERNS:
            if pattern.search(title):
                return level
        # Fallback: check description
        for pattern, level in _SENIORITY_PATTERNS:
            if pattern.search(description[:500]):
                return level
        return SeniorityLevel.MID

    # ------------------------------------------------------------------
    # Salary normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_salary(
        sal_min: float | None,
        sal_max: float | None,
        currency: str,
    ) -> tuple[int, int]:
        """Normalize salary to monthly USD. Returns (0, 0) if unknown."""
        if sal_min is None and sal_max is None:
            return 0, 0

        lo = sal_min or 0.0
        hi = sal_max or lo

        # Heuristic: if values > 500, likely annual → divide by 12
        if lo > 500:
            lo = lo / _SALARY_NORM_ANNUAL_TO_MONTHLY
            hi = hi / _SALARY_NORM_ANNUAL_TO_MONTHLY

        return int(lo), int(hi)
