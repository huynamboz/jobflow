"""Admin-only training management + dashboard (/api/admin/...)."""

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cvs.models import CV
from apps.jobs.models import Company, Job, Platform
from apps.matching.models import TrainRun
from apps.matching.serializers import DashboardStatsSerializer, TrainRunSerializer
from apps.skills.models import Skill
from apps.users.permissions import IsAdmin


class AdminDashboardView(APIView):
    """GET /api/admin/dashboard/ — System stats overview."""

    permission_classes = [IsAdmin]

    @extend_schema(responses={200: DashboardStatsSerializer}, tags=["Admin"])
    def get(self, request):
        active_model = TrainRun.objects.filter(is_active=True).first()
        platforms = list(
            Platform.objects.annotate(job_count=Count("jobs")).values("name", "slug", "job_count", "is_active")
        )

        data = {
            "total_jobs": Job.objects.filter(is_active=True).count(),
            "total_cvs": CV.objects.filter(is_active=True).count(),
            "total_skills": Skill.objects.count(),
            "total_companies": Company.objects.count(),
            "total_platforms": Platform.objects.count(),
            "active_model": TrainRunSerializer(active_model).data if active_model else None,
            "platforms": platforms,
        }
        return Response({"success": True, "data": data})


class AdminTrainRunListView(APIView):
    """GET /api/admin/training/ — List all training runs."""

    permission_classes = [IsAdmin]

    @extend_schema(responses={200: TrainRunSerializer(many=True)}, tags=["Admin"])
    def get(self, request):
        runs = TrainRun.objects.all()[:50]
        return Response({"success": True, "data": TrainRunSerializer(runs, many=True).data})


class AdminTrainRunDetailView(APIView):
    """GET/PATCH /api/admin/training/<id>/ — View or update training run."""

    permission_classes = [IsAdmin]

    @extend_schema(responses={200: TrainRunSerializer}, tags=["Admin"])
    def get(self, request, pk):
        try:
            run = TrainRun.objects.get(pk=pk)
        except TrainRun.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Training run not found.", "status": 404}}, status=404)
        return Response({"success": True, "data": TrainRunSerializer(run).data})

    @extend_schema(request=TrainRunSerializer, responses={200: TrainRunSerializer}, tags=["Admin"])
    def patch(self, request, pk):
        try:
            run = TrainRun.objects.get(pk=pk)
        except TrainRun.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Training run not found.", "status": 404}}, status=404)

        # Only allow updating description
        if "description" in request.data:
            run.description = request.data["description"]
            run.save(update_fields=["description"])

        return Response({"success": True, "data": TrainRunSerializer(run).data})


class AdminTrainRunActivateView(APIView):
    """POST /api/admin/training/<id>/activate/ — Set this model as active."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def post(self, request, pk):
        try:
            run = TrainRun.objects.get(pk=pk)
        except TrainRun.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Training run not found.", "status": 404}}, status=404)

        if run.status != TrainRun.Status.COMPLETED:
            return Response({"success": False, "error": {"code": "BAD_REQUEST", "message": "Can only activate completed training runs.", "status": 400}}, status=400)

        # Copy checkpoint to "latest"
        import shutil
        from django.conf import settings

        if run.checkpoint_path:
            shutil.copytree(run.checkpoint_path, settings.ML_CHECKPOINT_DIR, dirs_exist_ok=True)

        run.activate()

        return Response({"success": True, "message": f"Model {run.version} activated.", "data": TrainRunSerializer(run).data})


# In-app rule-based training (TrainService/PairLabeler) was removed — production
# models are trained offline via run_train_save.py on LLM labels (see
# docs/codebase-knowledge/05-training-pipeline.md). The TrainRun history +
# activate-a-checkpoint views below stay.
