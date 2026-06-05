from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.employees.views import (
    EmployeeJobMatchViewSet,
    EmployeeViewSet,
    PipelineKpiView,
)

router = DefaultRouter()
router.register(r"employees", EmployeeViewSet, basename="admin-employee")
router.register(r"matches", EmployeeJobMatchViewSet, basename="admin-match")

urlpatterns = [
    path("", include(router.urls)),
    path("pipeline/kpi/", PipelineKpiView.as_view(), name="admin-pipeline-kpi"),
]
