"""Admin-only training management URLs (/api/admin/...)."""

from django.urls import path

from apps.matching.admin_views import (
    AdminDashboardView,
    AdminTrainRunActivateView,
    AdminTrainRunDetailView,
    AdminTrainRunListView,
)

urlpatterns = [
    path("dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("training/", AdminTrainRunListView.as_view(), name="admin-train-list"),
    path("training/<int:pk>/", AdminTrainRunDetailView.as_view(), name="admin-train-detail"),
    path("training/<int:pk>/activate/", AdminTrainRunActivateView.as_view(), name="admin-train-activate"),
]
