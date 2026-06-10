"""Tests for feature 022 — decision-boundary bucket generation + agent labeling."""

from unittest.mock import patch

from django.test import TestCase


def _mk_cv(role, seniority, skills, exp=3.0):
    from apps.cvs.models import CV, CVSkill
    from apps.skills.models import Skill

    cv = CV.objects.create(role_category=role, seniority=seniority,
                           experience_years=exp, is_active=True,
                           raw_text=f"{role} dev " * 10)
    for name in skills:
        skill, _ = Skill.objects.get_or_create(canonical_name=name)
        CVSkill.objects.create(cv=cv, skill=skill, proficiency=3)
    return cv


def _mk_job(batch, title, seniority, skills, text="job description " * 10):
    from apps.jobs.models import JDExtractionRecord

    return JDExtractionRecord.objects.create(
        batch=batch, index=JDExtractionRecord.objects.count(),
        combined_text=f"{title}. {text}", status=JDExtractionRecord.STATUS_DONE,
        result={"title": title, "seniority": seniority,
                "skills": [{"name": n, "importance": imp} for n, imp in skills]},
    )


FAKE_EXPANSION = {  # flask≈django, mysql≈postgresql — test không cần embeddings
    "flask": {"django"}, "django": {"flask"},
    "mysql": {"postgresql"}, "postgresql": {"mysql"},
}


class BucketGenerationTests(TestCase):
    """022/1.1: bucket conditions, dedup, stratified split."""

    def setUp(self):
        from apps.jobs.models import JDExtractionBatch
        self.batch = JDExtractionBatch.objects.create(file_path="t.csv")
        # CV1 backend MID: python/django/postgresql
        self.cv1 = _mk_cv("backend", 2, ["python", "django", "postgresql"])
        # CV2 backend MID: flask/celery/mysql (related-skill candidate)
        self.cv2 = _mk_cv("backend", 2, ["flask", "celery", "mysql"])
        # Jobs
        self.vfx = _mk_job(self.batch, "Senior Compositor", 2,
                           [("python", 4), ("nuke", 5), ("maya", 3)])      # role→other
        self.django_job = _mk_job(self.batch, "Django Developer", 2,
                                  [("django", 5), ("postgresql", 4), ("jenkins", 3)])
        self.lead_job = _mk_job(self.batch, "Lead Backend Engineer", 4,
                                [("python", 5), ("django", 4), ("postgresql", 4)])

    def _run(self):
        from django.core.management import call_command
        with patch("apps.labeling.management.commands.generate_pairs.Command._build_expansion_map",
                   return_value={k: set(v) for k, v in FAKE_EXPANSION.items()}):
            call_command("generate_pairs", "--buckets", "--n-pairs", "60", "--seed", "1")

    def _reason(self, cv, job_rec):
        from apps.labeling.models import PairQueue
        row = PairQueue.objects.filter(cv__cv_id=cv.id, job__job_id=job_rec.id).first()
        return row.selection_reason if row else None

    def test_bucket_conditions(self):
        self._run()
        # CV1 (backend) × VFX job sharing python → cross-domain hard negative
        self.assertEqual(self._reason(self.cv1, self.vfx), "cross_domain_hard_neg")
        # CV2 (flask/mysql) × Django job: direct J=0 but expanded covers 2/3 → related-skill
        self.assertEqual(self._reason(self.cv2, self.django_job), "related_skill_positive")
        # CV1 MID × Lead job (Δsen=2, J cao) → seniority hard negative
        self.assertEqual(self._reason(self.cv1, self.lead_job), "seniority_hard_neg")

    def test_dedup_idempotent(self):
        from apps.labeling.models import PairQueue
        self._run()
        n1 = PairQueue.objects.count()
        self._run()  # chạy lại — không tạo trùng
        self.assertEqual(PairQueue.objects.count(), n1)


class ExportImportTests(TestCase):
    """022/1.2: export chunks + import validation/idempotency."""

    def setUp(self):
        import json
        from django.core.management import call_command
        from apps.jobs.models import JDExtractionBatch
        from apps.labeling.models import PairQueue

        self.batch = JDExtractionBatch.objects.create(file_path="t.csv")
        cv = _mk_cv("backend", 2, ["python", "django", "redis"])
        job = _mk_job(self.batch, "Backend Developer", 2, [("python", 5), ("django", 4), ("docker", 3)])
        with patch("apps.labeling.management.commands.generate_pairs.Command._build_expansion_map",
                   return_value={}):
            call_command("generate_pairs", "--buckets", "--n-pairs", "20", "--seed", "1")
        self.pair = PairQueue.objects.first()
        self.assertIsNotNone(self.pair)

    def test_export_then_import_roundtrip(self):
        import json, tempfile
        from pathlib import Path
        from django.core.management import call_command
        from apps.labeling.models import HumanLabel, PairQueue

        with tempfile.TemporaryDirectory() as d:
            call_command("export_pending_pairs", "--out", d, "--chunk-size", "5")
            chunks = sorted(Path(d).glob("chunk_*.jsonl"))
            self.assertTrue(chunks)
            row = json.loads(chunks[0].read_text().splitlines()[0])
            for key in ("pair_id", "bucket", "cv", "job"):
                self.assertIn(key, row)

            labels = Path(d) / "labels.jsonl"
            labels.write_text(json.dumps({
                "pair_id": row["pair_id"], "skill_fit": 2, "seniority_fit": 2,
                "experience_fit": 2, "domain_fit": 0, "overall": 0}) + "\n")
            call_command("import_labels", "--in", str(labels))

            hl = HumanLabel.objects.get(pair_id=row["pair_id"])
            self.assertEqual(hl.note, "claude-labeled")
            self.assertEqual(hl.overall, 0)
            self.assertEqual(PairQueue.objects.get(id=row["pair_id"]).status, "labeled")

    def test_import_rejects_bad_scores_atomically(self):
        import json, tempfile
        from pathlib import Path
        from django.core.management import CommandError, call_command
        from apps.labeling.models import HumanLabel

        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.jsonl"
            bad.write_text(json.dumps({
                "pair_id": self.pair.id, "skill_fit": 5, "seniority_fit": 2,
                "experience_fit": 2, "domain_fit": 0, "overall": 0}) + "\n")
            with self.assertRaises(CommandError):
                call_command("import_labels", "--in", str(bad))
            self.assertEqual(HumanLabel.objects.count(), 0)  # atomic: nothing written
