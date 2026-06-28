from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.static import serve as _serve_media
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
    # Employee MVP (feature 012)
    path("api/admin/", include("apps.employees.urls")),
    path("api/admin/mail/", include("apps.mail.urls")),
    path("api/admin/integrations/", include("apps.integrations.urls")),
    path("api/notifications/", include("apps.notifications.urls")),

    # Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
]

# Serve uploaded media (CV PDFs, etc.) from the dev server when DEBUG is on.
# The view is X-Frame-Options-exempt so the admin SPA (different dev origin,
# :5173) can preview PDFs inside an <iframe> without being clickjack-blocked.
# In production, a real web server / object storage should serve MEDIA_URL.
if settings.DEBUG:
    _media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(
            rf"^{_media_prefix}(?P<path>.*)$",
            xframe_options_exempt(_serve_media),
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
