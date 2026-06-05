import { apiClient } from "@/lib/api-client";
import type { EmployeeJobMatch, MatchStatus, PipelineKpi } from "@/types/match.types";

interface ListParams {
  employee?: number;
  job?: number;
  status?: MatchStatus;
  assigned_to?: number;
  page?: number;
}

interface ListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: EmployeeJobMatch[];
}

interface UpdatePayload {
  status?: MatchStatus;
  notes?: string;
  assigned_to?: number | null;
  // Set true to proceed past the duplicate-apply warning (US3).
  confirm_duplicate?: boolean;
}

export interface DuplicateApplyFrontman {
  employee_id: number;
  employee_name: string;
  match_id: number;
  status: MatchStatus;
}

export interface DuplicateApplyError {
  code: "DUPLICATE_APPLY";
  message: string;
  frontman: DuplicateApplyFrontman;
}

class MatchService {
  async list(params: ListParams = {}): Promise<ListResponse> {
    const res = await apiClient.get<ListResponse>("/admin/matches/", { params });
    return res.data;
  }

  async update(id: number, payload: UpdatePayload): Promise<EmployeeJobMatch> {
    const res = await apiClient.patch<EmployeeJobMatch>(`/admin/matches/${id}/`, payload);
    return res.data;
  }

  async remove(id: number): Promise<void> {
    await apiClient.delete<void>(`/admin/matches/${id}/`);
  }

  async kpi(): Promise<PipelineKpi> {
    const res = await apiClient.get<{ success: boolean; data: PipelineKpi }>(
      "/admin/pipeline/kpi/",
    );
    return res.data.data;
  }
}

export const matchService = new MatchService();
