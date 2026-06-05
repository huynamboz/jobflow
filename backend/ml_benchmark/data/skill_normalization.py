from __future__ import annotations

import json
import logging
from pathlib import Path

from ml_benchmark.config import get_settings
from ml_benchmark.graph.schema import SkillCategory

logger = logging.getLogger(__name__)


class SkillNormalizer:
    """Load skill-alias.json and provide alias -> canonical lookups."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = get_settings().skill_alias_path
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        skills_data: dict = raw["skills"]

        # canonical -> category
        self._catalog: dict[str, SkillCategory] = {}
        # lowercase alias -> canonical
        self._alias_map: dict[str, str] = {}

        for canonical, info in skills_data.items():
            cat = SkillCategory(info["category"])
            self._catalog[canonical] = cat
            # Map the canonical name itself (lowered)
            self._alias_map[canonical.lower()] = canonical
            for alias in info.get("aliases", []):
                self._alias_map[alias.lower()] = canonical

    def normalize(self, raw_skill: str) -> str | None:
        """Return canonical skill name, or None if unknown."""
        result = self._alias_map.get(raw_skill.strip().lower())
        if result is None:
            logger.debug("Skill dropped (not in taxonomy): %r", raw_skill)
        return result

    @property
    def canonical_skills(self) -> list[str]:
        """All canonical skill names."""
        return list(self._catalog.keys())

    @property
    def skill_catalog(self) -> dict[str, SkillCategory]:
        """Mapping of canonical skill name -> SkillCategory."""
        return dict(self._catalog)

    def get_skills_by_category(self, category: SkillCategory) -> list[str]:
        """Return canonical skill names belonging to *category*."""
        return [s for s, c in self._catalog.items() if c == category]
