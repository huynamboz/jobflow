import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  IconMail, IconArrowDownLeft, IconArrowUpRight, IconAlertTriangle,
  IconCircleCheck, IconCircleX, IconRefresh, IconInbox, IconSend, IconUserCircle,
} from "@tabler/icons-react";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { addToast } from "@heroui/toast";

import { Card } from "@/components/ui/card";
import { mailService, type MailLog } from "@/services/mail.service";

type LogRow = MailLog & { employee: number; employee_name: string; match: number | null; job_title: string };
type Account = { employee: { id: number; name: string }; gmail_address: string; status: string; last_error: string; linked_at: string };
type TabKey = "sent" | "replies" | "bounces" | "accounts";

const TABS = [
  { key: "sent", dir: "out", bounce: "", icon: IconSend, tint: "text-primary bg-primary/10" },
  { key: "replies", dir: "in", bounce: "", icon: IconInbox, tint: "text-emerald-600 bg-emerald-500/10" },
  { key: "bounces", dir: "in", bounce: "1", icon: IconAlertTriangle, tint: "text-danger bg-danger/10" },
  { key: "accounts", dir: "", bounce: "", icon: IconUserCircle, tint: "text-violet-600 bg-violet-500/10" },
] as const;

const PAGE = 30;

function relTime(iso: string | null, t: TFunction): string {
  if (!iso) return t("relTime.never");
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 1 ? t("relTime.justNow") : m < 60 ? t("relTime.minutesAgo", { count: m }) : t("relTime.hoursAgo", { count: Math.round(m / 60) });
}

