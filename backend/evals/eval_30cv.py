"""30-persona eval — diverse stacks/seniorities incl. niches (docs 12)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup()
import logging; logging.disable(logging.WARNING)
from apps.matching.services.matching_service import match_cv_data

CVS = [
  ("FE React junior", 1, 1.5, ["react","javascript","html_css","redux"], "Junior React developer, SPA development"),
  ("FE Vue mid", 2, 3, ["vuejs","nuxtjs","typescript","tailwind"], "Vue/Nuxt frontend developer"),
  ("FE Angular senior", 3, 6, ["angular","typescript","sass","webpack"], "Senior Angular engineer, enterprise apps"),
  ("BE Java Spring", 3, 5, ["java","spring","hibernate","mysql","kafka"], "Senior Java backend, microservices"),
  ("BE Go", 2, 3, ["golang","postgresql","grpc","docker"], "Go backend engineer, high-throughput services"),
  ("BE PHP Laravel", 2, 4, ["php","laravel","mysql","redis"], "PHP Laravel backend developer"),
  ("BE Node Nest", 2, 3, ["nodejs","nestjs","typescript","mongodb"], "NestJS backend developer"),
  ("BE Python lead", 4, 9, ["python","django","postgresql","aws","system_design"], "Lead backend engineer, architecture and mentoring"),
  ("BE C#/.NET", 3, 5, ["csharp","dotnet","sql_server","azure"], "Senior .NET backend developer"),
  ("Fullstack PERN", 2, 3, ["react","nodejs","express","postgresql","typescript"], "Fullstack JS developer, PERN stack"),
  ("Fullstack Django+React", 3, 5, ["python","django","react","postgresql","docker"], "Fullstack engineer Python/React"),
  ("Fullstack junior", 1, 1, ["javascript","nodejs","react","mongodb"], "Junior fullstack developer, MERN"),
  ("DevOps AWS", 3, 5, ["aws","terraform","kubernetes","ci_cd","python"], "DevOps engineer on AWS"),
  ("DevOps GCP junior", 1, 1.5, ["gcp","docker","linux","bash"], "Junior cloud engineer, GCP"),
  ("SRE senior", 4, 8, ["kubernetes","prometheus","grafana","golang","terraform"], "Senior SRE, reliability and observability"),
  ("Data Scientist mid", 2, 3, ["python","pandas","scikit_learn","sql","tableau"], "Data scientist, churn and pricing models"),
  ("ML Engineer CV", 3, 5, ["python","pytorch","computer_vision","docker","mlflow"], "ML engineer, computer vision in production"),
  ("ML LLM engineer", 2, 2.5, ["python","llm","langchain","huggingface","fastapi"], "LLM application engineer, RAG systems"),
  ("Data Engineer Spark", 3, 5, ["spark","airflow","python","aws","sql"], "Data engineer, batch pipelines on Spark"),
  ("Analytics/BI", 2, 3, ["sql","powerbi","dbt","excel"], "BI analyst building dashboards"),
  ("Mobile Android", 2, 4, ["android","kotlin","rest_api"], "Android developer, Kotlin"),
  ("Mobile iOS senior", 3, 6, ["ios","swift","rest_api"], "Senior iOS engineer"),
  ("Mobile React Native", 2, 3, ["react_native","javascript","redux","rest_api"], "React Native mobile developer"),
  ("QA Automation", 2, 4, ["selenium","cypress","api_testing","python"], "QA automation engineer"),
  ("QA Manual junior", 1, 1, ["manual_testing","postman","jira","sql"], "Junior manual tester"),
  ("Security/SecOps", 3, 5, ["cybersecurity","siem","linux","python","soc"], "Security operations engineer"),
  ("UI/UX Designer", 2, 4, ["figma","html_css"], "UI/UX product designer for web and mobile"),
  ("Business Analyst", 2, 4, ["jira","confluence","sql","excel"], "Business analyst, requirements for fintech products"),
  ("Embedded C", 2, 4, ["c","cpp","linux","python"], "Embedded software engineer, firmware"),
  ("Intern CS", 0, 0, ["python","sql","git","java"], "Final-year CS student seeking internship"),
]

hits, rates = 0, []
for role, sen, exp, skills, text in CVS:
    res = match_cv_data(skills=skills, seniority=sen, experience_years=exp, text=text, top_k=5)
    jobs = res.get("jobs", [])
    flags = [1 if ((j.get("dim_scores") or {}).get("domain_fit", 0) or 0) >= 0.5 else 0 for j in jobs]
    hits += bool(flags and flags[0])
    rates.append(sum(flags) / len(flags) if flags else 0)
print(f"SUMMARY-30: top1_on_domain = {hits}/30 ({hits*100//30}%) · mean on_domain@5 = {sum(rates)/len(rates):.2f}")
