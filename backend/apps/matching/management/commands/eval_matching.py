"""Matching-quality evaluation harness (feature 020).

Runs a FIXED, diverse set of IT CVs through the live matcher and reports, per CV,
the top-K jobs + whether they are on-domain (domain_fit ≥ 0.5), plus a summary
on-domain rate. Reproducible (CV set hard-coded). Use it before vs after the
domain-aware change to evidence the cross-domain noise is gone.

    python manage.py eval_matching            # top-5 per CV + summary
    python manage.py eval_matching --k 3
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

# (role label, seniority 0-5, experience yrs, skills, free text)
EVAL_CVS = [
    ("Frontend (React)", 3, 4, ["html_css", "javascript", "typescript", "react", "redux", "tailwind"], "Senior React frontend developer, SPA, responsive UI"),
    ("Frontend (Vue)", 2, 3, ["html_css", "javascript", "vuejs", "nuxtjs", "sass"], "Vue/Nuxt frontend engineer building web apps"),
    ("Backend (Python/Django)", 3, 5, ["python", "django", "postgresql", "redis", "docker"], "Backend engineer, REST APIs with Django and Postgres"),
    ("Backend (Node)", 2, 3, ["javascript", "nodejs", "express", "mongodb"], "Node.js backend developer, Express, MongoDB"),
    ("Fullstack (MERN)", 3, 4, ["javascript", "react", "nodejs", "express", "mongodb", "typescript"], "Fullstack MERN engineer"),
    ("DevOps", 4, 6, ["docker", "kubernetes", "aws", "terraform", "jenkins", "linux"], "DevOps engineer, CI/CD, Kubernetes, AWS"),
    ("Data/ML", 3, 4, ["python", "pandas", "numpy", "pytorch", "scikit_learn", "sql"], "Machine learning engineer, PyTorch, data pipelines"),
    ("Mobile (React Native)", 2, 3, ["javascript", "react", "react_native", "typescript"], "React Native mobile developer"),
    ("QA Automation", 2, 3, ["selenium", "cypress", "javascript", "testing"], "QA automation engineer, Selenium and Cypress"),
    ("Data Engineer", 3, 5, ["python", "sql", "spark", "airflow", "aws"], "Data engineer building ETL pipelines on Spark"),
    ("Java Backend", 3, 5, ["java", "spring", "postgresql", "kafka", "docker"], "Java backend engineer with Spring Boot"),
    ("PHP Backend", 2, 4, ["php", "laravel", "mysql", "javascript"], "PHP Laravel backend developer"),
    (".NET Backend", 3, 5, ["csharp", "dotnet", "sql", "azure"], "C# .NET backend engineer"),
    ("Android (Kotlin)", 2, 3, ["kotlin", "android", "java"], "Android developer with Kotlin"),
    ("iOS (Swift)", 3, 4, ["swift", "ios"], "iOS developer with Swift"),
    ("Cloud/AWS", 4, 6, ["aws", "terraform", "docker", "python", "linux"], "Cloud engineer, AWS infrastructure"),
    ("UI/UX + Frontend", 2, 3, ["html_css", "javascript", "react"], "Frontend developer with UI/UX focus"),
    ("Golang Backend", 3, 4, ["golang", "docker", "kubernetes", "postgresql"], "Go backend engineer, microservices"),
    ("Fullstack (Django+React)", 3, 5, ["python", "django", "javascript", "react", "postgresql"], "Fullstack Django + React engineer"),
    ("Junior Generalist", 1, 1, ["javascript", "html_css", "python", "sql"], "Junior software developer, eager to learn"),
]


class Command(BaseCommand):
    help = "Run a fixed diverse CV set through the live matcher; report on-domain quality."

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=5, help="top-K per CV (default 5).")

    def handle(self, *args, **opts):
        from apps.matching.services.matching_service import match_cv_data

        k = opts["k"]
        self.stdout.write(f"{'CV role':28} | top-{k} jobs (score · domain_fit) → on-domain?")
        self.stdout.write("-" * 110)

        top1_hits, ondomain_rates = 0, []
        for role, sen, exp, skills, text in EVAL_CVS:
            res = match_cv_data(skills=skills, seniority=sen, experience_years=exp, text=text, top_k=k)
            jobs = res.get("jobs", [])
            parts, flags = [], []
            for j in jobs:
                dm = (j.get("dim_scores") or {}).get("domain_fit", None)
                parts.append(f"{(j.get('title') or '')[:24]} ({j.get('score', 0):.2f}·dm{dm})")
                flags.append(1 if (dm is not None and dm >= 0.5) else 0)
            top1 = "✓on-domain" if (flags and flags[0]) else "✗OFF-DOMAIN"
            if flags and flags[0]:
                top1_hits += 1
            ondomain_rates.append(sum(flags) / len(flags) if flags else 0.0)
            self.stdout.write(f"{role:28} | " + " || ".join(parts) + f"   {top1}")

        n = len(EVAL_CVS)
        mean_rate = sum(ondomain_rates) / n if n else 0.0
        self.stdout.write("-" * 110)
        self.stdout.write(self.style.SUCCESS(
            f"SUMMARY: top1_on_domain = {top1_hits}/{n} ({100 * top1_hits / n:.0f}%) · "
            f"mean on_domain@{k} = {mean_rate:.2f}"
        ))
