import tempfile
from pathlib import Path

from drf_spectacular.utils import OpenApiTypes, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matching.serializers import (
    CVFileMatchRequest,
    CVMatchResponse,
    CVParseResponse,
    CVTextMatchRequest,
    JobMatchResponse,
)
from apps.matching.services import match_cv_file, match_cv_text, parse_cv_file, parse_cv_text


class MatchCVTextView(APIView):
    """POST /api/matching/cv — Input CV text → Top K matching Jobs."""

    permission_classes = [AllowAny]

    @extend_schema(request=CVTextMatchRequest, responses={200: CVMatchResponse()})
    def post(self, request):
        serializer = CVTextMatchRequest(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = match_cv_text(
            cv_text=serializer.validated_data["text"],
            top_k=serializer.validated_data.get("top_k", 10),
        )
        return Response({"success": True, "data": CVMatchResponse(result).data})


class MatchCVUploadView(APIView):
    """POST /api/matching/cv/upload — Upload CV PDF/DOCX → Top K matching Jobs."""

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary", "description": "CV file (PDF/DOCX/TXT)"},
                    "top_k": {"type": "integer", "default": 10, "description": "Number of top jobs to return"},
                },
                "required": ["file"],
            }
        },
        responses={200: JobMatchResponse(many=True)},
    )
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"success": False, "error": {"code": "BAD_REQUEST", "message": "No file uploaded.", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suffix = Path(file.name).suffix.lower()
        if suffix not in (".pdf", ".docx", ".txt"):
            return Response(
                {"success": False, "error": {"code": "BAD_REQUEST", "message": f"Unsupported file type: {suffix}. Use .pdf, .docx, or .txt", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        top_k = int(request.data.get("top_k", 10))

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            result = match_cv_file(tmp_path, top_k=top_k)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not result["jobs"] and not result["cv_info"]["skills"]:
            return Response(
                {"success": False, "error": {"code": "UNPROCESSABLE_ENTITY", "message": "No skills could be extracted from the CV.", "status": 422}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response({"success": True, "data": CVMatchResponse(result).data})


class ParseCVTextView(APIView):
    """POST /api/matching/parse — Parse CV text → structured data (debug)."""

    permission_classes = [AllowAny]

    @extend_schema(request=CVTextMatchRequest, responses={200: CVParseResponse})
    def post(self, request):
        serializer = CVTextMatchRequest(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = parse_cv_text(serializer.validated_data["text"])
        return Response({"success": True, "data": CVParseResponse(result).data})


class ParseCVUploadView(APIView):
    """POST /api/matching/parse/upload — Upload CV → parsed data (debug)."""

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary", "description": "CV file (PDF/DOCX/TXT)"},
                },
                "required": ["file"],
            }
        },
        responses={200: CVParseResponse},
    )
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"success": False, "error": {"code": "BAD_REQUEST", "message": "No file uploaded.", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suffix = Path(file.name).suffix.lower()
        if suffix not in (".pdf", ".docx", ".txt"):
            return Response(
                {"success": False, "error": {"code": "BAD_REQUEST", "message": f"Unsupported file type: {suffix}. Use .pdf, .docx, or .txt", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            result = parse_cv_file(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return Response({"success": True, "data": CVParseResponse(result).data})


class JobInfoView(APIView):
    """GET /api/matching/job-info/<jd_id>/ — Full job details for the drawer.

    jd_id is JDExtractionRecord.id (what the matching engine uses as job_id).
    Returns description + all structured fields from the extraction result.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, jd_id: int):
        from apps.jobs.models import JDExtractionRecord
        try:
            record = JDExtractionRecord.objects.get(pk=jd_id)
        except JDExtractionRecord.DoesNotExist:
            return Response(
                {"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found.", "status": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = record.result or {}
        data = {
            "jd_id": jd_id,
            "title": result.get("title", ""),
            "company": result.get("company", ""),
            "location": result.get("location", ""),
            "is_remote": result.get("is_remote", False),
            "job_type": result.get("job_type", ""),
            "seniority": result.get("seniority"),
            "role_category": result.get("role_category", ""),
            "experience_min": result.get("experience_min"),
            "experience_max": result.get("experience_max"),
            "salary_min": result.get("salary_min"),
            "salary_max": result.get("salary_max"),
            "salary_currency": result.get("salary_currency", "USD"),
            "salary_type": result.get("salary_type", ""),
            "degree_requirement": result.get("degree_requirement"),
            "skills": result.get("skills", []),
            "description": record.combined_text or "",
            "source_url": record.source_url or "",
        }
        return Response({"success": True, "data": data})
