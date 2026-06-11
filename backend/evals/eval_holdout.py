"""Held-out eval — 20 personas NOT used in any tuning loop (docs 12)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup()
import logging; logging.disable(logging.WARNING)
from apps.matching.services.matching_service import match_cv_data

CVS = [
  ("Frontend (Angular)", 3, 5, ["angular", "typescript", "javascript", "html_css", "sass"], "Senior Angular frontend engineer, enterprise SPA"),
  ("Frontend (Svelte)", 2, 3, ["svelte", "javascript", "html_css", "vite", "tailwind"], "Frontend developer with Svelte, building modern web UIs"),
  ("Backend (FastAPI)", 2, 3, ["python", "fastapi", "postgresql", "redis", "docker"], "Backend developer building async APIs with FastAPI"),
  ("Backend (Flask)", 2, 4, ["python", "flask", "celery", "mysql", "gitlab_ci"], "Python backend engineer, Flask microservices"),
  ("Backend (Spring Kotlin)", 3, 6, ["kotlin", "spring", "postgresql", "kafka", "microservices"], "Senior Kotlin Spring Boot backend engineer"),
  ("Backend (Ruby)", 3, 5, ["ruby", "rails", "postgresql", "redis", "rest_api"], "Senior Ruby on Rails developer"),
  ("Fullstack (Vue+Laravel)", 2, 4, ["php", "laravel", "vuejs", "mysql", "javascript"], "Fullstack developer with Laravel and Vue"),
  ("Fullstack (T3/Next)", 2, 3, ["typescript", "nextjs", "react", "trpc", "postgresql"], "Fullstack TypeScript engineer with Next.js"),
  ("SRE", 4, 7, ["kubernetes", "prometheus", "grafana", "terraform", "golang", "linux"], "Site reliability engineer, observability and infra"),
  ("Platform (Azure)", 3, 5, ["azure", "terraform", "kubernetes", "ci_cd", "powershell"], "Platform engineer on Azure cloud"),
  ("Data Scientist", 3, 4, ["python", "pandas", "scikit_learn", "sql", "data_science"], "Data scientist, statistical modeling and experimentation"),
  ("ML (NLP)", 3, 4, ["python", "pytorch", "nlp", "huggingface", "llm"], "NLP engineer fine-tuning transformer models"),
  ("Data Eng (GCP)", 2, 3, ["python", "bigquery", "airflow", "dbt", "sql"], "Data engineer building ELT on GCP"),
  ("Analytics Eng", 2, 3, ["sql", "dbt", "tableau", "python"], "Analytics engineer, BI dashboards and metrics"),
  ("Mobile (Flutter)", 2, 3, ["flutter", "android", "ios"], "Flutter mobile developer, cross-platform apps"),
  ("QA Manual->Auto", 1, 2, ["manual_testing", "api_testing", "postman", "sql"], "QA engineer transitioning from manual to automation"),
  ("Security Eng", 3, 5, ["security", "cybersecurity", "linux", "python", "siem"], "Security engineer, SOC and incident response"),
  ("DBA", 3, 6, ["postgresql", "mysql", "sql", "linux", "bash"], "Database administrator, performance tuning and HA"),
  ("Game Dev (Unity)", 2, 3, ["csharp", "oop", "git"], "Unity game developer, C# gameplay programming"),
  ("Fresh Grad (CS)", 0, 0, ["python", "java", "sql", "git"], "Computer science fresh graduate seeking first role"),
]

hits, rates = 0, []
for role, sen, exp, skills, text in CVS:
    res = match_cv_data(skills=skills, seniority=sen, experience_years=exp, text=text, top_k=5)
    jobs = res.get("jobs", [])
    flags = [1 if ((j.get("dim_scores") or {}).get("domain_fit", 0) or 0) >= 0.5 else 0 for j in jobs]
    hits += bool(flags and flags[0])
    rates.append(sum(flags) / len(flags) if flags else 0)
print(f"HELD-OUT SUMMARY: top1_on_domain = {hits}/20 ({hits*5}%) · mean on_domain@5 = {sum(rates)/len(rates):.2f}")
