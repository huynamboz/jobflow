from rest_framework import serializers

from apps.jobs.models import Company, CompanyPlatform, Job, JobSkill, Platform


class PlatformSerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Platform
        fields = ("id", "name", "slug", "base_url", "logo_url", "is_active", "job_count", "created_at")
        read_only_fields = ("id", "created_at")


class CompanySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True, default=0)
    platforms = PlatformSerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = ("id", "name", "logo_url", "website_url", "industry", "size", "location", "platforms", "job_count", "created_at")
        read_only_fields = ("id", "created_at")


class JobSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.canonical_name", read_only=True)
    category = serializers.IntegerField(source="skill.category", read_only=True)

    class Meta:
        model = JobSkill
        fields = ("skill_name", "category", "importance")


class JobListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True, default="")
    platform_name = serializers.CharField(source="platform.name", read_only=True, default="")
    platform_logo = serializers.CharField(source="platform.logo_url", read_only=True, default="")

    class Meta:
        model = Job
        fields = (
            "id", "title", "company_name", "platform_name", "platform_logo", "location",
            "seniority", "job_type", "salary_min", "salary_max", "salary_currency",
            "salary_period", "salary_usd_annual_min", "salary_usd_annual_max",
            "applicant_count", "is_active", "date_posted", "source_url", "created_at",
            "lifecycle", "last_verified_at",
        )


class JobDetailSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    platform = PlatformSerializer(read_only=True)
    skills = JobSkillSerializer(source="job_skills", many=True, read_only=True)

    class Meta:
        model = Job
        fields = (
            "id", "title", "description", "company", "platform", "location",
            "seniority", "job_type", "salary_min", "salary_max", "salary_currency",
            "salary_period", "salary_usd_annual_min", "salary_usd_annual_max",
            "source_url", "applicant_count", "skills",
            "is_active", "date_posted", "created_at", "updated_at",
        )
