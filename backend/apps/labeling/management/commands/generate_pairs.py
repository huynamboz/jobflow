"""
Management command: generate_pairs

Sources:
  - CV data   : CV model + CVSkill (post CV-extraction)
  - Job data  : JDExtractionRecord.result (LLM-cleaned, not raw Job model)

Usage:
    python manage.py generate_pairs
    python manage.py generate_pairs --n-pairs 3500 --max-per-cv 12 --clear
"""

import random
from collections import defaultdict

from django.core.management.base import BaseCommand

DEV_ROLES = {
    "backend", "frontend", "fullstack", "mobile",
    "devops", "data_ml", "data_eng", "qa", "design",
}

_TITLE_ROLE_RULES: list[tuple[list[str], str]] = [
    (["full stack", "full-stack", "fullstack"],                                                   "fullstack"),
    (["react native", "flutter", "android", "ios ", "mobile"],                                   "mobile"),
    (["frontend", "front-end", "front end", "ui developer", "vue", "angular", "react developer", "reactjs"], "frontend"),
    (["backend", "back-end", "back end", "api developer", "django", "flask", "spring boot",
      "laravel", "rails", "golang developer", "java developer", "php developer"],                 "backend"),
    (["machine learning", "ml engineer", "ai engineer", "data scientist", "deep learning",
      "nlp engineer", "computer vision", "llm"],                                                  "data_ml"),
    (["data engineer", "data pipeline", "etl ", "spark ", "airflow", "bigquery",
      "data warehouse", "analytics engineer"],                                                     "data_eng"),
    (["devops", "dev-ops", "sre", "site reliability", "cloud engineer", "platform engineer",
      "kubernetes", "devsecops", "infrastructure engineer"],                                       "devops"),
    (["qa ", "quality assurance", "test engineer", "automation test", "tester", "software test"], "qa"),
    (["ux designer", "ui designer", "ux/ui", "product designer", "visual designer", "ui/ux"],    "design"),
    (["business analyst", "business intelligence", "product owner", "product manager",
      "scrum master", "agile coach"],                                                              "ba"),
    (["software engineer", "software developer", "web developer", "web engineer"],                "backend"),
]

# Broader keywords used only as fallback on combined_text (not title-matching)
_TEXT_ROLE_RULES: list[tuple[list[str], str]] = [
    (["react native", "flutter", "android", "ios developer", "mobile developer"],                "mobile"),
    (["reactjs", "react.js", "vuejs", "vue.js", "angular", "next.js", "nuxt",
      "frontend developer", "front-end developer"],                                               "frontend"),
    (["nodejs", "node.js", "expressjs", "express.js", "django", "flask", "fastapi",
      "spring boot", "laravel", "nestjs", "backend developer", "back-end developer"],            "backend"),
    (["machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn",
      "data scientist", "ml engineer", "ai engineer"],                                            "data_ml"),
    (["apache spark", "apache airflow", "data pipeline", "etl developer",
      "data warehouse", "bigquery", "snowflake", "data engineer"],                               "data_eng"),
    (["kubernetes", "docker swarm", "terraform", "ansible", "ci/cd pipeline",
      "devops engineer", "site reliability", "cloud infrastructure"],                             "devops"),
    (["test automation", "selenium", "cypress", "playwright", "qa engineer",
      "quality assurance engineer", "software tester"],                                           "qa"),
    (["ux research", "user experience design", "figma", "sketch", "product designer",
      "ui/ux designer"],                                                                          "design"),
]


def _infer_role(title: str, fallback_text: str = "") -> str:
    t = title.lower()
    for keywords, role in _TITLE_ROLE_RULES:
        if any(kw in t for kw in keywords):
            return role
    # Fallback: scan first 400 chars of combined_text with broader keywords
    if fallback_text:
        fb = fallback_text[:400].lower()
        for keywords, role in _TEXT_ROLE_RULES:
            if any(kw in fb for kw in keywords):
                return role
    return "other"


RELATED_ROLES: dict[str, set[str]] = {
    "backend":   {"fullstack"},
    "frontend":  {"fullstack"},
    "fullstack": {"backend", "frontend"},
    "data_ml":   {"data_eng"},
    "data_eng":  {"data_ml"},
}

SENIORITY_LABELS = {0: "INTERN", 1: "JUNIOR", 2: "MID", 3: "SENIOR", 4: "LEAD", 5: "MANAGER"}
EDUCATION_LABELS = {0: "NONE", 1: "COLLEGE", 2: "BACHELOR", 3: "MASTER", 4: "PHD"}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _same_or_related(a: str, b: str) -> bool:
    return a == b or b in RELATED_ROLES.get(a, set())


