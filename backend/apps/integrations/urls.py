from django.urls import path

from apps.integrations import views

urlpatterns = [
    path("", views.IntegrationListView.as_view(), name="integration-list"),
    # Zalo QR login (proxied to the zca-js sidecar) — must precede the generic
    # <platform_id> routes.
    path("zalo/login-qr/start/", views.zalo_login_start, name="integration-zalo-qr-start"),
    path("zalo/login-qr/status/", views.zalo_login_status, name="integration-zalo-qr-status"),
    path("zalo/logout/", views.zalo_logout, name="integration-zalo-logout"),
    path("zalo/threads/", views.zalo_threads, name="integration-zalo-threads"),
    path("<str:platform_id>/", views.IntegrationDetailView.as_view(), name="integration-detail"),
    path("<str:platform_id>/test/", views.test_integration, name="integration-test"),
    path("<str:platform_id>/events/", views.set_events, name="integration-events"),
]
