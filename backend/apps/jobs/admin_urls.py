"""Admin-only job management URLs (/api/admin/...)."""

from django.urls import path

from apps.jobs.admin_views import (
    AdminCompanyDetailView,
    AdminCompanyListView,
    AdminJobDetailView,
    AdminJobListView,
    AdminPlatformDetailView,
    AdminPlatformListView,
    JDBatchPreviewView,
    JDBatchListView,
    JDBatchDetailView,
    JDBatchCancelView,
    JDBatchResumeView,
    JDBatchRecordDetailView,
    JDExportView,
)

urlpatterns = [
    path("platforms/", AdminPlatformListView.as_view(), name="admin-platform-list"),
    path("platforms/<int:pk>/", AdminPlatformDetailView.as_view(), name="admin-platform-detail"),
    path("companies/", AdminCompanyListView.as_view(), name="admin-company-list"),
    path("companies/<int:pk>/", AdminCompanyDetailView.as_view(), name="admin-company-detail"),
    path("jobs/", AdminJobListView.as_view(), name="admin-job-list"),
    path("jobs/<int:pk>/", AdminJobDetailView.as_view(), name="admin-job-detail"),
    path("jd/export/", JDExportView.as_view(), name="admin-jd-export"),
    path("jd/batches/preview/", JDBatchPreviewView.as_view(), name="admin-jd-batch-preview"),
    path("jd/batches/", JDBatchListView.as_view(), name="admin-jd-batch-list"),
    path("jd/batches/<int:pk>/", JDBatchDetailView.as_view(), name="admin-jd-batch-detail"),
    path("jd/batches/<int:pk>/cancel/", JDBatchCancelView.as_view(), name="admin-jd-batch-cancel"),
    path("jd/batches/<int:pk>/resume/", JDBatchResumeView.as_view(), name="admin-jd-batch-resume"),
    path("jd/batches/<int:pk>/records/<int:record_pk>/", JDBatchRecordDetailView.as_view(), name="admin-jd-batch-record-detail"),
]
