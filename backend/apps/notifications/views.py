from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


class UnsubscribeView(APIView):
    """POST /api/notifications/unsubscribe/<uuid:token>/ — public opt-out."""

    permission_classes = [AllowAny]

    def post(self, request, token):
        user = get_object_or_404(User, unsubscribe_token=token)
        user.notify_daily_digest = False
        user.save(update_fields=["notify_daily_digest"])
        return Response(
            {"success": True, "message": "You have been unsubscribed from the daily digest."}
        )
