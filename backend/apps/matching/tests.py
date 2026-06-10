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


class DomainAwareTests(TestCase):
    """Feature 020: domain term + role-aware tuning metric."""

    def _job(self, role=""):
        from ml_service.graph.schema import JobData, SeniorityLevel
        return JobData(job_id=1, seniority=SeniorityLevel(2), skills=("python",),
                       skill_importances=(5,), salary_min=0, salary_max=0, text="job",
                       experience_min=0.0, role_category=role)

    def test_role_domain_fit(self):
        from ml_service.inference.engine import InferenceEngine
        f = InferenceEngine._role_domain_fit
        self.assertEqual(f("frontend", self._job("frontend")), 1.0)   # same field
        self.assertEqual(f("frontend", self._job("backend")), 0.0)    # mismatch
        self.assertEqual(f("frontend", self._job("")), 0.5)           # job role unknown → neutral

    def test_simplex4_sums_to_one_and_includes_chosen(self):
        from apps.matching.management.commands.tune_hybrid_weights import Command
        combos = Command._simplex4(0.05)
        for a, b, g, d in combos:
            self.assertAlmostEqual(a + b + g + d, 1.0, places=6)
        self.assertIn((0.10, 0.25, 0.25, 0.40), [tuple(round(x, 2) for x in c) for c in combos])

    def test_role_metrics_rewards_relevant_on_top(self):
        from apps.matching.management.commands.tune_hybrid_weights import Command
        cv_idx = np.array([0, 0, 0])
        rel = np.array([1, 0, 1])
        good = np.array([0.9, 0.1, 0.8])   # relevant ranked high → NDCG high
        bad = np.array([0.1, 0.9, 0.2])    # relevant ranked low → NDCG lower
        ndcg_good, _ = Command._role_metrics(cv_idx, rel, good, 10)
        ndcg_bad, _ = Command._role_metrics(cv_idx, rel, bad, 10)
        self.assertGreater(ndcg_good, ndcg_bad)
        self.assertAlmostEqual(ndcg_good, 1.0, places=6)


class DimensionScoreTests(TestCase):
    """Feature 019: transparent per-dimension fit formulas (hand-reproducible)."""

    def _cv(self, skills=("python",), seniority=2, exp=3.0, text="python developer"):
        from ml_service.graph.schema import CVData, EducationLevel, SeniorityLevel
        return CVData(cv_id=-1, seniority=SeniorityLevel(seniority), experience_years=exp,
                      education=EducationLevel(2), skills=tuple(skills),
                      skill_proficiencies=tuple(3 for _ in skills), text=text)

    def _job(self, skills=("python",), imps=(5,), seniority=2, exp_min=0.0, role=""):
        from ml_service.graph.schema import JobData, SeniorityLevel
        return JobData(job_id=1, seniority=SeniorityLevel(seniority), skills=tuple(skills),
                       skill_importances=tuple(imps), salary_min=0, salary_max=0,
                       text="job", experience_min=exp_min, role_category=role)

    def _dim(self, cv, job, matched):
        from ml_service.inference.engine import InferenceEngine
        return InferenceEngine._dimension_scores(cv, job, set(matched))

    def test_skill_fit_is_importance_weighted(self):
        cv = self._cv(skills=("python",))
        job = self._job(skills=("python", "django"), imps=(5, 3))  # total imp 8
        d = self._dim(cv, job, {"python"})
        self.assertAlmostEqual(d["skill_fit"], 5 / 8, places=3)   # 0.625, not 1/2

    def test_skill_fit_no_required_is_full(self):
        d = self._dim(self._cv(), self._job(skills=(), imps=()), set())
        self.assertEqual(d["skill_fit"], 1.0)

    def test_seniority_fit_decays_with_distance(self):
        cv = self._cv(seniority=2)
        self.assertEqual(self._dim(cv, self._job(seniority=2), {"python"})["seniority_fit"], 1.0)
        self.assertAlmostEqual(self._dim(cv, self._job(seniority=3), {"python"})["seniority_fit"], 0.7, places=3)
        self.assertAlmostEqual(self._dim(cv, self._job(seniority=4), {"python"})["seniority_fit"], 0.4, places=3)

    def test_experience_fit_penalizes_deficit_neutral_when_unknown(self):
        # job needs 5y, cv has 2y → deficit 3 → 1 - 3/5 = 0.4
        d = self._dim(self._cv(exp=2.0), self._job(exp_min=5.0), {"python"})
        self.assertAlmostEqual(d["experience_fit"], 0.4, places=3)
        # unknown requirement → neutral 1.0
        d2 = self._dim(self._cv(exp=2.0), self._job(exp_min=0.0), {"python"})
        self.assertEqual(d2["experience_fit"], 1.0)

    def test_domain_fit_neutral_when_role_unknown(self):
        d = self._dim(self._cv(), self._job(role=""), {"python"})
        self.assertEqual(d["domain_fit"], 0.5)

    def test_all_scores_in_unit_interval(self):
        d = self._dim(self._cv(seniority=1, exp=0), self._job(skills=("go",), imps=(5,), seniority=5, exp_min=10, role="backend"), set())
        for k, v in d.items():
            self.assertGreaterEqual(v, 0.0, k)
            self.assertLessEqual(v, 1.0, k)


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
