"""Thin DRF views — call into services.py, wrap in the standard envelope."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_dashboard import services


def _envelope(data):
    return Response({"success": True, "data": data})


class DashboardKpiView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _envelope(services.compute_kpi())


class DashboardCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _envelope(services.compute_catalog())


class DashboardFreshnessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days_added = int(request.query_params.get("days_added", 30))
        days_outcomes = int(request.query_params.get("days_outcomes", 14))
        return _envelope(
            services.compute_freshness(
                days_added=days_added, days_outcomes=days_outcomes
            )
        )


class DashboardOpsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get("recent_runs_limit", 20))
        return _envelope(services.compute_ops(recent_runs_limit=limit))


class DashboardLabelingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _envelope(services.compute_labeling())


class DashboardModelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _envelope(services.compute_model())
