import { apiClient } from "@/lib/api-client";
import type {
  ScheduleCommand,
  ScheduleConfig,
  ScheduleHistory,
  ScheduleLiveLog,
} from "@/types/schedule.types";

const BASE = "/admin/schedule";

class ScheduleService {
  async getConfig(cmd: ScheduleCommand): Promise<ScheduleConfig> {
    const r = await apiClient.get(`${BASE}/${cmd}/`);
    return r.data.data;
  }
  async updateConfig(cmd: ScheduleCommand, patch: Partial<ScheduleConfig>): Promise<ScheduleConfig> {
    const r = await apiClient.put(`${BASE}/${cmd}/`, patch);
    return r.data.data;
  }
  async start(cmd: ScheduleCommand): Promise<ScheduleConfig> {
    const r = await apiClient.post(`${BASE}/${cmd}/start/`);
    return r.data.data;
  }
  async stop(cmd: ScheduleCommand): Promise<ScheduleConfig> {
    const r = await apiClient.post(`${BASE}/${cmd}/stop/`);
    return r.data.data;
  }
  async tailLog(cmd: ScheduleCommand, since: number = 0): Promise<ScheduleLiveLog> {
    const r = await apiClient.get(`${BASE}/${cmd}/live-log/`, { params: { since } });
    return r.data.data;
  }
  async getHistory(cmd: ScheduleCommand, limit: number = 20): Promise<ScheduleHistory> {
    const r = await apiClient.get(`${BASE}/${cmd}/history/`, { params: { limit } });
    return r.data.data;
  }
  async getLogFile(cmd: ScheduleCommand, name: string): Promise<{ name: string; text: string; size_bytes: number }> {
    const r = await apiClient.get(`${BASE}/${cmd}/log-file/`, { params: { name } });
    return r.data.data;
  }
}

export const scheduleService = new ScheduleService();
