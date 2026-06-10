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
        # Feature 022: decision-boundary bucket mode (master plan Đợt 1)
        parser.add_argument("--buckets",    action="store_true",
                            help="Generate the 022 decision-boundary buckets instead of legacy ratios.")
        parser.add_argument("--per-cv-cap", type=int, default=30,
                            help="[--buckets] max pairs per CV per bucket.")
        parser.add_argument("--dry-run",    action="store_true",
                            help="[--buckets] print the per-bucket plan, write nothing.")

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
            __slots__ = ("rec_id", "title", "role", "seniority", "sen_int", "exp_min", "exp_max",
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
            jd.sen_int    = seniority_raw if isinstance(seniority_raw, int) else 2
            jd.seniority  = SENIORITY_LABELS.get(jd.sen_int, "MID")
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

        # ── Feature 022: decision-boundary bucket mode ───────────────────────
        if options["buckets"]:
            existing = set(PairQueue.objects.values_list("cv__cv_id", "job__job_id"))
            split_assigned = self._bucket_pairs(
                options, cvs, cv_skill_sets, job_list, job_skill_sets, existing,
            )
            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("--dry-run: nothing written."))
                return
            self.stdout.write("Inserting PairQueue (buckets)...")
            to_create = [
                PairQueue(
                    cv=cv_objs[cv_id], job=job_objs[job_id],
                    skill_overlap_score=round(overlap, 4),
                    selection_reason=reason, priority=REASON_PRIORITY[reason],
                    split=split,
                )
                for cv_id, job_id, overlap, reason, split in split_assigned
                if (cv_id, job_id) not in existing
            ]
            PairQueue.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f"Created {len(to_create):,} bucket pairs."))
            return

        # ── Compute overlaps + bucket ─────────────────────────────────────────
        # Compatible pairs (HIGH/MEDIUM/HARD_NEG) are collected WITHOUT a per-CV
        # cap so high-overlap pairs aren't missed due to iteration order.
        # RANDOM (incompatible role) pairs are capped at max_per_cv per CV.
        self.stdout.write("Computing skill overlaps...")
        n_pairs    = options["n_pairs"]
        max_per_cv = options["max_per_cv"]

        buckets: dict[str, list] = {r: [] for r in SelectionReason.values}

        for cv in cvs:
            cv_skills = cv_skill_sets[cv.id]
            cv_role   = cv.role_category or "other"

            compatible_pairs: list[tuple] = []
            random_candidates: list[tuple] = []

            for jd in job_list:
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
                    compatible_pairs.append((cv.id, jd.rec_id, overlap, reason))
                else:
                    random_candidates.append((cv.id, jd.rec_id, overlap, SelectionReason.RANDOM))

            # All compatible pairs go in — no per-CV cap (they are the signal)
            for item in compatible_pairs:
                buckets[item[3]].append(item)

            # Random (incompatible) pairs capped at max_per_cv per CV
            random.shuffle(random_candidates)
            for item in random_candidates[:max_per_cv]:
                buckets[SelectionReason.RANDOM].append(item)

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

    # ── Feature 022: decision-boundary buckets ────────────────────────────────
    def _build_expansion_map(self, all_names: list[str]) -> dict[str, set[str]]:
        """name → related names, via SKILL_CLUSTERS co-membership + semantic
        similarity (cosine ≥ 0.7 on the embedding provider, max 5/skill)."""
        from ml_service.data.skill_taxonomy import SKILL_CLUSTERS

        expand: dict[str, set[str]] = {n: set() for n in all_names}
        name_set = set(all_names)
        for members in SKILL_CLUSTERS.values():
            present = [m for m in members if m in name_set]
            for m in present:
                expand[m].update(x for x in present if x != m)

        try:
            import numpy as np
            from ml_service.embedding import get_provider
            vecs = get_provider().encode(all_names)
            sims = vecs @ vecs.T
            for i, n in enumerate(all_names):
                order = np.argsort(-sims[i])
                added = 0
                for j in order:
                    if j == i or added >= 5:
                        continue
                    if sims[i, j] < 0.70:
                        break
                    expand[n].add(all_names[j])
                    added += 1
        except Exception as e:  # noqa: BLE001 — clusters alone still useful
            self.stdout.write(self.style.WARNING(f"semantic expansion skipped: {e}"))
        return expand

    def _bucket_pairs(self, options, cvs, cv_skill_sets, job_list, job_skill_sets, existing):
        """Return [(cv_id, job_id, overlap, reason, split)] for the 022 buckets."""
        from apps.labeling.models import SelectionReason as SR

        n_pairs = options["n_pairs"]
        cap     = options["per_cv_cap"]
        quotas = {
            SR.CROSS_DOMAIN_HARD_NEG:  int(n_pairs * 0.32),
            SR.RELATED_SKILL_POSITIVE: int(n_pairs * 0.20),
            SR.SENIORITY_HARD_NEG:     int(n_pairs * 0.13),
            SR.MISSING_MUST_HAVE:      int(n_pairs * 0.10),
            SR.BOUNDARY_MEDIUM:        int(n_pairs * 0.15),
            SR.HIGH_OVERLAP:           int(n_pairs * 0.05),  # positive top-up
            SR.RANDOM:                 int(n_pairs * 0.05),  # scale anchor
        }

        self.stdout.write("Building skill expansion map (clusters + semantic)...")
        all_names = sorted({s for ss in cv_skill_sets.values() for s in ss}
                           | {s for ss in job_skill_sets.values() for s in ss})
        expand = self._build_expansion_map(all_names)

        must_have_map = {  # job → required (importance ≥ 4) skill names
            jd.rec_id: {(s.get("name") or "").lower() for s in jd.skills
                        if (s.get("importance") or 3) >= 4}
            for jd in job_list
        }

        self.stdout.write("Scanning CV×job space for bucket candidates...")
        cands: dict[str, list[tuple]] = {r: [] for r in quotas}
        for cv in cvs:
            cv_skills = cv_skill_sets[cv.id]
            cv_role   = cv.role_category or "other"
            cv_sen    = int(cv.seniority)
            expanded  = set(cv_skills)
            for s in cv_skills:
                expanded |= expand.get(s, set())

            for jd in job_list:
                if (cv.id, jd.rec_id) in existing:
                    continue
                job_skills = job_skill_sets[jd.rec_id]
                j          = _jaccard(cv_skills, job_skills)
                same       = cv_role == jd.role
                compatible = _same_or_related(cv_role, jd.role)
                dsen       = abs(cv_sen - jd.sen_int)

                if j >= 0.15 and not compatible:
                    cands[SR.CROSS_DOMAIN_HARD_NEG].append((cv.id, jd.rec_id, j, cv_role))
                elif same and j < 0.15 and dsen <= 1 and job_skills:
                    exp_cov = len(expanded & job_skills) / len(job_skills)
                    if exp_cov >= 0.5:
                        cands[SR.RELATED_SKILL_POSITIVE].append((cv.id, jd.rec_id, j, cv_role))
                elif same and j >= 0.2 and dsen >= 2:
                    cands[SR.SENIORITY_HARD_NEG].append((cv.id, jd.rec_id, j, cv_role))
                elif same and 0.15 <= j < 0.5 and len(must_have_map[jd.rec_id] - cv_skills) >= 2:
                    cands[SR.MISSING_MUST_HAVE].append((cv.id, jd.rec_id, j, cv_role))
                elif compatible and 0.08 <= j < 0.2:
                    cands[SR.BOUNDARY_MEDIUM].append((cv.id, jd.rec_id, j, cv_role))
                elif same and j >= 0.25 and dsen <= 1:
                    cands[SR.HIGH_OVERLAP].append((cv.id, jd.rec_id, j, cv_role))
                elif not compatible and j < 0.05:
                    cands[SR.RANDOM].append((cv.id, jd.rec_id, j, cv_role))

        # Sample: role round-robin + per-CV cap → quota; split stratified per bucket
        out: list[tuple] = []
        self.stdout.write(f"{'bucket':26} {'cands':>8} {'quota':>6} {'taken':>6} shortfall")
        for reason, quota in quotas.items():
            pool = cands[reason]
            random.shuffle(pool)
            by_role: dict[str, list] = defaultdict(list)
            for item in pool:
                by_role[item[3]].append(item)
            taken, per_cv = [], defaultdict(int)
            role_lists = list(by_role.values())
            i = 0
            while len(taken) < quota and any(role_lists):
                lst = role_lists[i % len(role_lists)]
                i += 1
                while lst:
                    cv_id, job_id, j, _role = lst.pop()
                    if per_cv[(reason, cv_id)] >= cap:
                        continue
                    per_cv[(reason, cv_id)] += 1
                    taken.append((cv_id, job_id, j))
                    break
                role_lists = [l for l in role_lists if l]
                if not role_lists:
                    break
            shortfall = quota - len(taken)
            self.stdout.write(f"{reason:26} {len(pool):>8,} {quota:>6} {len(taken):>6} "
                              f"{shortfall if shortfall > 0 else '-'}")
            random.shuffle(taken)
            n = len(taken)
            for k, (cv_id, job_id, j) in enumerate(taken):
                split = "train" if k < n * 0.70 else ("val" if k < n * 0.85 else "test")
                out.append((cv_id, job_id, j, reason, split))

        self.stdout.write(f"Total bucket pairs: {len(out):,}")
        return out