export default function MailPage() {
  const { t } = useTranslation("mail");
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("sent");
  const [rows, setRows] = useState<LogRow[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [counts, setCounts] = useState({ sent: 0, replies: 0, bounces: 0, accounts: 0 });
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadCounts = useCallback(async () => {
    try {
      const [s, r, b, a] = await Promise.all([
        mailService.logs({ direction: "out", page: 1 }),
        mailService.logs({ direction: "in", page: 1 }),
        mailService.logs({ direction: "in", is_bounce: "1", page: 1 }),
        mailService.accounts(),
      ]);
      setCounts({ sent: s.count, replies: r.count, bounces: b.count, accounts: a.length });
    } catch { /* counts are best-effort */ }
  }, []);

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
  useEffect(() => { void loadCounts(); }, [loadCounts]);
  useEffect(() => { mailService.syncStatus().then((d) => setLastSync(d.last_synced)).catch(() => {}); }, []);
  useEffect(() => { setPage(1); }, [tab]);

  const doSync = async () => {
    setSyncing(true);
    try {
      const d = await mailService.sync();
      setLastSync(d.last_synced);
      addToast({ title: d.new > 0 ? t("toast.newMail", { count: d.new }) : t("toast.upToDate"), color: d.new > 0 ? "success" : "default" });
      await Promise.all([load(), loadCounts()]);
    } catch {
      addToast({ title: t("toast.syncFailed"), color: "danger" });
    } finally { setSyncing(false); }
  };

  const pages = useMemo(() => Math.max(1, Math.ceil(count / PAGE)), [count]);
  const activeTab = TABS.find((x) => x.key === tab)!;

  return (
    <div className="flex flex-col gap-5">
      <style>{`@keyframes mailspin { to { transform: rotate(360deg); } }`}</style>

      {/* ── Hero header ── */}
      <Card padding={20} className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-4">
          <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
            <IconMail size={26} stroke={1.75} />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-foreground">{t("page.title")}</h1>
            <p className="truncate text-sm text-default-500">{t("page.subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 sm:ml-auto">
          <div className="text-right leading-tight">
            <div className="text-[11px] uppercase tracking-wide text-default-400">{t("page.lastSync")}</div>
            <div className="text-xs font-semibold tabular-nums text-default-600">{relTime(lastSync, t)}</div>
          </div>
          <Button color="primary" variant="shadow" size="sm" isLoading={syncing}
            onPress={() => void doSync()}
            startContent={!syncing && <IconRefresh size={16} style={{ animation: syncing ? "mailspin 0.8s linear infinite" : "none" }} />}>
            {syncing ? t("page.syncing") : t("page.syncNow")}
          </Button>
        </div>
      </Card>

      {/* ── Stat strip = tab selector ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {TABS.map((tabDef) => {
          const Icon = tabDef.icon;
          const active = tab === tabDef.key;
          const value = counts[tabDef.key];
          return (
            <Card key={tabDef.key} hoverable padding={16} onClick={() => setTab(tabDef.key)}
              className={`relative ${active ? "ring-2 ring-primary ring-offset-1" : ""}`}>
              <div className="flex items-center gap-3">
                <div className={`grid size-10 shrink-0 place-items-center rounded-xl ${tabDef.tint}`}>
                  <Icon size={20} stroke={1.75} />
                </div>
                <div className="min-w-0">
                  <div className="text-2xl font-bold tabular-nums leading-none text-foreground">{value}</div>
                  <div className="mt-1 truncate text-xs font-medium text-default-500">{t(`tabs.${tabDef.key}`)}</div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* ── Body ── */}
      <Card padding={0} className="overflow-hidden">
        {loading ? (
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-11 animate-pulse rounded-lg bg-default-100" />
            ))}
          </div>
        ) : tab === "accounts" ? (
          accounts.length === 0 ? (
            <EmptyState icon={<IconUserCircle size={28} stroke={1.5} />}
              title={t("empty.noAccountsTitle")}
              hint={t("empty.noAccountsHint")} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-default-50 text-left text-[11px] uppercase tracking-wide text-default-400">
                  <Th>{t("table.employee")}</Th><Th>{t("table.gmail")}</Th><Th>{t("table.status")}</Th><Th>{t("table.linked")}</Th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a, i) => (
                  <tr key={i} onClick={() => navigate(`/admin/employees/${a.employee.id}/info`)}
                    className="cursor-pointer border-t border-default-100 transition-colors hover:bg-default-50">
                    <Td className="font-medium text-foreground">{a.employee.name}</Td>
                    <Td className="text-default-600">{a.gmail_address}</Td>
                    <Td>
                      {a.status === "active"
                        ? <Chip size="sm" variant="flat" color="success" startContent={<IconCircleCheck size={13} />}>{t("chip.active")}</Chip>
                        : <Chip size="sm" variant="flat" color="danger" startContent={<IconCircleX size={13} />} title={a.last_error}>{t("chip.error")}</Chip>}
                    </Td>
                    <Td className="tabular-nums text-default-400">{new Date(a.linked_at).toLocaleDateString("vi-VN")}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : rows.length === 0 ? (
          <EmptyState icon={<activeTab.icon size={28} stroke={1.5} />}
            title={tab === "sent" ? t("empty.noSentTitle") : tab === "bounces" ? t("empty.noBouncesTitle") : t("empty.noRepliesTitle")}
            hint={tab === "sent"
              ? t("empty.noSentHint")
              : tab === "bounces"
                ? t("empty.noBouncesHint")
                : t("empty.noRepliesHint")} />
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-default-50 text-left text-[11px] uppercase tracking-wide text-default-400">
                  <Th className="w-10"> </Th><Th>{t("table.employee")}</Th><Th>{t("table.job")}</Th>
                  <Th>{tab === "sent" ? t("table.to") : t("table.from")}</Th><Th>{t("table.subject")}</Th><Th>{t("table.status")}</Th><Th>{t("table.time")}</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => navigate(`/admin/mail/${r.id}`)}
                    className="cursor-pointer border-t border-default-100 transition-colors hover:bg-default-50">
                    <Td>
                      <span className={`grid size-7 place-items-center rounded-lg ${
                        r.is_bounce ? "bg-danger/10 text-danger"
                          : r.direction === "in" ? "bg-emerald-500/10 text-emerald-600"
                            : "bg-default-100 text-default-500"}`}>
                        {r.is_bounce ? <IconAlertTriangle size={15} />
                          : r.direction === "in" ? <IconArrowDownLeft size={15} />
                            : <IconArrowUpRight size={15} />}
                      </span>
                    </Td>
                    <Td className="font-medium text-foreground">{r.employee_name}</Td>
                    <Td className="text-default-500">{r.job_title || "—"}</Td>
                    <Td className="text-default-500">{tab === "sent" ? r.to_addr : r.from_addr}</Td>
                    <Td className="max-w-[22ch] truncate text-default-700">{r.subject}</Td>
                    <Td>
                      {r.is_bounce
                        ? <Chip size="sm" variant="flat" color="danger">{t("chip.bounced")}</Chip>
                        : r.status === "failed"
                          ? <Chip size="sm" variant="flat" color="danger">{t("chip.failed")}</Chip>
                          : <Chip size="sm" variant="flat" color={r.direction === "in" ? "success" : "default"}>{r.status}</Chip>}
                    </Td>
                    <Td className="whitespace-nowrap tabular-nums text-default-400">{new Date(r.created_at).toLocaleString("vi-VN")}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
            {count > PAGE && (
              <div className="flex items-center justify-between border-t border-default-100 px-4 py-2.5 text-xs text-default-500">
                <span className="tabular-nums">{t("pagination.total", { count })}</span>
                <span className="flex items-center gap-3">
                  <Button size="sm" variant="flat" isDisabled={page <= 1} onPress={() => setPage((p) => p - 1)}>{t("common:actions.previous")}</Button>
                  <span className="tabular-nums">{t("pagination.pageOf", { page, pages })}</span>
                  <Button size="sm" variant="flat" isDisabled={page >= pages} onPress={() => setPage((p) => p + 1)}>{t("common:actions.next")}</Button>
                </span>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <th className={`px-4 py-2.5 font-bold ${className}`}>{children}</th>;
}
function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-2.5 align-middle ${className}`}>{children}</td>;
}
function EmptyState({ icon, title, hint }: { icon: React.ReactNode; title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="grid size-14 place-items-center rounded-2xl bg-default-100 text-default-400">{icon}</div>
      <div className="text-sm font-semibold text-foreground">{title}</div>
      <p className="max-w-xs text-xs leading-relaxed text-default-400">{hint}</p>
    </div>
  );
}