class Command(BaseCommand):
    help = "Generate CV-Job pairs from extracted data for LLM labeling"

    def add_arguments(self, parser):
        parser.add_argument("--n-pairs",        type=int,  default=3500)
        parser.add_argument("--max-per-cv",     type=int,  default=12)
        parser.add_argument("--min-cv-skills",  type=int,  default=3)
        parser.add_argument("--min-job-skills", type=int,  default=3)
        parser.add_argument("--seed",           type=int,  default=42)
        parser.add_argument("--clear",          action="store_true")
        parser.add_argument("--dev-roles-only", action="store_true")

    def handle(self, *args, **options):
        from apps.cvs.models import CV, CVSkill
        from apps.jobs.models import JDExtractionRecord
        from apps.labeling.models import (
            LabelingCV, LabelingJob, PairQueue,
            SelectionReason, REASON_PRIORITY,
        )

        random.seed(options["seed"])

        if options["clear"]:
            self.stdout.write("Clearing PairQueue, LabelingCV, LabelingJob...")
            PairQueue.objects.all().delete()
            LabelingCV.objects.all().delete()
            LabelingJob.objects.all().delete()

        # ── CVs (from CV model + CVSkill) ────────────────────────────────────
        self.stdout.write("Loading CVs...")
        cv_qs = CV.objects.filter(is_active=True)
        if options.get("dev_roles_only"):
            cv_qs = cv_qs.filter(role_category__in=DEV_ROLES)

        cv_skill_map: dict[int, list[dict]] = defaultdict(list)
        for cs in CVSkill.objects.filter(cv__in=cv_qs).select_related("skill"):
            cv_skill_map[cs.cv_id].append({"name": cs.skill.canonical_name, "proficiency": cs.proficiency})

        min_cv = options["min_cv_skills"]
        cvs = [cv for cv in cv_qs if len(cv_skill_map[cv.id]) >= min_cv]
        self.stdout.write(f"  {len(cvs)} CVs with ≥{min_cv} skills")

        cv_skill_sets: dict[int, set[str]] = {
            cv.id: {s["name"].lower() for s in cv_skill_map[cv.id]} for cv in cvs
        }

        # ── Jobs (from JDExtractionRecord.result) ────────────────────────────
        self.stdout.write("Loading jobs from JDExtractionRecord...")
        min_job = options["min_job_skills"]

        # rec_id → (title, role, seniority_str, exp_min, exp_max, skills, salary_min, salary_max, text)
        class _JobData:
            __slots__ = ("rec_id", "title", "role", "seniority", "exp_min", "exp_max",
                         "salary_min", "salary_max", "skills", "text")

        job_list: list[_JobData] = []
        for rec in (
            JDExtractionRecord.objects
            .filter(status=JDExtractionRecord.STATUS_DONE)
            .exclude(result=None)
            .only("id", "result", "combined_text")
        ):
            r = rec.result or {}
            skills = r.get("skills") or []
            if len(skills) < min_job:
                continue

            jd = _JobData()
            jd.rec_id     = rec.id
            jd.title      = (r.get("title") or "")[:200]
            jd.role       = _infer_role(jd.title, rec.combined_text or "")
            seniority_raw = r.get("seniority")
            jd.seniority  = SENIORITY_LABELS.get(seniority_raw if isinstance(seniority_raw, int) else 2, "MID")
            jd.exp_min    = float(r.get("experience_min") or 0)
            exp_max_raw   = r.get("experience_max")
            jd.exp_max    = float(exp_max_raw) if exp_max_raw is not None else None
            jd.salary_min = r.get("salary_min")
            jd.salary_max = r.get("salary_max")
            jd.skills     = skills   # [{name, importance}]
            jd.text       = (rec.combined_text or "")[:600]
            job_list.append(jd)

        self.stdout.write(f"  {len(job_list)} extracted JDs with ≥{min_job} skills")
        roles_ok = sum(1 for j in job_list if j.role != "other")
        self.stdout.write(f"  role inferred for {roles_ok}/{len(job_list)} ({roles_ok*100//max(len(job_list),1)}%)")

        job_skill_sets: dict[int, set[str]] = {
            j.rec_id: {s["name"].lower() for s in j.skills} for j in job_list
        }

        # ── Upsert LabelingCV ─────────────────────────────────────────────────
        self.stdout.write("Upserting LabelingCV...")
        cv_objs: dict[int, LabelingCV] = {}
        for cv in cvs:
            obj, _ = LabelingCV.objects.update_or_create(
                cv_id=cv.id,
                defaults=dict(
                    source=cv.source or "dataset",
                    role_category=cv.role_category or "other",
                    skills=cv_skill_map[cv.id],
                    seniority=SENIORITY_LABELS.get(cv.seniority, "MID"),
                    experience_years=cv.experience_years,
                    education=EDUCATION_LABELS.get(cv.education, "BACHELOR"),
                    text_summary=(cv.parsed_text or cv.raw_text or "")[:600],
                ),
            )
            cv_objs[cv.id] = obj

        # ── Upsert LabelingJob (keyed by JDExtractionRecord.id) ───────────────
        self.stdout.write("Upserting LabelingJob...")
        job_objs: dict[int, LabelingJob] = {}
        for jd in job_list:
            obj, _ = LabelingJob.objects.update_or_create(
                job_id=jd.rec_id,
                defaults=dict(
                    title=jd.title,
                    role_category=jd.role,
                    skills=jd.skills,
                    seniority=jd.seniority,
                    experience_min=jd.exp_min,
                    experience_max=jd.exp_max,
                    salary_min=jd.salary_min,
                    salary_max=jd.salary_max,
                    text_summary=jd.text,
                ),
            )
            job_objs[jd.rec_id] = obj

        # ── Compute overlaps + bucket ─────────────────────────────────────────
        self.stdout.write("Computing skill overlaps...")
        n_pairs    = options["n_pairs"]
        max_per_cv = options["max_per_cv"]

        buckets: dict[str, list] = {r: [] for r in SelectionReason.values}
        cv_pair_count: dict[int, int] = defaultdict(int)

        for cv in cvs:
            cv_skills = cv_skill_sets[cv.id]
            cv_role   = cv.role_category or "other"
            for jd in job_list:
                if cv_pair_count[cv.id] >= max_per_cv:
                    break
                job_skills = job_skill_sets[jd.rec_id]
                overlap    = _jaccard(cv_skills, job_skills)
                compatible = _same_or_related(cv_role, jd.role)

                if compatible:
                    if overlap >= 0.20:
                        reason = SelectionReason.HIGH_OVERLAP
                    elif overlap >= 0.08:
                        reason = SelectionReason.MEDIUM_OVERLAP
                    else:
                        reason = SelectionReason.HARD_NEGATIVE
                else:
                    reason = SelectionReason.RANDOM

                buckets[reason].append((cv.id, jd.rec_id, overlap, reason))
                cv_pair_count[cv.id] += 1

        for bucket in buckets.values():
            random.shuffle(bucket)

        for reason, items in buckets.items():
            self.stdout.write(f"  {reason}: {len(items):,} candidates")

        # ── Sample by ratio ───────────────────────────────────────────────────
        ratios = {
            SelectionReason.HIGH_OVERLAP:   0.30,
            SelectionReason.MEDIUM_OVERLAP: 0.40,
            SelectionReason.HARD_NEGATIVE:  0.20,
            SelectionReason.RANDOM:         0.10,
        }
        selected: list[tuple] = []
        for reason, ratio in ratios.items():
            selected.extend(buckets[reason][:int(n_pairs * ratio)])

        if len(selected) < n_pairs:
            needed = n_pairs - len(selected)
            used = {(cv_id, job_id) for cv_id, job_id, _, _ in selected}
            for reason in ratios:
                for item in buckets[reason]:
                    if needed <= 0:
                        break
                    if (item[0], item[1]) not in used:
                        selected.append(item)
                        used.add((item[0], item[1]))
                        needed -= 1

        random.shuffle(selected)
        self.stdout.write(f"Selected {len(selected):,} pairs total")

        # ── Assign splits (70/15/15) ──────────────────────────────────────────
        split_assigned = []
        for cv_id, job_id, overlap, reason in selected:
            r = random.random()
            split = "train" if r < 0.70 else ("val" if r < 0.85 else "test")
            split_assigned.append((cv_id, job_id, overlap, reason, split))

        # ── Bulk insert PairQueue ─────────────────────────────────────────────
        self.stdout.write("Inserting PairQueue...")
        existing = set(PairQueue.objects.values_list("cv__cv_id", "job__job_id"))
        to_create = [
            PairQueue(
                cv=cv_objs[cv_id],
                job=job_objs[job_id],
                skill_overlap_score=round(overlap, 4),
                selection_reason=reason,
                priority=REASON_PRIORITY[reason],
                split=split,
            )
            for cv_id, job_id, overlap, reason, split in split_assigned
            if (cv_id, job_id) not in existing
        ]
        PairQueue.objects.bulk_create(to_create, ignore_conflicts=True)

        total   = PairQueue.objects.count()
        pending = PairQueue.objects.filter(status="pending").count()
        self.stdout.write(self.style.SUCCESS(
            f"\nDone! PairQueue: {total:,} total, {pending:,} pending "
            f"({PairQueue.objects.filter(split='train').count():,} train / "
            f"{PairQueue.objects.filter(split='val').count():,} val / "
            f"{PairQueue.objects.filter(split='test').count():,} test)"
        ))
