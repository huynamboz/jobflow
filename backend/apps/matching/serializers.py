from rest_framework import serializers

from apps.matching.models import TrainRun


class CVTextMatchRequest(serializers.Serializer):
    text = serializers.CharField(min_length=10, help_text="CV text content")
    top_k = serializers.IntegerField(default=10, min_value=1, max_value=100)


class CVFileMatchRequest(serializers.Serializer):
    file = serializers.FileField(help_text="CV file (PDF/DOCX/TXT)")
    top_k = serializers.IntegerField(default=10, min_value=1, max_value=100, required=False)

    class Meta:
        pass


class JobMatchResponse(serializers.Serializer):
    job_id = serializers.IntegerField()
    score = serializers.FloatField()
    eligible = serializers.BooleanField()
    matched_skills = serializers.ListField(child=serializers.CharField())
    missing_skills = serializers.ListField(child=serializers.CharField())
    seniority_match = serializers.BooleanField()
    title = serializers.CharField()
    company_name = serializers.CharField(default="")
    location = serializers.CharField(default="")
    job_type = serializers.CharField(default="")
    salary_min = serializers.IntegerField(default=0)
    salary_max = serializers.IntegerField(default=0)
    salary_currency = serializers.CharField(default="USD")
    role_category = serializers.CharField(default="")
    experience_min = serializers.FloatField(allow_null=True, default=None)
    experience_max = serializers.FloatField(allow_null=True, default=None)
    source_url = serializers.CharField(default="")


class CVInfoResponse(serializers.Serializer):
    skills = serializers.ListField(child=serializers.CharField())
    seniority = serializers.CharField()
    experience_years = serializers.FloatField()
    education = serializers.CharField()


class CVMatchResponse(serializers.Serializer):
    cv_info = CVInfoResponse()
    jobs = JobMatchResponse(many=True)


class CVParseResponse(serializers.Serializer):
    seniority = serializers.CharField()
    experience_years = serializers.FloatField()
    education = serializers.CharField()
    skills = serializers.ListField(child=serializers.CharField())


class TrainRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainRun
        fields = (
            "id", "version", "is_active", "status", "description",
            "num_jobs", "num_cvs", "num_pairs", "num_skills",
            "model_type", "hidden_channels", "num_layers", "learning_rate",
            "auc_roc", "recall_at_5", "recall_at_10",
            "precision_at_5", "precision_at_10", "ndcg_at_10", "mrr",
            "best_epoch", "final_loss", "reranker_accuracy",
            "metrics_json", "config_json",
            "checkpoint_path", "training_duration_seconds",
            "started_at", "completed_at",
        )
        read_only_fields = (
            "id", "version", "status",
            "num_jobs", "num_cvs", "num_pairs", "num_skills",
            "auc_roc", "recall_at_5", "recall_at_10",
            "precision_at_5", "precision_at_10", "ndcg_at_10", "mrr",
            "best_epoch", "final_loss", "reranker_accuracy",
            "metrics_json", "config_json",
            "checkpoint_path", "training_duration_seconds",
            "started_at", "completed_at",
        )


class DashboardStatsSerializer(serializers.Serializer):
    total_jobs = serializers.IntegerField()
    total_cvs = serializers.IntegerField()
    total_skills = serializers.IntegerField()
    total_companies = serializers.IntegerField()
    total_platforms = serializers.IntegerField()
    active_model = TrainRunSerializer(allow_null=True)
    platforms = serializers.ListField()
