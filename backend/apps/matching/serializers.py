from rest_framework import serializers

from apps.matching.models import TrainRun


# 025: sandbox matching API serializers removed (see views.py).


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
