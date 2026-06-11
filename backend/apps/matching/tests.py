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

    def test_carries_experience_fields(self):
        # 021/A1: experience_min/max must reach JobData or the experience gate
        # and experience_fit are silent no-ops on the live pool.
        from apps.jobs.models import Job, JobSkill
        from apps.matching.services.matching_service import build_jobdata_from_db

        job = Job.objects.create(
            title="Senior DevOps", description="K8s", seniority=3,
            experience_min=5.0, experience_max=8.0, is_active=True,
        )
        JobSkill.objects.create(job=job, skill=self._skill("kubernetes"), importance=5)
        none_job = Job.objects.create(title="Intern", description="x", is_active=True)
        JobSkill.objects.create(job=none_job, skill=self._skill("excel"), importance=3)

        by_id = {jd.job_id: jd for jd in build_jobdata_from_db()}
        self.assertEqual(by_id[job.id].experience_min, 5.0)
        self.assertEqual(by_id[job.id].experience_max, 8.0)
        self.assertEqual(by_id[none_job.id].experience_min, 0.0)  # null → neutral

    def test_excludes_skill_less_and_inactive(self):
        from apps.jobs.models import Job, JobSkill
        from apps.matching.services.matching_service import build_jobdata_from_db

        no_skill = Job.objects.create(title="A", description="x", is_active=True)
        inactive = Job.objects.create(title="B", description="x", is_active=False)
        JobSkill.objects.create(job=inactive, skill=self._skill("go"), importance=4)

        ids = {jd.job_id for jd in build_jobdata_from_db()}
        self.assertNotIn(no_skill.id, ids)   # no skills → excluded
        self.assertNotIn(inactive.id, ids)   # inactive → excluded


class JobDedupTests(TestCase):
    """021/A9: catalog dedup keeps engaged/newest; serving guard drops repeats."""

    def test_serving_guard_drops_title_company_repeats(self):
        from apps.matching.services.matching_service import _dedup_by_title_company
        items = [
            {"title": "JavaScript Tutor", "company_name": "Wyzant", "score": 0.9},
            {"title": "javascript tutor ", "company_name": " WYZANT", "score": 0.8},  # repeat
            {"title": "JavaScript Tutor", "company_name": "Other Co", "score": 0.7},  # diff company
        ]
        out = _dedup_by_title_company(items)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["score"], 0.9)  # first (best) kept

    def test_dedup_jobs_keeps_engaged_else_newest(self):
        from django.core.management import call_command
        from apps.employees.models import Employee, EmployeeJobMatch
        from apps.jobs.models import Job

        old = Job.objects.create(title="Dup Dev", description="x", is_active=True)
        new = Job.objects.create(title="Dup Dev", description="x", is_active=True)
        old_engaged = Job.objects.create(title="Eng Dev", description="x", is_active=True)
        new_plain = Job.objects.create(title="Eng Dev", description="x", is_active=True)
        emp = Employee.objects.create(full_name="E", seniority=2)
        EmployeeJobMatch.objects.create(employee=emp, job=old_engaged, match_score=0.5,
                                        status=EmployeeJobMatch.Status.APPLIED)

        call_command("dedup_jobs")
        old.refresh_from_db(); new.refresh_from_db()
        old_engaged.refresh_from_db(); new_plain.refresh_from_db()
        self.assertFalse(old.is_active)          # older loses
        self.assertTrue(new.is_active)           # newest kept
        self.assertTrue(old_engaged.is_active)   # engaged kept despite being older
        self.assertFalse(new_plain.is_active)


class PerCvMetricsTests(TestCase):
    """021/A7: ranking metrics are per-CV means, not a global flat ranking."""

    def test_per_cv_means_and_exclusions(self):
        from ml_service.inference import engine  # noqa: F401 — warm PyG import chain (standalone-run quirk)
        from ml_service.training.trainer import _per_cv_metrics
        # CV 0: perfect ranking (pos on top). CV 1: worst (pos at bottom).
        # CV 2: no positive → excluded.
        y = np.array([1, 0, 0,   0, 0, 1,   0, 0])
        s = np.array([.9, .5, .1, .9, .5, .1, .9, .5])
        cv = np.array([0, 0, 0,  1, 1, 1,   2, 2])
        m = _per_cv_metrics(y, s, cv)
        self.assertEqual(m["num_cvs_evaluated"], 2.0)
        self.assertAlmostEqual(m["mrr"], (1.0 + 1/3) / 2, places=4)  # mean of per-CV MRR
        self.assertLess(m["precision@5"], 1.0)  # no global-ranking artifact
        self.assertIn("auc_roc", m)             # global AUC still reported


class FinalOrderTests(TestCase):
    """021/A3: final order follows rank_score (reranker×penalty); display monotonic."""

    def _result(self, job_id, score):
        from ml_service.inference.engine import JobMatchResult
        return JobMatchResult(job_id=job_id, score=score, eligible=True,
                              matched_skills=(), missing_skills=(),
                              seniority_match=True, title=f"j{job_id}")

    def test_order_follows_rank_and_display_monotonic(self):
        from ml_service.inference.engine import InferenceEngine
        # display says A > B > C, but reranker rank says C > A > B
        results = [self._result(1, 0.9), self._result(2, 0.8), self._result(3, 0.7)]
        rank = [0.30, 0.10, 0.50]
        final = InferenceEngine._finalize_results(results, rank, top_k=3, remap=True)
        self.assertEqual([r.job_id for r in final], [3, 1, 2])      # reranker order wins
        scores = [r.score for r in final]
        self.assertEqual(scores, sorted(scores, reverse=True))      # monotonic display
        self.assertEqual(scores[0], 0.9)                            # mapped into display range
        self.assertEqual(scores[-1], 0.7)

    def test_no_reranker_keeps_legacy_behavior(self):
        from ml_service.inference.engine import InferenceEngine
        results = [self._result(1, 0.9), self._result(2, 0.8)]
        rank = [0.9, 0.8]  # fallback: rank == penalized stage-1
        final = InferenceEngine._finalize_results(results, rank, top_k=2, remap=False)
        self.assertEqual([r.job_id for r in final], [1, 2])
        self.assertEqual([r.score for r in final], [0.9, 0.8])      # untouched


