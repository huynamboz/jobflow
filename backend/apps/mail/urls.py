from django.urls import path

from apps.mail import views

urlpatterns = [
    path("credentials/", views.CredentialView.as_view(), name="mail-credential"),
    path("credentials/<int:employee_id>/", views.CredentialUnlinkView.as_view(), name="mail-credential-unlink"),
    path("send-apply/", views.send_apply, name="mail-send-apply"),
    path("thread/", views.thread, name="mail-thread"),
    path("notifications/", views.NotificationListView.as_view(), name="mail-notifications"),
    path("notifications/unread-count/", views.unread_count, name="mail-unread-count"),
    path("notifications/<int:pk>/read/", views.mark_read, name="mail-mark-read"),
    path("notifications/recent-replies/", views.recent_replies, name="mail-recent-replies"),
    path("sync/", views.sync_now, name="mail-sync"),
    path("sync-status/", views.sync_status, name="mail-sync-status"),
    path("logs/", views.email_log_list, name="mail-logs"),
    path("logs/<int:pk>/", views.email_log_detail, name="mail-log-detail"),
    path("accounts/", views.credential_list, name="mail-accounts"),
]
