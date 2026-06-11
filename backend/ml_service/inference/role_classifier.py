"""Infer role category from skills/text for role-based matching penalty.

Roles: frontend, backend, fullstack, devops, data, mobile, security, other.
If CV role != JD role → penalty on matching score.
"""

from __future__ import annotations

import re

# Role → defining skills (if >= 2 match, assign this role)
_ROLE_SKILLS: dict[str, set[str]] = {
    "frontend": {"react", "vuejs", "angular", "nextjs", "html_css", "tailwind", "sass", "bootstrap", "redux", "typescript", "javascript", "css", "html", "vite", "webpack", "nuxtjs"},
    "backend": {"django", "fastapi", "flask", "spring", "express", "nestjs", "nodejs", "laravel", "rails", "postgresql", "mysql", "mongodb", "redis", "kafka", "rabbitmq", "grpc", "graphql", "java", "python", "golang", "csharp", "dotnet", "php", "ruby", "scala", "kotlin", "hibernate", "jpa", "rest_api", "microservices"},
    "devops": {"docker", "kubernetes", "terraform", "ansible", "ci_cd", "aws", "gcp", "azure", "helm", "argocd", "prometheus", "grafana", "jenkins", "nginx", "linux"},
    "data": {"spark", "airflow", "hadoop", "hive", "flink", "snowflake", "databricks", "dbt", "bigquery", "pandas", "numpy", "data_engineering", "data_science", "etl", "sql", "tableau", "powerbi"},
    "ml": {"machine_learning", "deep_learning", "pytorch", "tensorflow", "scikit_learn", "nlp", "computer_vision", "llm", "xgboost", "mlflow", "sagemaker", "langchain"},
    "mobile": {"react_native", "flutter", "ios", "android", "swift", "kotlin"},
    "qa": {"manual_testing", "api_testing", "selenium", "cypress", "playwright_tool", "appium", "jmeter", "unit_testing", "mockito"},
    "design": {"figma", "framer", "storybook"},
    "security": {"security", "cybersecurity", "penetration_testing", "soc", "siem"},
    "erp": {"sap", "oracle_erp", "salesforce", "dynamics365", "workday", "servicenow"},
}

# Role → title keywords
_ROLE_TITLE_PATTERNS: dict[str, re.Pattern] = {
    # 024 refinement: qa/design/ba inferable from CV titles too (jobs already
    # carry these roles via extraction/backfill — the gap was CV-side).
    # design/qa/ba MUST precede frontend: its pattern includes \b(ui|ux)\b.
    "design": re.compile(r"\b(?:ui/?ux\s+designer|product\s+designer|graphic\s+designer|web\s+designer|designer)\b", re.I),
    "qa": re.compile(r"\b(?:qa|qc|tester|sdet|quality\s+(?:assurance|control|engineer)|test\s+(?:engineer|analyst|automation))\b", re.I),
    "ba": re.compile(r"\b(?:business\s+analyst|product\s+(?:owner|manager)|scrum\s+master|project\s+manager)\b", re.I),
    "frontend": re.compile(r"\b(?:front.?end|ui|ux|react|vue|angular)\b", re.I),
    "backend": re.compile(r"\b(?:back.?end|server|api|django|spring|node)\b", re.I),
    "fullstack": re.compile(r"\b(?:full.?stack)\b", re.I),
    "devops": re.compile(r"\b(?:devops|sre|platform|infra|cloud|reliability)\b", re.I),
    "data": re.compile(r"\b(?:data\s+(?:engineer|analyst|scientist)|etl|bi\b|analytics)\b", re.I),
    "ml": re.compile(r"\b(?:machine\s+learning|ml\b|ai\b|deep\s+learning|nlp|computer\s+vision)\b", re.I),
    "mobile": re.compile(r"\b(?:mobile|ios|android|react\s+native|flutter)\b", re.I),
    "security": re.compile(r"\b(?:security|cyber|penetration|soc)\b", re.I),
    "erp": re.compile(r"\b(?:sap|salesforce|oracle\s+erp|workday|dynamics|servicenow|crm\s+consultant|erp\s+consultant)\b", re.I),
}

