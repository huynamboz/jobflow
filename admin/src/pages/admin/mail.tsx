import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconMail, IconArrowDownLeft, IconArrowUpRight, IconAlertTriangle, IconCircleCheck, IconCircleX } from "@tabler/icons-react";

import { mailService, type MailLog } from "@/services/mail.service";

const T = {
  ink: "var(--ink, #0f172a)", ink2: "#334155", ink3: "#64748b", ink4: "#94a3b8",
  line: "var(--line, #e2e8f0)", surface: "#fff", surface2: "#f8fafc",
  accent: "#167a7a", accent50: "#e8f4f4", success: "#16a34a", danger: "#dc2626", warning: "#c2410c",
};

type LogRow = MailLog & { employee: number; employee_name: string; match: number | null; job_title: string };
type Account = { employee: { id: number; name: string }; gmail_address: string; status: string; last_error: string; linked_at: string };

const TABS = [
  { key: "sent", label: "Sent", dir: "out", bounce: "" },
  { key: "replies", label: "Replies", dir: "in", bounce: "" },
  { key: "bounces", label: "Bounces", dir: "in", bounce: "1" },
  { key: "accounts", label: "Linked accounts", dir: "", bounce: "" },
] as const;

export default function MailPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("sent");
  const [rows, setRows] = useState<LogRow[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "accounts") {
        setAccounts(await mailService.accounts());
      } else {
        const t = TABS.find((x) => x.key === tab)!;
        const d = await mailService.logs({ direction: t.dir, is_bounce: t.bounce || undefined, page });
        setRows(d.results); setCount(d.count);
      }
    } finally { setLoading(false); }
  }, [tab, page]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPage(1); }, [tab]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <IconMail size={22} style={{ color: T.accent }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: T.ink, letterSpacing: "-0.02em" }}>Mail</h1>
        <span style={{ fontSize: 13, color: T.ink3 }}>Application emails, recruiter replies, and linked accounts.</span>
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        {TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            style={{ padding: "6px 14px", borderRadius: 999, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                     border: `1px solid ${tab === t.key ? T.accent : T.line}`,
                     background: tab === t.key ? T.accent : T.surface, color: tab === t.key ? "#fff" : T.ink2 }}>
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ border: `1px solid ${T.line}`, borderRadius: 14, overflow: "hidden", background: T.surface }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: T.ink4 }}>Loading…</div>
        ) : tab === "accounts" ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr style={{ background: T.surface2, color: T.ink3, textAlign: "left" }}>
              <th style={th}>Employee</th><th style={th}>Gmail</th><th style={th}>Status</th><th style={th}>Linked</th>
            </tr></thead>
            <tbody>
              {accounts.length === 0 && <tr><td colSpan={4} style={{ ...td, textAlign: "center", color: T.ink4 }}>No linked accounts</td></tr>}
              {accounts.map((a, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${T.line}`, cursor: "pointer" }}
                    onClick={() => navigate(`/admin/employees/${a.employee.id}`)}>
                  <td style={td}>{a.employee.name}</td>
                  <td style={td}>{a.gmail_address}</td>
                  <td style={td}>
                    {a.status === "active"
                      ? <span style={{ color: T.success, display: "inline-flex", alignItems: "center", gap: 4 }}><IconCircleCheck size={14} />active</span>
                      : <span style={{ color: T.danger, display: "inline-flex", alignItems: "center", gap: 4 }} title={a.last_error}><IconCircleX size={14} />error</span>}
                  </td>
                  <td style={{ ...td, color: T.ink4 }}>{new Date(a.linked_at).toLocaleDateString("vi-VN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr style={{ background: T.surface2, color: T.ink3, textAlign: "left" }}>
                <th style={th}></th><th style={th}>Employee</th><th style={th}>Job</th>
                <th style={th}>{tab === "sent" ? "To" : "From"}</th><th style={th}>Subject</th>
                <th style={th}>Status</th><th style={th}>Time</th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={7} style={{ ...td, textAlign: "center", color: T.ink4 }}>No emails</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} style={{ borderTop: `1px solid ${T.line}`, cursor: r.match ? "pointer" : "default" }}
                      onClick={() => r.match && navigate(`/admin/employees/${r.employee}?match=${r.match}`)}>
                    <td style={td}>
                      {r.is_bounce ? <IconAlertTriangle size={15} style={{ color: T.danger }} />
                        : r.direction === "in" ? <IconArrowDownLeft size={15} style={{ color: T.accent }} />
                        : <IconArrowUpRight size={15} style={{ color: T.ink4 }} />}
                    </td>
                    <td style={td}>{r.employee_name}</td>
                    <td style={{ ...td, color: T.ink3 }}>{r.job_title || "—"}</td>
                    <td style={{ ...td, color: T.ink3 }}>{tab === "sent" ? r.to_addr : r.from_addr}</td>
                    <td style={td}>{r.subject}</td>
                    <td style={td}>
                      {r.is_bounce ? <span style={{ color: T.danger }}>bounced</span>
                        : r.status === "failed" ? <span style={{ color: T.danger }}>failed</span>
                        : <span style={{ color: T.ink3 }}>{r.status}</span>}
                    </td>
                    <td style={{ ...td, color: T.ink4, whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleString("vi-VN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {count > 30 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", borderTop: `1px solid ${T.line}`, fontSize: 12.5, color: T.ink3 }}>
                <span>{count} total</span>
                <span style={{ display: "flex", gap: 8 }}>
                  <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} style={pbtn(page <= 1)}>Prev</button>
                  <span>page {page} / {Math.ceil(count / 30)}</span>
                  <button type="button" disabled={page >= Math.ceil(count / 30)} onClick={() => setPage((p) => p + 1)} style={pbtn(page >= Math.ceil(count / 30))}>Next</button>
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "10px 14px", fontSize: 11.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" };
const td: React.CSSProperties = { padding: "10px 14px", color: T.ink2 };
const pbtn = (disabled: boolean): React.CSSProperties => ({
  padding: "4px 10px", borderRadius: 8, border: `1px solid ${T.line}`, background: "#fff",
  cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.4 : 1, color: T.ink2,
});
