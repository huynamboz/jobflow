"""Admin-only job management endpoints (/api/admin/...)."""

import json

from django.db.models import Count, F
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Company, Job, JobSkill, Platform
from apps.jobs.serializers import (
    CompanySerializer,
    JobDetailSerializer,
    JobListSerializer,
    PlatformSerializer,
)
from apps.users.permissions import IsAdmin


# --- JD Batch Extraction ---
# (The single-JD extract/save admin page was removed; JD batch below stays.)

def _batch_to_dict(batch) -> dict:
    return {
        "id": batch.id,
        "file_path": batch.file_path,
        "fields_config": batch.fields_config,
        "status": batch.status,
        "total": batch.total,
        "done_count": batch.done_count,
        "error_count": batch.error_count,
        "workers": batch.workers,
        "created_at": batch.created_at.isoformat(),
    }


def _record_to_dict(record, include_result: bool = False) -> dict:
    d = {
        "id": record.id,
        "index": record.index,
        "status": record.status,
        "error_msg": record.error_msg,
        "title": (record.raw_data or {}).get("title", ""),
        "company": (record.raw_data or {}).get("company", ""),
        "source_url": record.source_url,
    }
    if include_result:
        d["result"] = record.result
        d["combined_text"] = record.combined_text
    return d


def _parse_jsonl(file_obj, limit=None):
    """Read a JSONL file object, return (records list, fields set, total count)."""
    import json as _json
    records = []
    fields: set[str] = set()
    total = 0
    idx = 0
    for raw in file_obj:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        fields.update(obj.keys())
        total += 1
        if limit is None or idx < limit:
            records.append((idx, obj))
        idx += 1
    return records, fields, total


class JDBatchPreviewView(APIView):
    permission_classes = [IsAdmin]
    parser_classes = [__import__("rest_framework.parsers", fromlist=["MultiPartParser"]).MultiPartParser]

    @extend_schema(tags=["Admin"])
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"success": False, "error": {"code": "INVALID_INPUT", "message": "file is required.", "status": 400}}, status=400)

        try:
            records, fields, total = _parse_jsonl(upload, limit=None)
        except Exception as exc:
            return Response({"success": False, "error": {"code": "READ_ERROR", "message": str(exc), "status": 400}}, status=400)

        sample = [obj for _, obj in records[:5]]
        return Response({
            "success": True,
            "data": {
                "total": total,
                "fields": sorted(fields),
                "sample": sample,
                "filename": upload.name,
            },
        })


class JDBatchListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def get(self, request):
        from apps.jobs.models import JDExtractionBatch
        batches = JDExtractionBatch.objects.all()[:20]
        return Response({"success": True, "data": [_batch_to_dict(b) for b in batches]})

    @extend_schema(tags=["Admin"])
    def post(self, request):
        import json as _json
        from rest_framework.parsers import MultiPartParser, JSONParser
        from apps.jobs.models import JDExtractionBatch, JDExtractionRecord
        from apps.jobs.services.jd_batch_processor import start_batch, content_hash

        upload = request.FILES.get("file")
        # fields_config comes as JSON string in multipart or list in JSON body
        raw_fields = request.data.get("fields_config") or "[]"
        if isinstance(raw_fields, str):
            try:
                fields_config = _json.loads(raw_fields)
            except _json.JSONDecodeError:
                fields_config = []
        else:
            fields_config = list(raw_fields)

        limit_raw = request.data.get("limit")
        limit = int(limit_raw) if limit_raw not in (None, "", "null") else None

        workers_raw = request.data.get("workers")
        workers = max(1, min(20, int(workers_raw))) if workers_raw not in (None, "", "null") else 3

        if not upload:
            return Response({"success": False, "error": {"code": "INVALID_INPUT", "message": "file is required.", "status": 400}}, status=400)
        if not fields_config:
            return Response({"success": False, "error": {"code": "INVALID_INPUT", "message": "fields_config required.", "status": 400}}, status=400)

        batch = JDExtractionBatch.objects.create(
            file_path=upload.name,
            fields_config=fields_config,
            workers=workers,
        )

        records_to_create = []
        try:
            all_records, _, _ = _parse_jsonl(upload, limit=limit)
            for idx, obj in all_records:
                parts = [f"{f}: {obj[f]}" for f in fields_config if obj.get(f)]
                combined = "\n".join(parts)
                records_to_create.append(JDExtractionRecord(
                    batch=batch,
                    index=idx,
                    raw_data=obj,
                    source_url=obj.get("source_url") or "",
                    combined_text=combined,
                    content_hash=content_hash(combined),
                ))
        except Exception as exc:
            batch.delete()
            return Response({"success": False, "error": {"code": "READ_ERROR", "message": str(exc), "status": 400}}, status=400)

        JDExtractionRecord.objects.bulk_create(records_to_create, batch_size=500)
        batch.total = len(records_to_create)
        batch.save(update_fields=["total"])

        start_batch(batch.id, workers=workers)

        return Response({"success": True, "data": _batch_to_dict(batch)}, status=status.HTTP_201_CREATED)


class JDBatchDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def get(self, request, pk):
        from apps.jobs.models import JDExtractionBatch, JDExtractionRecord

        try:
            batch = JDExtractionBatch.objects.get(pk=pk)
        except JDExtractionBatch.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Batch not found.", "status": 404}}, status=404)

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 50))
        status_filter = request.query_params.get("status", "")

        records_qs = JDExtractionRecord.objects.filter(batch=batch)
        if status_filter:
            records_qs = records_qs.filter(status=status_filter)

        total_records = records_qs.count()
        offset = (page - 1) * page_size
        records = records_qs[offset: offset + page_size]

        return Response({
            "success": True,
            "data": {
                "batch": _batch_to_dict(batch),
                "records": [_record_to_dict(r) for r in records],
                "total_records": total_records,
                "page": page,
                "page_size": page_size,
            },
        })


class JDBatchCancelView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def post(self, request, pk):
        from apps.jobs.models import JDExtractionBatch, JDExtractionRecord
        from apps.jobs.services.jd_batch_processor import cancel_batch

        try:
            batch = JDExtractionBatch.objects.get(pk=pk)
        except JDExtractionBatch.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Batch not found.", "status": 404}}, status=404)

        if batch.status != JDExtractionBatch.STATUS_RUNNING:
            return Response({"success": False, "error": {"code": "INVALID_STATE", "message": "Batch is not running.", "status": 400}}, status=400)

        cancel_batch(batch.id)
        # Force-cancel via DB — handles case where thread died (e.g. server restart)
        JDExtractionBatch.objects.filter(id=pk).update(status=JDExtractionBatch.STATUS_CANCELLED)
        JDExtractionRecord.objects.filter(batch_id=pk, status=JDExtractionRecord.STATUS_PROCESSING).update(
            status=JDExtractionRecord.STATUS_PENDING
        )
        return Response({"success": True})


class JDBatchResumeView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def post(self, request, pk):
        from apps.jobs.models import JDExtractionBatch
        from apps.jobs.services.jd_batch_processor import start_batch

        try:
            batch = JDExtractionBatch.objects.get(pk=pk)
        except JDExtractionBatch.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Batch not found.", "status": 404}}, status=404)

        if batch.status == JDExtractionBatch.STATUS_RUNNING:
            return Response({"success": False, "error": {"code": "INVALID_STATE", "message": "Batch is already running.", "status": 400}}, status=400)

        # Reset error and stuck-processing records to pending so they get retried
        from apps.jobs.models import JDExtractionRecord
        error_reset = JDExtractionRecord.objects.filter(
            batch_id=pk, status=JDExtractionRecord.STATUS_ERROR,
        ).update(status=JDExtractionRecord.STATUS_PENDING, error_msg="")
        JDExtractionRecord.objects.filter(
            batch_id=pk, status=JDExtractionRecord.STATUS_PROCESSING,
        ).update(status=JDExtractionRecord.STATUS_PENDING)
        # Deduct from batch error_count so progress bar starts correctly
        if error_reset:
            JDExtractionBatch.objects.filter(id=pk).update(error_count=F("error_count") - error_reset)

        pending = JDExtractionRecord.objects.filter(batch_id=pk, status=JDExtractionRecord.STATUS_PENDING).count()
        if pending == 0:
            return Response({"success": False, "error": {"code": "NO_PENDING", "message": "No pending or failed records to process.", "status": 400}}, status=400)

        workers_raw = request.data.get("workers")
        workers = max(1, min(20, int(workers_raw))) if workers_raw not in (None, "", "null") else batch.workers
        if workers != batch.workers:
            JDExtractionBatch.objects.filter(id=pk).update(workers=workers)

        start_batch(batch.id, workers=workers)
        return Response({"success": True, "pending": pending})


class JDBatchRecordDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def get(self, request, pk, record_pk):
        from apps.jobs.models import JDExtractionRecord

        try:
            record = JDExtractionRecord.objects.get(pk=record_pk, batch_id=pk)
        except JDExtractionRecord.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Record not found.", "status": 404}}, status=404)

        return Response({"success": True, "data": _record_to_dict(record, include_result=True)})


# --- Platforms ---

class AdminPlatformListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: PlatformSerializer(many=True)}, tags=["Admin"])
    def get(self, request):
        platforms = Platform.objects.annotate(job_count=Count("jobs")).order_by("name")
        return Response({"success": True, "data": PlatformSerializer(platforms, many=True).data})


class AdminPlatformDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: PlatformSerializer}, tags=["Admin"])
    def get(self, request, pk):
        try:
            platform = Platform.objects.annotate(job_count=Count("jobs")).get(pk=pk)
        except Platform.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Platform not found.", "status": 404}}, status=404)
        return Response({"success": True, "data": PlatformSerializer(platform).data})

    @extend_schema(request=PlatformSerializer, responses={200: PlatformSerializer}, tags=["Admin"])
    def patch(self, request, pk):
        try:
            platform = Platform.objects.get(pk=pk)
        except Platform.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Platform not found.", "status": 404}}, status=404)
        serializer = PlatformSerializer(platform, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": serializer.data})


# --- Companies ---

class AdminCompanyListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: CompanySerializer(many=True)}, tags=["Admin"])
    def get(self, request):
        qs = Company.objects.annotate(job_count=Count("jobs")).prefetch_related("platforms")
        platform = request.query_params.get("platform")
        search = request.query_params.get("search")
        if platform:
            qs = qs.filter(platform_profiles__platform__slug=platform)
        if search:
            qs = qs.filter(name__icontains=search)
        return Response({"success": True, "data": CompanySerializer(qs[:100], many=True).data})


class AdminCompanyDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: CompanySerializer}, tags=["Admin"])
    def get(self, request, pk):
        try:
            company = Company.objects.annotate(job_count=Count("jobs")).prefetch_related("platforms").get(pk=pk)
        except Company.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Company not found.", "status": 404}}, status=404)
        return Response({"success": True, "data": CompanySerializer(company).data})


# --- Jobs ---

class AdminJobListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: JobListSerializer(many=True)}, tags=["Admin"])
    def get(self, request):
        qs = Job.objects.select_related("company", "platform")
        # Filters
        platform = request.query_params.get("platform")
        company_id = request.query_params.get("company")
        seniority = request.query_params.get("seniority")
        search = request.query_params.get("search")
        is_active = request.query_params.get("is_active")

        if platform:
            qs = qs.filter(platform__slug=platform)
        if company_id:
            qs = qs.filter(company_id=company_id)
        if seniority is not None:
            qs = qs.filter(seniority=seniority)
        if search:
            qs = qs.filter(title__icontains=search)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        offset = (page - 1) * page_size
        total = qs.count()

        return Response({
            "success": True,
            "data": JobListSerializer(qs[offset:offset + page_size], many=True).data,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


class AdminJobDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: JobDetailSerializer}, tags=["Admin"])
    def get(self, request, pk):
        try:
            job = Job.objects.select_related("company", "platform").prefetch_related("job_skills__skill").get(pk=pk)
        except Job.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found.", "status": 404}}, status=404)
        return Response({"success": True, "data": JobDetailSerializer(job).data})

    @extend_schema(tags=["Admin"])
    def patch(self, request, pk):
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found.", "status": 404}}, status=404)

        # Allow updating is_active, seniority, job_type
        for field in ("is_active", "seniority", "job_type"):
            if field in request.data:
                setattr(job, field, request.data[field])
        job.save()
        return Response({"success": True, "data": JobListSerializer(job).data})

    @extend_schema(tags=["Admin"])
    def delete(self, request, pk):
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            return Response({"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found.", "status": 404}}, status=404)
        job.is_active = False
        job.save()
        return Response({"success": True, "message": "Job deactivated."})


class JDExportView(APIView):
    """GET /api/admin/jd/export/ — Download latest JD extraction results as JSON."""
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Admin"])
    def get(self, request):
        from apps.jobs.models import Job, JobSkill, JDExtractionRecord

        role_filter = request.query_params.get("role_category", "")

        # Build url → Job.id mapping
        url_to_job: dict[str, int] = {}
        for j in Job.objects.filter(is_active=True).only("id", "source_url"):
            if j.source_url:
                url_to_job[j.source_url] = j.id

        # Fetch all done JDExtractionRecords, deduplicate by source_url (keep latest)
        seen_urls: set[str] = set()
        seen_no_url: set[int] = set()
        records = []
        for rec in (
            JDExtractionRecord.objects
            .filter(status=JDExtractionRecord.STATUS_DONE)
            .exclude(result=None)
            .order_by("-id")  # latest first for dedup
            .only("id", "source_url", "result")
        ):
            result = rec.result or {}
            role = result.get("role_category") or "other"

            if role_filter and role != role_filter:
                continue

            # Dedup by source_url (or record id if no url)
            if rec.source_url:
                if rec.source_url in seen_urls:
                    continue
                seen_urls.add(rec.source_url)
            else:
                if rec.id in seen_no_url:
                    continue
                seen_no_url.add(rec.id)

            job_id = url_to_job.get(rec.source_url) if rec.source_url else None
            records.append((job_id, result))

        # Fetch job titles for matched jobs
        matched_ids = [jid for jid, _ in records if jid is not None]
        title_map: dict[int, str] = dict(
            Job.objects.filter(id__in=matched_ids).values_list("id", "title")
        )

        output = []
        for job_id, result in records:
            output.append({
                "job_id":              job_id,
                "title":               title_map.get(job_id, result.get("title", "")),
                "role_category":       result.get("role_category") or "other",
                "seniority":           result.get("seniority", 2),
                "is_remote":           bool(result.get("is_remote", False)),
                "experience_min":      result.get("experience_min", 0) or 0,
                "experience_max":      result.get("experience_max"),
                "degree_requirement":  result.get("degree_requirement", 0) or 0,
                "salary_usd_annual_min": result.get("salary_usd_annual_min", 0) or 0,
                "salary_usd_annual_max": result.get("salary_usd_annual_max", 0) or 0,
                "skills":              result.get("skills") or [],
            })

        payload = json.dumps(output, ensure_ascii=False, indent=2)
        return HttpResponse(
            payload,
            content_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="jds_extracted.json"'},
        )
