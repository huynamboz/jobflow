"""Authorization + behavior tests for Employee MVP (feature 012)."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apps.employees.models import Employee, EmployeeJobMatch
from apps.jobs.models import Job, Platform

User = get_user_model()


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class EmployeeAuthorizationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="boss", email="boss@x.com", password="bosspass1", role="admin"
        )
        cls.hr = User.objects.create_user(
            username="hr1", email="hr@x.com", password="hrpass1", role="recruiter"
        )
        cls.candidate = User.objects.create_user(
            username="cand", email="cand@x.com", password="candpass1", role="candidate"
        )
        cls.platform = Platform.objects.create(name="LinkedIn", slug="linkedin")
        cls.job1 = Job.objects.create(platform=cls.platform, title="Senior Python Dev", description="...")
        cls.emp = Employee.objects.create(full_name="Alice", email="alice@acme.com")

    def test_anonymous_denied(self):
        resp = APIClient().get("/api/admin/employees/")
        self.assertEqual(resp.status_code, 401)

    def test_candidate_forbidden(self):
        resp = _auth_client(self.candidate).get("/api/admin/employees/")
        self.assertEqual(resp.status_code, 403)

    def test_recruiter_can_list(self):
        resp = _auth_client(self.hr).get("/api/admin/employees/")
        self.assertEqual(resp.status_code, 200)

    def test_recruiter_can_create(self):
        resp = _auth_client(self.hr).post(
            "/api/admin/employees/",
            {"full_name": "Bob", "email": "bob@acme.com", "seniority": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_recruiter_cannot_delete(self):
        resp = _auth_client(self.hr).delete(f"/api/admin/employees/{self.emp.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_delete(self):
        resp = _auth_client(self.admin).delete(f"/api/admin/employees/{self.emp.id}/")
        self.assertEqual(resp.status_code, 204)

    def test_manual_edit_clears_parse_failed(self):
        # Feature 1.3: editing a parse-failed employee marks it resolved.
        broken = Employee.objects.create(full_name="Broken", is_parse_failed=True)
        resp = _auth_client(self.hr).patch(
            f"/api/admin/employees/{broken.id}/",
            {"skills": ["python", "django"], "seniority": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        broken.refresh_from_db()
        self.assertFalse(broken.is_parse_failed)
        self.assertEqual(broken.skills, ["python", "django"])

    def test_bulk_upload_size_limit(self):
        # Build a fake list of 51 small files via DRF's MultiPartParser
        import io

        files = [("files", io.BytesIO(b"%PDF-1.4 fake"), f"cv{i}.pdf") for i in range(51)]
        client = _auth_client(self.hr)
        # Use multipart
        from django.core.files.uploadedfile import SimpleUploadedFile

        payload = {"files": [SimpleUploadedFile(f"cv{i}.pdf", b"%PDF-1.4 fake") for i in range(51)]}
        resp = client.post("/api/admin/employees/bulk_upload/", payload, format="multipart")
        self.assertEqual(resp.status_code, 413)


class MatchTransitionTests(APITestCase):
    """Shadow model (feature 014): match transitions never auto-change
    Employee.status; the frontman stays on bench to apply again."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="boss", email="boss@x.com", password="x1", role="admin"
        )
        cls.platform = Platform.objects.create(name="LinkedIn", slug="linkedin")
        cls.job = Job.objects.create(platform=cls.platform, title="Job", description="...")
        cls.emp = Employee.objects.create(full_name="Alice", status="bench")
        cls.match = EmployeeJobMatch.objects.create(
            employee=cls.emp, job=cls.job, status="suggested", match_score=0.8
        )

    def test_won_does_not_place_employee(self):
        # US4: winning a job records won_at but leaves the frontman on bench.
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "won"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.emp.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.emp.status, "bench")
        self.assertIsNotNone(self.match.won_at)

    def test_pursuing_does_not_change_employee_status(self):
        # US4: Employee.status is fully manual now.
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "pursuing"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.status, "bench")

    def test_manual_status_change_allowed(self):
        # US4/FR-011: HR can still mark an employee busy (placed) manually.
        resp = _auth_client(self.admin).patch(
            f"/api/admin/employees/{self.emp.id}/",
            {"status": "placed"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.status, "placed")

    def test_dismissed_hidden_from_list(self):
        self.match.status = "dismissed"
        self.match.save()
        client = _auth_client(self.admin)
        default = client.get(f"/api/admin/matches/?employee={self.emp.id}")
        self.assertFalse(any(m["status"] == "dismissed" for m in default.data["results"]))
        only = client.get(f"/api/admin/matches/?employee={self.emp.id}&status=dismissed")
        self.assertTrue(any(m["status"] == "dismissed" for m in only.data["results"]))

    def test_applied_stamps_timestamp(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "applied"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.applied_at)

    def test_explainability_fields_exposed(self):
        # US1: serializer surfaces missing_skills + seniority_gap.
        self.match.missing_skills = ["kubernetes"]
        self.match.matched_skills = ["python"]
        self.match.seniority_gap = 1
        self.match.save()
        resp = _auth_client(self.admin).get(
            f"/api/admin/matches/{self.match.id}/",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["missing_skills"], ["kubernetes"])
        self.assertEqual(resp.data["matched_skills"], ["python"])
        self.assertEqual(resp.data["seniority_gap"], 1)


class DuplicateApplyGuardTests(APITestCase):
    """US3: warn when two employees front the same job."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="boss", email="boss@x.com", password="x1", role="admin"
        )
        cls.platform = Platform.objects.create(name="LinkedIn", slug="linkedin")
        cls.job = Job.objects.create(platform=cls.platform, title="Job", description="...")
        cls.emp1 = Employee.objects.create(full_name="Alice", status="bench")
        cls.emp2 = Employee.objects.create(full_name="Bob", status="bench")
        cls.match1 = EmployeeJobMatch.objects.create(
            employee=cls.emp1, job=cls.job, status="applied", match_score=0.8
        )
        cls.match2 = EmployeeJobMatch.objects.create(
            employee=cls.emp2, job=cls.job, status="suggested", match_score=0.7
        )

    def test_duplicate_apply_warns(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match2.id}/",
            {"status": "applied"},
            format="json",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["error"]["code"], "DUPLICATE_APPLY")
        self.assertEqual(resp.data["error"]["frontman"]["employee_id"], self.emp1.id)
        self.match2.refresh_from_db()
        self.assertEqual(self.match2.status, "suggested")

    def test_duplicate_apply_proceeds_with_confirm(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match2.id}/",
            {"status": "applied", "confirm_duplicate": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.match2.refresh_from_db()
        self.assertEqual(self.match2.status, "applied")

    def test_first_apply_no_warning(self):
        # A job with no prior frontman applies cleanly.
        emp3 = Employee.objects.create(full_name="Cara", status="bench")
        platform2 = Platform.objects.create(name="Indeed", slug="indeed")
        job2 = Job.objects.create(platform=platform2, title="Other", description="...")
        match3 = EmployeeJobMatch.objects.create(
            employee=emp3, job=job2, status="suggested", match_score=0.6
        )
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{match3.id}/",
            {"status": "applied"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)


class CvParserAdapterTests(APITestCase):
    """Feature: wire the real CV parser into the Add-employee flow."""

    def test_seniority_name_to_int_mapping(self):
        from apps.employees.parsers import _seniority_to_int

        self.assertEqual(_seniority_to_int("INTERN"), 0)
        self.assertEqual(_seniority_to_int("mid"), 2)
        self.assertEqual(_seniority_to_int("Senior"), 3)
        self.assertEqual(_seniority_to_int("MANAGER"), 5)
        self.assertEqual(_seniority_to_int(3), 3)
        self.assertIsNone(_seniority_to_int(None))
        self.assertIsNone(_seniority_to_int("unknown-grade"))

    def test_email_phone_extraction(self):
        from apps.employees.parsers import _first_email, _first_phone

        text = "John Doe\n+84354633778 | john.doe@gmail.com\nGPA 3.51/4.0  2021-2023"
        self.assertEqual(_first_email(text), "john.doe@gmail.com")
        self.assertEqual(_first_phone(text), "+84354633778")
        # A bare year range must NOT be read as a phone number.
        self.assertEqual(_first_phone("Education 2021 - 2023"), "")

    def test_position_from_work_experience(self):
        from apps.employees.parsers import _position_from

        self.assertEqual(_position_from([{"title": "Senior Backend Dev"}], "backend"), "Senior Backend Dev")
        self.assertEqual(_position_from([], "frontend"), "Frontend Developer")
        self.assertEqual(_position_from([], "unknownrole"), "")

    def test_adapter_maps_full_output(self):
        # Stub the LLM + text extraction + normalizer so the test stays fast.
        from unittest.mock import patch

        from apps.employees import parsers
        from apps.cvs.services.llm_cv_extractor import CVExtractResult

        result = CVExtractResult(
            name="Jane Smith", experience_years=6.0, seniority=3, role_category="backend",
            skills=[{"name": "Python", "proficiency": 4}, {"name": "Django", "proficiency": 3}],
            work_experience=[{"title": "Senior Backend Engineer"}],
        )
        norm = type("N", (), {"normalize": staticmethod(lambda s: s.lower())})()
        with patch.object(parsers, "_extract_text", return_value="Jane Smith jane@x.com +84354633778"), \
             patch("apps.cvs.services.llm_cv_extractor.extract", return_value=result), \
             patch.object(parsers, "_get_normalizer", return_value=norm):
            out = parsers.parse_cv_file("/tmp/cv.pdf")
        self.assertEqual(out["full_name"], "Jane Smith")
        self.assertEqual(out["position"], "Senior Backend Engineer")
        self.assertEqual(out["email"], "jane@x.com")
        self.assertEqual(out["phone"], "+84354633778")
        self.assertEqual(out["seniority"], 3)
        self.assertEqual(out["skills"], ["python", "django"])

    def test_adapter_returns_empty_on_failure(self):
        from unittest.mock import patch

        from apps.employees import parsers

        with patch.object(parsers, "_extract_text", side_effect=RuntimeError("no file")):
            self.assertEqual(parsers.parse_cv_file("/tmp/cv.pdf"), {})


class RematchTests(APITestCase):
    """Re-match must refresh scores without re-parsing the CV or resetting the
    pipeline status (no-LLM path)."""

    @classmethod
    def setUpTestData(cls):
        cls.platform = Platform.objects.create(name="LinkedIn", slug="linkedin")
        cls.job = Job.objects.create(platform=cls.platform, title="Backend", description="...", seniority=3)
        cls.emp = Employee.objects.create(full_name="Alice", status="bench", seniority=2, skills=["python"])

    def test_persist_preserves_status_on_existing(self):
        from apps.employees.tasks import _persist_matches

        EmployeeJobMatch.objects.create(
            employee=self.emp, job=self.job, status="applied", match_score=0.5, matched_skills=["python"]
        )
        res = _persist_matches(self.emp, [{
            "job_id": self.job.id, "score": 0.91,
            "matched_skills": ["python", "django"], "missing_skills": ["aws"],
        }])
        m = EmployeeJobMatch.objects.get(employee=self.emp, job=self.job)
        self.assertEqual(m.status, "applied")          # HR progress preserved
        self.assertAlmostEqual(m.match_score, 0.91)    # score refreshed
        self.assertEqual(m.matched_skills, ["python", "django"])
        self.assertEqual(res["matches_created"], 0)

    def test_persist_creates_as_suggested_with_gap(self):
        from apps.employees.tasks import _persist_matches

        res = _persist_matches(self.emp, [{
            "job_id": self.job.id, "score": 0.8, "matched_skills": ["python"], "missing_skills": [],
        }])
        m = EmployeeJobMatch.objects.get(employee=self.emp, job=self.job)
        self.assertEqual(m.status, "suggested")
        self.assertEqual(m.seniority_gap, 1)           # job 3 − emp 2
        self.assertEqual(res["matches_created"], 1)

    def test_rematch_uses_engine_not_llm_with_cv_text(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.employees import matching

        emp = Employee.objects.create(
            full_name="Bob", status="bench", seniority=2, skills=["python", "django"],
            cv_file=SimpleUploadedFile("cv.pdf", b"%PDF fake"),
        )
        fake = {"jobs": [{"job_id": self.job.id, "score": 0.7, "matched_skills": ["python"], "missing_skills": []}]}
        with patch("apps.matching.services.match_cv_data", return_value=fake) as mcd, \
             patch("apps.employees.parsers.extract_text_from_cv", return_value="real cv text"):
            out = matching.rematch_employee(emp, top_k=10)

        self.assertEqual([o["job_id"] for o in out], [self.job.id])
        _, kwargs = mcd.call_args
        self.assertEqual(kwargs["skills"], ["python", "django"])  # stored skills, no LLM
        self.assertEqual(kwargs["text"], "real cv text")          # faithful CV text


class DashboardTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="a", email="a@x.com", password="x1", role="admin"
        )
        cls.platform = Platform.objects.create(name="LinkedIn", slug="linkedin")
        cls.job = Job.objects.create(platform=cls.platform, title="Job", description="...")
        cls.bench = Employee.objects.create(full_name="BenchGuy", status="bench")
        cls.broken = Employee.objects.create(full_name="Broken", is_parse_failed=True)
        EmployeeJobMatch.objects.create(
            employee=cls.bench, job=cls.job, status="suggested", match_score=0.9
        )

    def test_requires_hr_role(self):
        cand = User.objects.create_user(
            username="c", email="c@x.com", password="x1", role="candidate"
        )
        resp = _auth_client(cand).get("/api/admin/staffing/dashboard/")
        self.assertEqual(resp.status_code, 403)

    def test_returns_all_blocks(self):
        resp = _auth_client(self.admin).get("/api/admin/staffing/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["data"]
        for key in ("kpi", "action_queue", "funnel", "alerts", "recent"):
            self.assertIn(key, data)
        # bench employee with a suggested match shows up in the action queue
        self.assertTrue(
            any(r["full_name"] == "BenchGuy" for r in data["action_queue"]["top_new_matches"])
        )
        # high-score suggested match surfaces as an alert
        self.assertTrue(len(data["alerts"]["high_score_unapplied"]) >= 1)
        # parse-failed employee surfaces as an alert
        self.assertTrue(
            any(r["full_name"] == "Broken" for r in data["alerts"]["parse_failed"])
        )
        self.assertEqual(data["funnel"]["suggested"], 1)


class KpiTests(APITestCase):
    def test_kpi_requires_hr_role(self):
        cand = User.objects.create_user(
            username="c", email="c@x.com", password="x1", role="candidate"
        )
        resp = _auth_client(cand).get("/api/admin/pipeline/kpi/")
        self.assertEqual(resp.status_code, 403)

    def test_kpi_returns_expected_shape(self):
        admin = User.objects.create_user(
            username="a", email="a@x.com", password="x1", role="admin"
        )
        resp = _auth_client(admin).get("/api/admin/pipeline/kpi/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("employees", resp.data["data"])
        self.assertIn("matches_this_week", resp.data["data"])
        self.assertIn("top_employees_pursuing", resp.data["data"])
