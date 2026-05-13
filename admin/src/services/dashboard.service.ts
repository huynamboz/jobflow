import { apiClient } from "@/lib/api-client";
import type {
  CatalogComposition,
  FreshnessActivity,
  KpiSnapshot,
  LabelingSnapshot,
  ModelSnapshot,
  OpsHealth,
} from "@/types/dashboard.types";

const BASE = "/admin/dashboard";

class DashboardService {
  async getKpi(): Promise<KpiSnapshot> {
    const r = await apiClient.get(`${BASE}/kpi/`);
    return r.data.data;
  }

  async getCatalog(): Promise<CatalogComposition> {
    const r = await apiClient.get(`${BASE}/catalog/`);
    return r.data.data;
  }

  async getFreshness(opts?: { daysAdded?: number; daysOutcomes?: number }): Promise<FreshnessActivity> {
    const r = await apiClient.get(`${BASE}/freshness/`, {
      params: {
        days_added: opts?.daysAdded ?? 30,
        days_outcomes: opts?.daysOutcomes ?? 14,
      },
    });
    return r.data.data;
  }

  async getOps(opts?: { recentRunsLimit?: number }): Promise<OpsHealth> {
    const r = await apiClient.get(`${BASE}/ops/`, {
      params: { recent_runs_limit: opts?.recentRunsLimit ?? 20 },
    });
    return r.data.data;
  }

  async getLabeling(): Promise<LabelingSnapshot> {
    const r = await apiClient.get(`${BASE}/labeling/`);
    return r.data.data;
  }

  async getModel(): Promise<ModelSnapshot> {
    const r = await apiClient.get(`${BASE}/model/`);
    return r.data.data;
  }
}

export const dashboardService = new DashboardService();