class GraphConflictGuardTests(TestCase):
    """021/A2: GraphBuilder must refuse a pair labeled both match and no_match."""

    class _FakeEmbed:
        dim = 384
        def encode(self, texts):
            return np.zeros((len(texts), 384), dtype=np.float32)

    def _build(self, pairs):
        from ml_service.graph.builder import GraphBuilder
        from ml_service.graph.schema import (CVData, EducationLevel, JobData,
                                             LabeledPair, SeniorityLevel, SkillCategory)
        cvs = [CVData(cv_id=1, seniority=SeniorityLevel(2), experience_years=3.0,
                      education=EducationLevel(2), skills=("python",),
                      skill_proficiencies=(3,), text="dev")]
        jobs = [JobData(job_id=10, seniority=SeniorityLevel(2), skills=("python",),
                        skill_importances=(4,), salary_min=0, salary_max=0, text="job")]
        catalog = {"python": SkillCategory.TECHNICAL}
        lp = [LabeledPair(cv_id=p[0], job_id=p[1], label=p[2]) for p in pairs]
        return GraphBuilder(self._FakeEmbed()).build(cvs, jobs, catalog, lp)

    def test_conflicting_pair_raises(self):
        with self.assertRaises(ValueError):
            self._build([(1, 10, 1), (1, 10, 0)])  # same pair, both labels

    def test_clean_pairs_build_fine(self):
        data = self._build([(1, 10, 1)])
        self.assertEqual(data["cv", "match", "job"].edge_index.shape[1], 1)
        self.assertEqual(data["cv", "no_match", "job"].edge_index.shape[1], 0)


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


class RerankerWeightSyncTests(TestCase):
    """023/3.6 (A14): reranker must be trained with the serving hybrid weights."""

    def test_sync_detection(self):
        from ml_service.inference.engine import InferenceEngine
        w = {"alpha": 0.05, "beta": 0.35, "gamma": 0.2, "delta": 0.4}
        ok = InferenceEngine._reranker_weights_in_sync
        self.assertTrue(ok(w, dict(w)))
        self.assertFalse(ok(w, {**w, "delta": 0.1}))     # tuned after training → stale
        self.assertFalse(ok(w, None))                     # old checkpoint, no stamp → warn
        self.assertFalse(ok(None, w))


class DeterministicRoleTests(TestCase):
    """025: CV role decided once from structured fields — path-independent."""

    def test_skill_dump_text_does_not_flip_role(self):
        from ml_service.inference.role_classifier import infer_role
        skills = ("react", "vuejs", "nodejs", "express", "docker", "ci_cd")
        # role từ skills + position (đường match_cv_data) phải ổn định,
        # không phụ thuộc text "Skills: react, ..." (từng kích hoạt title regex)
        self.assertEqual(infer_role(skills, ""), infer_role(skills, ""))
        with_position = infer_role(skills, "Frontend Developer")
        self.assertEqual(with_position, "frontend")

    def test_cvdata_role_takes_precedence_over_text(self):
        from ml_service.inference.engine import InferenceEngine
        from ml_service.graph.schema import CVData, SeniorityLevel, EducationLevel
        cv = CVData(cv_id=-1, seniority=SeniorityLevel(2), experience_years=3.0,
                    education=EducationLevel(2), skills=("react", "nodejs"),
                    skill_proficiencies=(3, 3),
                    text="Skills: react, nodejs",  # text bẫy title-regex
                    role_category="fullstack")
        self.assertEqual(InferenceEngine._cv_role(cv), "fullstack")


class CoveredSkillsTests(TestCase):
    """025: 3-tier coverage — implication beats PMI's common-skill blindness."""

    def _covered(self, cv_skills, missing):
        from ml_service.inference.engine import InferenceEngine
        class _E:  # chỉ cần _skill_similarity cho tier 3
            _skill_similarity = {}
            _SKILL_IMPLIES = InferenceEngine._SKILL_IMPLIES
            _EQUIV_CLUSTERS = InferenceEngine._EQUIV_CLUSTERS
            _COVER_MIN_SIM = InferenceEngine._COVER_MIN_SIM
        return InferenceEngine._covered_missing(_E(), set(cv_skills), set(missing))

    def test_frameworks_imply_javascript(self):
        cov = self._covered(["react", "nodejs", "express", "ci_cd"],
                            ["javascript", "microservices", "unit_testing", "mongodb"])
        self.assertIn("javascript", cov)           # react/nodejs/express ⇒ js
        self.assertNotIn("mongodb", cov)           # express KHÔNG thay mongodb (co-travel)
        self.assertNotIn("microservices", cov)     # thiếu thật
        self.assertNotIn("unit_testing", cov)

    def test_equiv_cluster_and_implies(self):
        cov = self._covered(["vuejs", "vite", "sass"], ["react", "webpack", "html_css", "python"])
        self.assertEqual(cov.get("react"), "vuejs")    # cụm FE framework
        self.assertEqual(cov.get("webpack"), "vite")   # cụm build tool
        self.assertIn(cov.get("html_css"), ("sass", "vuejs"))  # sass/vuejs ⇒ html_css
        self.assertNotIn("python", cov)
