from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeType(StrEnum):
    CV = "cv"
    JOB = "job"
    SKILL = "skill"
    SENIORITY = "seniority"


class EdgeType(StrEnum):
    HAS_SKILL = "has_skill"
    REQUIRES_SKILL = "requires_skill"
    HAS_SENIORITY = "has_seniority"
    REQUIRES_SENIORITY = "requires_seniority"
    MATCH = "match"
    NO_MATCH = "no_match"


# (source_node_type, edge_type, dest_node_type)
EDGE_TRIPLETS: dict[EdgeType, tuple[str, str, str]] = {
    EdgeType.HAS_SKILL: ("cv", "has_skill", "skill"),
    EdgeType.REQUIRES_SKILL: ("job", "requires_skill", "skill"),
    EdgeType.HAS_SENIORITY: ("cv", "has_seniority", "seniority"),
    EdgeType.REQUIRES_SENIORITY: ("job", "requires_seniority", "seniority"),
    EdgeType.MATCH: ("cv", "match", "job"),
    EdgeType.NO_MATCH: ("cv", "no_match", "job"),
}


class SeniorityLevel(IntEnum):
    INTERN = 0
    JUNIOR = 1
    MID = 2
    SENIOR = 3
    LEAD = 4
    MANAGER = 5


class SkillCategory(IntEnum):
    TECHNICAL = 0
    SOFT = 1
    TOOL = 2
    DOMAIN = 3


class EducationLevel(IntEnum):
    NONE = 0
    COLLEGE = 1
    BACHELOR = 2
    MASTER = 3
    PHD = 4


# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

SENIORITY_TO_YEARS: dict[SeniorityLevel, tuple[float, float]] = {
    SeniorityLevel.INTERN: (0, 0.5),
    SeniorityLevel.JUNIOR: (0.5, 2),
    SeniorityLevel.MID: (2, 5),
    SeniorityLevel.SENIOR: (5, 10),
    SeniorityLevel.LEAD: (7, 15),
    SeniorityLevel.MANAGER: (8, 20),
}

SENIORITY_TO_SALARY_USD: dict[SeniorityLevel, tuple[int, int]] = {
    SeniorityLevel.INTERN: (500, 1_500),
    SeniorityLevel.JUNIOR: (1_000, 2_500),
    SeniorityLevel.MID: (2_000, 4_000),
    SeniorityLevel.SENIOR: (3_500, 6_000),
    SeniorityLevel.LEAD: (5_000, 8_000),
    SeniorityLevel.MANAGER: (5_000, 10_000),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CVData:
    cv_id: int
    seniority: SeniorityLevel
    experience_years: float
    education: EducationLevel
    skills: tuple[str, ...]
    skill_proficiencies: tuple[int, ...]  # 1-5 per skill
    text: str  # free-text for embedding


@dataclass(frozen=True)
class JobData:
    job_id: int
    seniority: SeniorityLevel
    skills: tuple[str, ...]
    skill_importances: tuple[int, ...]  # 1-5 per skill
    salary_min: int
    salary_max: int
    text: str  # free-text for embedding
    experience_min: float = 0.0
    experience_max: float | None = None
    role_category: str = ""


@dataclass(frozen=True)
class LabeledPair:
    cv_id: int
    job_id: int
    label: int  # 1 = match, 0 = no_match
    split: str = "train"  # train / val / test


@dataclass(frozen=True)
class DatasetSplit:
    train: list[LabeledPair] = field(default_factory=list)
    val: list[LabeledPair] = field(default_factory=list)
    test: list[LabeledPair] = field(default_factory=list)
