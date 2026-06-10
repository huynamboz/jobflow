"""Tests for feature 018 — inductive live-catalog job pool."""

import shutil
import tempfile
from pathlib import Path

import numpy as np
import torch
from django.test import TestCase


class BuildJobDataTests(TestCase):
    """build_jobdata_from_db maps Job + JobSkill → JobData."""

    def _skill(self, name):
        from apps.skills.models import Skill
        return Skill.objects.create(canonical_name=name)

    def test_maps_job_skills_importances_and_text(self):
        from apps.jobs.models import Job, JobSkill
        from apps.matching.services.matching_service import build_jobdata_from_db

        job = Job.objects.create(
            title="Backend Dev", description="Build APIs", seniority=3,
            salary_min=100, salary_max=200, role_category="backend", is_active=True,
        )
        JobSkill.objects.create(job=job, skill=self._skill("python"), importance=5)
        JobSkill.objects.create(job=job, skill=self._skill("django"), importance=3)

        jds = build_jobdata_from_db()
        self.assertEqual(len(jds), 1)
        jd = jds[0]
        self.assertEqual(jd.job_id, job.id)  # id space == Job.id
        self.assertEqual(dict(zip(jd.skills, jd.skill_importances)), {"python": 5, "django": 3})
        self.assertIn("Backend Dev", jd.text)
        self.assertIn("Build APIs", jd.text)
        self.assertEqual(int(jd.seniority), 3)
        self.assertEqual(jd.role_category, "backend")

    def test_excludes_skill_less_and_inactive(self):
        from apps.jobs.models import Job, JobSkill
        from apps.matching.services.matching_service import build_jobdata_from_db

        no_skill = Job.objects.create(title="A", description="x", is_active=True)
        inactive = Job.objects.create(title="B", description="x", is_active=False)
        JobSkill.objects.create(job=inactive, skill=self._skill("go"), importance=4)

        ids = {jd.job_id for jd in build_jobdata_from_db()}
        self.assertNotIn(no_skill.id, ids)   # no skills → excluded
        self.assertNotIn(inactive.id, ids)   # inactive → excluded


class JobPoolSnapshotTests(TestCase):
    """Atomic save/load + model-signature gating + length invariant."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "job_pool"

    def tearDown(self):
        shutil.rmtree(self.dir.parent, ignore_errors=True)

    def _jobs(self, n=2):
        from ml_service.graph.schema import JobData, SeniorityLevel
        return [
            JobData(job_id=i + 1, seniority=SeniorityLevel(2), skills=("python",),
                    skill_importances=(5,), salary_min=0, salary_max=0, text=f"job {i}",
                    role_category="backend")
            for i in range(n)
        ]

    def test_roundtrip(self):
        from ml_service.inference import job_pool_snapshot
        emb = torch.randn(3, 8)
        tv = np.random.rand(3, 384).astype("float32")
        job_pool_snapshot.save(self.dir, self._jobs(3), emb, tv, "sig-A", skill_skipped_edges=2)

        loaded = job_pool_snapshot.load(self.dir, "sig-A")
        self.assertIsNotNone(loaded)
        ljobs, lemb, ltv = loaded
        self.assertEqual([j.job_id for j in ljobs], [1, 2, 3])
        self.assertEqual(tuple(lemb.shape), (3, 8))
        self.assertEqual(ltv.shape, (3, 384))

    def test_model_sig_mismatch_returns_none(self):
        from ml_service.inference import job_pool_snapshot
        job_pool_snapshot.save(self.dir, self._jobs(1), torch.randn(1, 8),
                               np.random.rand(1, 384).astype("float32"), "sig-A")
        self.assertIsNone(job_pool_snapshot.load(self.dir, "sig-B"))

    def test_missing_snapshot_returns_none(self):
        from ml_service.inference import job_pool_snapshot
        self.assertIsNone(job_pool_snapshot.load(self.dir / "nope", "sig-A"))

    def test_length_mismatch_rejected_on_save(self):
        from ml_service.inference import job_pool_snapshot
        with self.assertRaises(ValueError):
            job_pool_snapshot.save(self.dir, self._jobs(2), torch.randn(1, 8),
                                   np.random.rand(2, 384).astype("float32"), "sig-A")