# Roles that are compatible (no penalty between them)
_COMPATIBLE_ROLES: dict[str, set[str]] = {
    "frontend": {"frontend", "fullstack"},
    "backend": {"backend", "fullstack"},
    "fullstack": {"frontend", "backend", "fullstack"},
    "devops": {"devops", "backend"},
    "data_eng": {"data_eng", "data_ml", "backend"},
    "data_ml": {"data_ml", "data_eng"},
    "mobile": {"mobile", "frontend"},
    "qa": {"qa"},
    "design": {"design"},
    "ba": {"ba"},
    "other": set(),  # compatible with everything
}


# 023/3.5: canonicalize internal role names to the Job.role_category taxonomy
# (backend/frontend/fullstack/mobile/devops/data_ml/data_eng/qa/design/ba/other).
# Before this, infer_role returned "data"/"ml"/"security"/"erp" which NEVER
# equaled any Job category → data CVs could not domain-match ANY data job.
_CANONICAL_ROLE = {
    "ml": "data_ml",
    "data": "data_eng",
    "security": "devops",
    "erp": "other",
}


def infer_role(skills: tuple[str, ...] | set[str], text: str = "") -> str:
    """Infer primary role from skills and/or text.

    Returns one of the Job.role_category values: frontend, backend, fullstack,
    devops, data_ml, data_eng, mobile, other (qa/design/ba are not inferable
    from dev-skill signals and fall to other).
    """
    return _CANONICAL_ROLE.get(_infer_role_raw(skills, text), _infer_role_raw(skills, text))


def _infer_role_raw(skills: tuple[str, ...] | set[str], text: str = "") -> str:
    skill_set = set(skills)

    # Check title patterns first (strongest signal)
    for role, pattern in _ROLE_TITLE_PATTERNS.items():
        if pattern.search(text[:200]):  # check first 200 chars (title area)
            return role

    # Count skill matches per role
    scores: dict[str, int] = {}
    for role, defining_skills in _ROLE_SKILLS.items():
        overlap = len(skill_set & defining_skills)
        if overlap >= 2:
            scores[role] = overlap

    if not scores:
        return "other"

    # If both frontend and backend skills → fullstack
    if "frontend" in scores and "backend" in scores:
        return "fullstack"

    return max(scores, key=lambda r: scores[r])


# Roles with moderate overlap — partial penalty
_ADJACENT_ROLES: dict[str, set[str]] = {
    "frontend": {"backend", "fullstack"},
    "backend": {"frontend", "fullstack", "devops"},
    "fullstack": {"frontend", "backend", "devops"},
    "devops": {"backend", "fullstack"},
    "data_eng": {"data_ml", "backend"},
    "data_ml": {"data_eng", "backend"},
    "mobile": {"frontend", "fullstack"},
    "design": {"frontend"},
    "qa": {"backend", "frontend"},
}


def role_match_penalty(cv_role: str, job_role: str) -> float:
    """Penalty multiplier for role mismatch.

    Returns:
        1.0  — same role or compatible (e.g. frontend↔fullstack)
        0.7  — adjacent roles (e.g. frontend↔backend, data↔ml)
        0.45 — clear mismatch (e.g. frontend↔devops, frontend↔data)
    """
    if cv_role == "other" or job_role == "other":
        return 1.0  # can't determine → no penalty

    if cv_role == job_role:
        return 1.0

    compatible = _COMPATIBLE_ROLES.get(cv_role, set())
    if job_role in compatible:
        return 1.0

    reverse_compatible = _COMPATIBLE_ROLES.get(job_role, set())
    if cv_role in reverse_compatible:
        return 1.0

    # Adjacent roles — partial penalty
    adjacent = _ADJACENT_ROLES.get(cv_role, set())
    if job_role in adjacent:
        return 0.7

    reverse_adjacent = _ADJACENT_ROLES.get(job_role, set())
    if cv_role in reverse_adjacent:
        return 0.7

    # Clear mismatch (e.g. frontend vs data/ml/security/devops)
    return 0.45
