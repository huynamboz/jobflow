import { apiClient } from "@/lib/api-client";
import type {
  BulkUploadResponse,
  Employee,
  EmployeeListResponse,
  EmployeeStatus,
} from "@/types/employee.types";

interface ListParams {
  status?: EmployeeStatus;
  seniority?: number;
  search?: string;
  page?: number;
}

const PARSE_TIMEOUT = 120_000;

class EmployeeService {
  async list(params: ListParams = {}): Promise<EmployeeListResponse> {
    const res = await apiClient.get<EmployeeListResponse>("/admin/employees/", { params });
    return res.data;
  }

  async get(id: number): Promise<Employee> {
    const res = await apiClient.get<Employee>(`/admin/employees/${id}/`);
    return res.data;
  }

  async create(payload: Partial<Employee>): Promise<Employee> {
    const res = await apiClient.post<Employee>("/admin/employees/", payload);
    return res.data;
  }

  async update(id: number, payload: Partial<Employee>): Promise<Employee> {
    const res = await apiClient.patch<Employee>(`/admin/employees/${id}/`, payload);
    return res.data;
  }

  async remove(id: number): Promise<void> {
    await apiClient.delete<void>(`/admin/employees/${id}/`);
  }

  async bulkUpload(files: File[]): Promise<BulkUploadResponse> {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await apiClient.post<BulkUploadResponse>(
      "/admin/employees/bulk_upload/",
      form,
      {
        timeout: PARSE_TIMEOUT,
        headers: { "Content-Type": "multipart/form-data" },
      },
    );
    return res.data;
  }

  async rescore(id: number): Promise<void> {
    await apiClient.post<void>(`/admin/employees/${id}/rescore/`, {});
  }

  /** Refresh job matches against the current catalog (no CV re-parse / no LLM).
   *  Synchronous — resolves once re-matching is done. Generous timeout so the
   *  first call after a cold GNN-engine load (which warms it) isn't cut off;
   *  subsequent calls take a couple of seconds. */
  async rematch(id: number): Promise<{ matches_total: number; matches_created: number; matches_skipped: number }> {
    const res = await apiClient.post<{ success: boolean; data: { matches_total: number; matches_created: number; matches_skipped: number } }>(
      `/admin/employees/${id}/rematch/`, {}, { timeout: 120_000 },
    );
    return res.data.data;
  }
}

export const employeeService = new EmployeeService();
