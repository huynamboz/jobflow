from django.urls import path

from apps.notifications.views import UnsubscribeView

urlpatterns = [
    path("unsubscribe/<uuid:token>/", UnsubscribeView.as_view(), name="notifications-unsubscribe"),
]
