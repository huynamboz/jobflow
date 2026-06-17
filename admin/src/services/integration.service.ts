import { apiClient } from "@/lib/api-client";

export interface IntegrationState {
  platform: string;
  name: string;
  connected: boolean;
  status: "connected" | "error" | null;
  last_error: string;
  last_sent_at: string | null;
  updated_at: string | null;
  /** Non-secret config values echoed back from the server. */
  config: Record<string, string>;
  /** Secret field keys that already hold a saved value. */
  secrets_set: string[];
}

class IntegrationService {
  async list(): Promise<IntegrationState[]> {
    const r = await apiClient.get<IntegrationState[]>("/admin/integrations/");
    return r.data;
  }

  /** Connect or update a platform. Blank secret fields keep their saved value. */
  async save(platform: string, config: Record<string, string>): Promise<IntegrationState> {
    const r = await apiClient.post<IntegrationState>(`/admin/integrations/${platform}/`, config);
    return r.data;
  }

  async disconnect(platform: string): Promise<void> {
    await apiClient.delete(`/admin/integrations/${platform}/`);
  }

  /** Send a real test message through the saved config. */
  async test(platform: string): Promise<{ ok: boolean; last_sent_at: string }> {
    const r = await apiClient.post(`/admin/integrations/${platform}/test/`, {});
    return r.data as { ok: boolean; last_sent_at: string };
  }

  // --- Zalo QR login (zca-js sidecar) ---
  async zaloLoginStart(): Promise<ZaloQrStatus> {
    const r = await apiClient.post<ZaloQrStatus>("/admin/integrations/zalo/login-qr/start/", {});
    return r.data;
  }
  async zaloLoginStatus(): Promise<ZaloQrStatus> {
    const r = await apiClient.get<ZaloQrStatus>("/admin/integrations/zalo/login-qr/status/");
    return r.data;
  }
}

export type ZaloQrState =
  | "idle"
  | "starting"
  | "waiting_scan"
  | "scanned"
  | "logged_in"
  | "expired"
  | "declined"
  | "error";

export interface ZaloQrStatus {
  state: ZaloQrState;
  /** base64 PNG (no data: prefix) while waiting for a scan. */
  image: string | null;
  user: { name: string; avatar: string } | null;
  error: string | null;
  loggedIn: boolean;
}

export const integrationService = new IntegrationService();
