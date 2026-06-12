import { apiClient } from "@/lib/api-client";

export interface CredentialStatus {
  linked: boolean;
  employee?: number;
  gmail_address?: string;
  status?: "active" | "error";
  last_error?: string;
  linked_at?: string;
}
export interface MailLog {
  id: number; direction: "out" | "in"; from_addr: string; to_addr: string;
  subject: string; body_text: string; is_bounce: boolean; cv_attached: boolean;
  status: string; error: string; created_at: string;
}
export interface AppNotification {
  id: number; type: "mail_reply" | "mail_bounce"; title: string;
  body_preview: string; link_url: string; employee: number | null;
  read_at: string | null; created_at: string;
}

class MailService {
  async credentialStatus(employee: number): Promise<CredentialStatus> {
    const r = await apiClient.get<CredentialStatus>("/admin/mail/credentials/", { params: { employee } });
    return r.data;
  }
  async link(employee: number, gmail_address: string, app_password: string): Promise<CredentialStatus> {
    const r = await apiClient.post<CredentialStatus>("/admin/mail/credentials/", { employee, gmail_address, app_password });
    return r.data;
  }
  async unlink(employee: number): Promise<void> {
    await apiClient.delete(`/admin/mail/credentials/${employee}/`);
  }
  async sendApply(match: number, to: string, subject: string, body: string) {
    const r = await apiClient.post("/admin/mail/send-apply/", { match, to, subject, body });
    return r.data as { ok: boolean; email_log: number; match_status: string; cv_attached: boolean };
  }
  async thread(match: number): Promise<MailLog[]> {
    const r = await apiClient.get<MailLog[]>("/admin/mail/thread/", { params: { match } });
    return r.data;
  }
  async notifications(page = 1) {
    const r = await apiClient.get("/admin/mail/notifications/", { params: { page } });
    return r.data as { count: number; unread: number; results: AppNotification[] };
  }
  async unreadCount(): Promise<number> {
    const r = await apiClient.get<{ unread: number }>("/admin/mail/notifications/unread-count/");
    return r.data.unread;
  }
  async markRead(id: number): Promise<void> {
    await apiClient.post(`/admin/mail/notifications/${id}/read/`, {});
  }
  async recentReplies() {
    const r = await apiClient.get("/admin/mail/notifications/recent-replies/");
    return r.data as { employee: { id: number; name: string }; title: string; snippet: string; created_at: string; link_url: string }[];
  }

  async logs(params: { direction?: string; status?: string; is_bounce?: string; employee?: number; page?: number } = {}) {
    const r = await apiClient.get("/admin/mail/logs/", { params });
    return r.data as { count: number; page: number; results: (MailLog & { employee: number; employee_name: string; match: number | null; job_title: string })[] };
  }
  async accounts() {
    const r = await apiClient.get("/admin/mail/accounts/");
    return r.data as { employee: { id: number; name: string }; gmail_address: string; status: string; last_error: string; linked_at: string }[];
  }
}
export const mailService = new MailService();
