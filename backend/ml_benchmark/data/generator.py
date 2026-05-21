from __future__ import annotations

import random as _random_mod

from ml_benchmark.data.skill_normalization import SkillNormalizer
from ml_benchmark.data.skill_taxonomy import (
    CLUSTER_DISPLAY_NAMES,
    SKILL_CLUSTERS,
    SKILL_SYNONYMS,
    TEXT_TEMPLATES_CV,
    TEXT_TEMPLATES_JOB,
    TEXT_TEMPLATES_JOB_CLUSTER,
)
from ml_benchmark.graph.schema import (
    SENIORITY_TO_SALARY_USD,
    SENIORITY_TO_YEARS,
    CVData,
    EducationLevel,
    JobData,
    SeniorityLevel,
    SkillCategory,
)

# Seniority weights for CV generation (all levels)
_CV_SENIORITY_WEIGHTS: dict[SeniorityLevel, float] = {
    SeniorityLevel.INTERN: 0.10,
    SeniorityLevel.JUNIOR: 0.25,
    SeniorityLevel.MID: 0.30,
    SeniorityLevel.SENIOR: 0.20,
    SeniorityLevel.LEAD: 0.10,
    SeniorityLevel.MANAGER: 0.05,
}

# JD seniority weights (no intern — companies don't post intern JDs as frequently)
_JOB_SENIORITY_WEIGHTS: dict[SeniorityLevel, float] = {
    SeniorityLevel.JUNIOR: 0.25,
    SeniorityLevel.MID: 0.35,
    SeniorityLevel.SENIOR: 0.25,
    SeniorityLevel.LEAD: 0.10,
    SeniorityLevel.MANAGER: 0.05,
}

# Skill count ranges by seniority
_CV_SKILL_COUNT: dict[SeniorityLevel, tuple[int, int]] = {
    SeniorityLevel.INTERN: (4, 6),
    SeniorityLevel.JUNIOR: (5, 8),
    SeniorityLevel.MID: (6, 10),
    SeniorityLevel.SENIOR: (8, 12),
    SeniorityLevel.LEAD: (8, 12),
    SeniorityLevel.MANAGER: (7, 11),
}

# Category distribution weights by seniority (technical, soft, tool, domain)
_CATEGORY_WEIGHTS: dict[SeniorityLevel, dict[SkillCategory, float]] = {
    SeniorityLevel.INTERN: {
        SkillCategory.TECHNICAL: 0.3,
        SkillCategory.SOFT: 0.3,
        SkillCategory.TOOL: 0.3,
        SkillCategory.DOMAIN: 0.1,
    },
    SeniorityLevel.JUNIOR: {
        SkillCategory.TECHNICAL: 0.3,
        SkillCategory.SOFT: 0.2,
        SkillCategory.TOOL: 0.4,
        SkillCategory.DOMAIN: 0.1,
    },
    SeniorityLevel.MID: {
        SkillCategory.TECHNICAL: 0.25,
        SkillCategory.SOFT: 0.15,
        SkillCategory.TOOL: 0.4,
        SkillCategory.DOMAIN: 0.2,
    },
    SeniorityLevel.SENIOR: {
        SkillCategory.TECHNICAL: 0.2,
        SkillCategory.SOFT: 0.15,
        SkillCategory.TOOL: 0.35,
        SkillCategory.DOMAIN: 0.3,
    },
    SeniorityLevel.LEAD: {
        SkillCategory.TECHNICAL: 0.15,
        SkillCategory.SOFT: 0.25,
        SkillCategory.TOOL: 0.3,
        SkillCategory.DOMAIN: 0.3,
    },
    SeniorityLevel.MANAGER: {
        SkillCategory.TECHNICAL: 0.1,
        SkillCategory.SOFT: 0.35,
        SkillCategory.TOOL: 0.25,
        SkillCategory.DOMAIN: 0.3,
    },
}

# Proficiency ranges by seniority (min, max) for random.randint
_PROFICIENCY_RANGE: dict[SeniorityLevel, tuple[int, int]] = {
    SeniorityLevel.INTERN: (1, 2),
    SeniorityLevel.JUNIOR: (1, 3),
    SeniorityLevel.MID: (2, 4),
    SeniorityLevel.SENIOR: (3, 5),
    SeniorityLevel.LEAD: (3, 5),
    SeniorityLevel.MANAGER: (2, 4),
}

