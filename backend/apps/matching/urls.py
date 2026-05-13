from django.urls import path

from apps.matching.views import (
    JobInfoView,
    MatchCVTextView,
    MatchCVUploadView,
    ParseCVTextView,
    ParseCVUploadView,
)

urlpatterns = [
    path("cv/", MatchCVTextView.as_view(), name="match-cv-text"),
    path("cv/upload/", MatchCVUploadView.as_view(), name="match-cv-upload"),
    path("parse/", ParseCVTextView.as_view(), name="parse-cv-text"),
    path("parse/upload/", ParseCVUploadView.as_view(), name="parse-cv-upload"),
    path("job-info/<int:jd_id>/", JobInfoView.as_view(), name="job-info"),
]
