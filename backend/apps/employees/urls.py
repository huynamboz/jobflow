from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.employees.views import (
    DashboardView,
    EmployeeJobMatchViewSet,
    EmployeeViewSet,
    GenerateApplicationEmailView,
    PipelineKpiView,
)

router = DefaultRouter()
router.register(r"employees", EmployeeViewSet, basename="admin-employee")
router.register(r"matches", EmployeeJobMatchViewSet, basename="admin-match")

urlpatterns = [
    # Declared before the router so it isn't shadowed by employees/<pk>/.
    path("application-email/", GenerateApplicationEmailView.as_view(), name="admin-generate-email"),
    path("", include(router.urls)),
    path("pipeline/kpi/", PipelineKpiView.as_view(), name="admin-pipeline-kpi"),
    path("staffing/dashboard/", DashboardView.as_view(), name="admin-staffing-dashboard"),
]