# Education level weights by seniority
_EDU_WEIGHTS: dict[SeniorityLevel, list[tuple[EducationLevel, float]]] = {
    SeniorityLevel.INTERN: [
        (EducationLevel.COLLEGE, 0.4),
        (EducationLevel.BACHELOR, 0.5),
        (EducationLevel.MASTER, 0.1),
    ],
    SeniorityLevel.JUNIOR: [
        (EducationLevel.COLLEGE, 0.2),
        (EducationLevel.BACHELOR, 0.6),
        (EducationLevel.MASTER, 0.2),
    ],
    SeniorityLevel.MID: [
        (EducationLevel.COLLEGE, 0.1),
        (EducationLevel.BACHELOR, 0.6),
        (EducationLevel.MASTER, 0.3),
    ],
    SeniorityLevel.SENIOR: [
        (EducationLevel.BACHELOR, 0.5),
        (EducationLevel.MASTER, 0.4),
        (EducationLevel.PHD, 0.1),
    ],
    SeniorityLevel.LEAD: [
        (EducationLevel.BACHELOR, 0.4),
        (EducationLevel.MASTER, 0.5),
        (EducationLevel.PHD, 0.1),
    ],
    SeniorityLevel.MANAGER: [
        (EducationLevel.BACHELOR, 0.3),
        (EducationLevel.MASTER, 0.5),
        (EducationLevel.PHD, 0.2),
    ],
}


