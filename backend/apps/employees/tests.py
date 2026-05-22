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


class MatchAutoTransitionTests(APITestCase):
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

    def test_won_sets_employee_placed(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "won"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.emp.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.emp.status, "placed")
        self.assertIsNotNone(self.match.won_at)

    def test_pursuing_promotes_bench_employee(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "pursuing"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.status, "pursuing")

    def test_applied_stamps_timestamp(self):
        resp = _auth_client(self.admin).patch(
            f"/api/admin/matches/{self.match.id}/",
            {"status": "applied"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.applied_at)


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
