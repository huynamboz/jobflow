import { apiClient } from "@/lib/api-client";
import type { StaffingDashboard } from "@/types/staffing-dashboard.types";

class StaffingDashboardService {
  async get(): Promise<StaffingDashboard> {
    const res = await apiClient.get<{ success: boolean; data: StaffingDashboard }>(
      "/admin/staffing/dashboard/",
    );
    return res.data.data;
  }
}

export const staffingDashboardService = new StaffingDashboardService();