class SyntheticDataGenerator:
    def __init__(
        self,
        normalizer: SkillNormalizer,
        seed: int = 42,
        *,
        synonym_rate: float = 0.0,
        implicit_skill_rate: float = 0.0,
        cluster_rate: float = 0.0,
    ) -> None:
        self._norm = normalizer
        self._rng = _random_mod.Random(seed)
        self._synonym_rate = synonym_rate
        self._implicit_skill_rate = implicit_skill_rate
        self._cluster_rate = cluster_rate
        self._skills_by_cat: dict[SkillCategory, list[str]] = {
            cat: normalizer.get_skills_by_category(cat) for cat in SkillCategory
        }
        # Metadata populated during generation
        self.cv_text_skills: dict[int, set[str]] = {}
        self.job_clusters: dict[int, list[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_cvs(self, n: int) -> list[CVData]:
        self.cv_text_skills = {}
        return [self._make_cv(i) for i in range(n)]

    def generate_jobs(self, n: int) -> list[JobData]:
        self.job_clusters = {}
        return [self._make_job(i) for i in range(n)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _weighted_choice(self, options: dict | list, *, is_list: bool = False):
        if is_list:
            items, weights = zip(*options)
        else:
            items = list(options.keys())
            weights = list(options.values())
        return self._rng.choices(items, weights=weights, k=1)[0]

    def _sample_skills(self, seniority: SeniorityLevel, count: int) -> list[str]:
        cat_weights = _CATEGORY_WEIGHTS[seniority]
        sampled: list[str] = []
        attempts = 0
        while len(sampled) < count and attempts < count * 10:
            cat = self._weighted_choice(cat_weights)
            pool = self._skills_by_cat.get(cat, [])
            if not pool:
                attempts += 1
                continue
            skill = self._rng.choice(pool)
            if skill not in sampled:
                sampled.append(skill)
            attempts += 1
        return sampled

    def _skill_to_text(self, skill: str) -> str:
        """Convert canonical skill to a surface form for text generation."""
        if self._synonym_rate > 0 and self._rng.random() < self._synonym_rate:
            synonyms = SKILL_SYNONYMS.get(skill)
            if synonyms:
                return self._rng.choice(synonyms)
        return skill

    def _natural_join(self, items: list[str]) -> str:
        """Join items with commas and 'and': 'A, B, and C'."""
        if len(items) <= 1:
            return items[0] if items else ""
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + ", and " + items[-1]

    def _make_cv(self, idx: int) -> CVData:
        seniority = self._weighted_choice(_CV_SENIORITY_WEIGHTS)
        yr_lo, yr_hi = SENIORITY_TO_YEARS[seniority]
        experience = round(self._rng.uniform(yr_lo, yr_hi), 1)

        lo, hi = _CV_SKILL_COUNT[seniority]
        num_skills = self._rng.randint(lo, hi)
        all_skills = self._sample_skills(seniority, num_skills)

        # Split into structured skills vs text-only skills
        struct_skills = []
        text_only_skills: set[str] = set()
        for skill in all_skills:
            if self._implicit_skill_rate > 0 and self._rng.random() < self._implicit_skill_rate:
                text_only_skills.add(skill)
            else:
                struct_skills.append(skill)

        # Ensure at least 2 structured skills remain
        if len(struct_skills) < 2 and text_only_skills:
            while len(struct_skills) < 2 and text_only_skills:
                struct_skills.append(text_only_skills.pop())

        if text_only_skills:
            self.cv_text_skills[idx] = text_only_skills

        prof_lo, prof_hi = _PROFICIENCY_RANGE[seniority]
        proficiencies = [self._rng.randint(prof_lo, prof_hi) for _ in struct_skills]

        edu = self._weighted_choice(_EDU_WEIGHTS[seniority], is_list=True)

        # Text includes ALL skills (structured + text-only)
        text = self._cv_text(seniority, all_skills, experience, edu)

        return CVData(
            cv_id=idx,
            seniority=seniority,
            experience_years=experience,
            education=edu,
            skills=tuple(struct_skills),
            skill_proficiencies=tuple(proficiencies),
            text=text,
        )

    def _make_job(self, idx: int) -> JobData:
        seniority = self._weighted_choice(_JOB_SENIORITY_WEIGHTS)
        num_skills = self._rng.randint(3, 8)
        skills = self._sample_skills(seniority, num_skills)
        importances = [self._rng.randint(1, 5) for _ in skills]

        sal_lo, sal_hi = SENIORITY_TO_SALARY_USD[seniority]
        salary_min = self._rng.randint(sal_lo, (sal_lo + sal_hi) // 2)
        salary_max = self._rng.randint((sal_lo + sal_hi) // 2, sal_hi)

        # Optionally assign cluster requirements
        clusters: list[str] = []
        if self._cluster_rate > 0 and self._rng.random() < self._cluster_rate:
            available = [c for c in SKILL_CLUSTERS if any(s in SKILL_CLUSTERS[c] for s in skills)]
            if available:
                clusters = [self._rng.choice(available)]
                self.job_clusters[idx] = clusters

        text = self._job_text(seniority, skills, salary_min, salary_max, clusters)

        return JobData(
            job_id=idx,
            seniority=seniority,
            skills=tuple(skills),
            skill_importances=tuple(importances),
            salary_min=salary_min,
            salary_max=salary_max,
            text=text,
        )

    # ------------------------------------------------------------------
    # Text generation
    # ------------------------------------------------------------------

    def _cv_text(
        self,
        seniority: SeniorityLevel,
        skills: list[str],
        experience: float,
        edu: EducationLevel,
    ) -> str:
        skill_texts = [self._skill_to_text(s) for s in skills]
        skills_str = self._natural_join(skill_texts)
        title = seniority.name.capitalize()
        template = self._rng.choice(TEXT_TEMPLATES_CV)
        return template.format(
            title=title,
            exp=experience,
            skills=skills_str,
            edu=edu.name.lower(),
        )

    def _job_text(
        self,
        seniority: SeniorityLevel,
        skills: list[str],
        salary_min: int,
        salary_max: int,
        clusters: list[str],
    ) -> str:
        skill_texts = [self._skill_to_text(s) for s in skills]
        skills_str = self._natural_join(skill_texts)

        if clusters:
            cluster_name = CLUSTER_DISPLAY_NAMES.get(clusters[0], clusters[0])
            template = self._rng.choice(TEXT_TEMPLATES_JOB_CLUSTER)
            return template.format(
                level=seniority.name.lower(),
                cluster_name=cluster_name,
                skills=skills_str,
                sal_min=salary_min,
                sal_max=salary_max,
            )

        template = self._rng.choice(TEXT_TEMPLATES_JOB)
        return template.format(
            level=seniority.name.lower(),
            skills=skills_str,
            sal_min=salary_min,
            sal_max=salary_max,
        )
