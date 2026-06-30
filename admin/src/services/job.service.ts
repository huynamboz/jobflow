import { apiClient } from "@/lib/api-client";
import type { ApiSuccess } from "@/types/api.types";
import type { AdminPlatform, JDBatch, JDBatchDetail, JobDetail, JobListResponse } from "@/types/job.types";

export interface JobFilters {
  search?: string;
  platform?: string;
  seniority?: string;
  job_type?: string;
  is_active?: string; // "true" | "false" — active/inactive filter (server-side)
  page?: number;
  page_size?: number;
}

class JobService {
  async listJobs(filters: JobFilters = {}): Promise<JobListResponse> {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") params.set(k, String(v));
    });
    const res = await apiClient.get<JobListResponse>(`/admin/jobs/?${params}`);
    return res.data;
  }

  async listPlatforms(): Promise<AdminPlatform[]> {
    const res = await apiClient.get<ApiSuccess<AdminPlatform[]>>("/admin/platforms/");
    return res.data.data;
  }

  async getJob(id: number): Promise<JobDetail> {
    const res = await apiClient.get<ApiSuccess<JobDetail>>(`/admin/jobs/${id}/`);
    return res.data.data;
  }

  /** Verify one job on demand → returns the updated job (is_active, lifecycle,
   *  last_verified_at). Throws on UNSUPPORTED / VERIFY_FAILED. */
  async verifyJob(id: number): Promise<{ is_active: boolean; lifecycle: string; last_verified_at: string | null }> {
    const res = await apiClient.post<ApiSuccess<{ is_active: boolean; lifecycle: string; last_verified_at: string | null }>>(
      `/admin/jobs/${id}/verify/`,
    );
    return res.data.data;
  }

  async previewBatch(file: File): Promise<{ total: number; fields: string[]; sample: Record<string, unknown>[]; filename: string }> {
    const form = new FormData();
    form.append("file", file);
    const res = await apiClient.post<ApiSuccess<{ total: number; fields: string[]; sample: Record<string, unknown>[]; filename: string }>>(
      "/admin/jd/batches/preview/", form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  }

  async listBatches(): Promise<JDBatch[]> {
    const res = await apiClient.get<ApiSuccess<JDBatch[]>>("/admin/jd/batches/");
    return res.data.data;
  }

  async createBatch(file: File, fieldsConfig: string[], limit: number | null, workers = 3): Promise<JDBatch> {
    const form = new FormData();
    form.append("file", file);
    form.append("fields_config", JSON.stringify(fieldsConfig));
    if (limit != null) form.append("limit", String(limit));
    form.append("workers", String(workers));
    const res = await apiClient.post<ApiSuccess<JDBatch>>("/admin/jd/batches/", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data.data;
  }

  async getBatch(id: number, page = 1, pageSize = 50, status = ""): Promise<JDBatchDetail> {
    const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) p.set("status", status);
    const res = await apiClient.get<ApiSuccess<JDBatchDetail>>(`/admin/jd/batches/${id}/?${p}`);
    return res.data.data;
  }

  async cancelBatch(id: number): Promise<void> {
    await apiClient.post(`/admin/jd/batches/${id}/cancel/`);
  }

  async resumeBatch(id: number, workers?: number): Promise<void> {
    await apiClient.post(`/admin/jd/batches/${id}/resume/`, workers != null ? { workers } : {});
  }

  async getBatchRecord(batchId: number, recordId: number): Promise<import("@/types/job.types").JDBatchRecord> {
    const res = await apiClient.get<ApiSuccess<import("@/types/job.types").JDBatchRecord>>(`/admin/jd/batches/${batchId}/records/${recordId}/`);
    return res.data.data;
  }

  async exportJDs(filters: { role_category?: string } = {}): Promise<void> {
    const params = new URLSearchParams();
    if (filters.role_category) params.set("role_category", filters.role_category);
    const res = await apiClient.get(`/admin/jd/export/?${params}`, { responseType: "blob" });
    _downloadBlob(res.data as Blob, "jds_extracted.json");
  }
}

function _downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const jobService = new JobService();
