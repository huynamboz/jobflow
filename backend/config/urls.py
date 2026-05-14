from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django Admin (built-in)
    path("admin/", admin.site.urls),

    # Public APIs
    path("api/auth/", include("apps.users.urls")),
    path("api/jobs/", include("apps.jobs.urls")),
    path("api/cvs/", include("apps.cvs.urls")),
    path("api/skills/", include("apps.skills.urls")),
    path("api/matching/", include("apps.matching.urls")),

    path("api/labeling/", include("apps.labeling.urls")),

    # Admin-only APIs
    path("api/admin/users/", include("apps.users.admin_urls")),
    path("api/admin/", include("apps.jobs.admin_urls")),
    path("api/admin/", include("apps.matching.admin_urls")),
    path("api/admin/", include("apps.cvs.admin_urls")),
    path("api/admin/", include("apps.llm.urls")),
    path("api/admin/", include("apps.labeling.admin_urls")),
    path("api/admin/", include("apps.admin_dashboard.urls")),
    path("api/admin/", include("apps.schedule.urls")),

    # Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
]
