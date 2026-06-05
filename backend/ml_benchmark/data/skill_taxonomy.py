"""Skill synonyms, clusters, and text templates for realistic synthetic data."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Skill synonyms: canonical -> natural language surface forms for text generation
# ---------------------------------------------------------------------------
SKILL_SYNONYMS: dict[str, list[str]] = {
    "python": ["Python", "Python3", "Python programming"],
    "javascript": ["JavaScript", "JS", "ECMAScript"],
    "typescript": ["TypeScript", "TS"],
    "java": ["Java", "Core Java", "Java platform"],
    "go": ["Go", "Golang"],
    "rust": ["Rust", "Rust programming"],
    "cpp": ["C++", "C/C++"],
    "csharp": ["C#", ".NET C#"],
    "react": ["React", "ReactJS", "React.js", "React framework"],
    "nextjs": ["Next.js", "NextJS"],
    "vuejs": ["Vue.js", "VueJS", "Vue"],
    "angular": ["Angular", "Angular framework"],
    "nodejs": ["Node.js", "NodeJS", "server-side JavaScript"],
    "express": ["Express.js", "Express framework"],
    "fastapi": ["FastAPI", "Fast API"],
    "django": ["Django", "Django REST Framework"],
    "flask": ["Flask", "Flask framework"],
    "spring": ["Spring Boot", "Spring Framework"],
    "postgresql": ["PostgreSQL", "Postgres", "Postgres database"],
    "mysql": ["MySQL", "MySQL database"],
    "mongodb": ["MongoDB", "Mongo", "NoSQL MongoDB"],
    "redis": ["Redis", "Redis cache"],
    "elasticsearch": ["Elasticsearch", "Elastic Search", "ELK stack"],
    "aws": ["AWS", "Amazon Web Services", "cloud infrastructure on AWS"],
    "gcp": ["Google Cloud", "GCP", "Google Cloud Platform"],
    "azure": ["Microsoft Azure", "Azure cloud"],
    "docker": ["Docker", "containerization with Docker", "Docker containers"],
    "kubernetes": ["Kubernetes", "K8s", "container orchestration"],
    "terraform": ["Terraform", "infrastructure as code with Terraform"],
    "ci_cd": ["CI/CD", "continuous integration and deployment"],
    "git": ["Git", "version control with Git"],
    "linux": ["Linux", "Linux administration", "Unix/Linux"],
    "machine_learning": ["machine learning", "ML", "applied machine learning"],
    "deep_learning": ["deep learning", "neural networks", "DL"],
    "pytorch": ["PyTorch", "PyTorch framework"],
    "tensorflow": ["TensorFlow", "TF"],
    "nlp": ["NLP", "natural language processing"],
    "data_science": ["data science", "data analysis and science"],
    "rest_api": ["REST APIs", "RESTful services", "API development"],
    "graphql": ["GraphQL", "GraphQL APIs"],
    "microservices": ["microservices", "microservice architecture"],
    "kafka": ["Apache Kafka", "Kafka messaging"],
    "sql": ["SQL", "relational databases", "SQL databases"],
    "html_css": ["HTML/CSS", "web markup and styling"],
    "react_native": ["React Native", "cross-platform mobile with React Native"],
    "flutter": ["Flutter", "Flutter/Dart"],
    "agile": ["Agile", "Scrum/Agile methodology"],
    "system_design": ["system design", "software architecture"],
    "unit_testing": ["unit testing", "TDD", "test-driven development"],
    "security": ["application security", "cybersecurity practices"],
}

# ---------------------------------------------------------------------------
# Skill clusters: abstract roles -> constituent canonical skills
# ---------------------------------------------------------------------------
SKILL_CLUSTERS: dict[str, list[str]] = {
    "fullstack_web": ["react", "nodejs", "postgresql", "html_css", "javascript", "typescript"],
    "backend_python": ["python", "fastapi", "django", "flask", "postgresql", "redis"],
    "backend_java": ["java", "spring", "postgresql", "mysql", "kafka"],
    "frontend": ["react", "vuejs", "angular", "nextjs", "html_css", "tailwind", "javascript", "typescript"],
    "devops": ["docker", "kubernetes", "terraform", "ci_cd", "aws", "linux"],
    "data_ml": ["python", "pytorch", "tensorflow", "scikit_learn", "pandas", "numpy", "machine_learning"],
    "mobile": ["react_native", "flutter", "ios", "android", "swift", "kotlin"],
    "data_eng": ["python", "sql", "spark", "airflow", "kafka", "aws", "data_engineering"],
}

# Minimum coverage ratio for a cluster to be considered "covered"
_CLUSTER_COVERAGE_THRESHOLD = 0.4


def cluster_coverage(cv_skills: set[str], clusters: list[str]) -> float:
    """Fraction of required clusters covered by cv_skills.

    A cluster is "covered" if the CV has >= 40% of its member skills.
    Returns 0.0–1.0.
    """
    if not clusters:
        return 0.0
    covered = 0
    for cluster_name in clusters:
        members = SKILL_CLUSTERS.get(cluster_name, [])
        if not members:
            continue
        overlap = len(cv_skills & set(members)) / len(members)
        if overlap >= _CLUSTER_COVERAGE_THRESHOLD:
            covered += 1
    return covered / len(clusters)


# ---------------------------------------------------------------------------
# Varied text templates
# ---------------------------------------------------------------------------
TEXT_TEMPLATES_CV = [
    "{title} developer with {exp} years of hands-on experience. Proficient in {skills}. Holds a {edu} degree.",
    "Experienced {title} engineer specializing in {skills}. {exp} years in the industry with {edu} education.",
    "Results-driven {title} professional. Core competencies include {skills}. {exp} years of experience, {edu} background.",
    "{title} software engineer bringing {exp} years of expertise in {skills}. Academic background: {edu}.",
    "Passionate {title} developer skilled in {skills}. {exp}+ years building production systems. Education: {edu}.",
    "{edu} graduate working as {title} engineer for {exp} years. Technical stack: {skills}.",
    "Detail-oriented {title} professional with {exp} years experience. Expertise spans {skills}. {edu} educated.",
]

TEXT_TEMPLATES_JOB = [
    "Hiring {level} software engineer. Required skills: {skills}. Salary: ${sal_min}-${sal_max}/month.",
    "We are looking for a {level} developer experienced in {skills}. Compensation: ${sal_min}-${sal_max} monthly.",
    "{level} engineer needed. Must be proficient in {skills}. Budget: ${sal_min}-${sal_max} USD/month.",
    "Join our team as a {level} developer. You should know {skills}. We offer ${sal_min}-${sal_max}/month.",
    "Open role: {level} software engineer with strong {skills} skills. Pay range ${sal_min}-${sal_max}/month.",
    "Seeking {level} engineer. Ideal candidate has experience with {skills}. Salary ${sal_min}-${sal_max}/month.",
]

TEXT_TEMPLATES_JOB_CLUSTER = [
    "Hiring {level} {cluster_name} developer. Key skills: {skills}. Salary: ${sal_min}-${sal_max}/month.",
    "Looking for a {level} {cluster_name} engineer with expertise in {skills}. Budget ${sal_min}-${sal_max}/month.",
    "We need a {level} {cluster_name} specialist. Required: {skills}. Compensation: ${sal_min}-${sal_max}/month.",
]

# Human-readable cluster labels
CLUSTER_DISPLAY_NAMES: dict[str, str] = {
    "fullstack_web": "fullstack web",
    "backend_python": "Python backend",
    "backend_java": "Java backend",
    "frontend": "frontend",
    "devops": "DevOps",
    "data_ml": "machine learning",
    "mobile": "mobile",
    "data_eng": "data engineering",
}
