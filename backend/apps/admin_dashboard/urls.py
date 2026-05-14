from django.urls import path

from apps.admin_dashboard.views import (
    DashboardCatalogView,
    DashboardFreshnessView,
    DashboardKpiView,
    DashboardLabelingView,
    DashboardModelView,
    DashboardOpsView,
)

urlpatterns = [
    path("dashboard/kpi/",       DashboardKpiView.as_view(),       name="dashboard-kpi"),
    path("dashboard/catalog/",   DashboardCatalogView.as_view(),   name="dashboard-catalog"),
    path("dashboard/freshness/", DashboardFreshnessView.as_view(), name="dashboard-freshness"),
    path("dashboard/ops/",       DashboardOpsView.as_view(),       name="dashboard-ops"),
    path("dashboard/labeling/",  DashboardLabelingView.as_view(),  name="dashboard-labeling"),
    path("dashboard/model/",     DashboardModelView.as_view(),     name="dashboard-model"),
]
