import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { addToast } from "@heroui/toast";
import {
  IconArrowBackUp, IconArrowForwardUp, IconArchive, IconCalendarEvent,
  IconClock, IconCheck, IconAlertTriangle, IconRefresh, IconMail, IconLoader2,
} from "@tabler/icons-react";

import { Button, useReveal } from "@/components/ui";
import { cn } from "@/lib/utils";
import { mailService, type MailLog, type MailLogDetail } from "@/services/mail.service";

type SentLog = MailLog & { employee: number; employee_name: string; match: number | null; job_title: string };
type Status = "replied" | "awaiting" | "bounced";
type Thread = { log: SentLog; status: Status };
type Tab = "all" | Status;

const STATUS: Record<Status, { labelKey: string; color: string; bg: string; Icon: typeof IconClock }> = {
  replied: { labelKey: "box.status.replied", color: "#1F9E6E", bg: "#E7F6EF", Icon: IconArrowBackUp },
  awaiting: { labelKey: "box.status.awaiting", color: "#C77700", bg: "#FBF1DC", Icon: IconClock },
  bounced: { labelKey: "box.status.bounced", color: "#E0533A", bg: "#FCEDEA", Icon: IconAlertTriangle },
};

const TABS: Tab[] = ["all", "replied", "awaiting", "bounced"];

function relTime(iso: string | null, t: TFunction): string {
  if (!iso) return "—";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return t("relTime.justNow");
  if (m < 60) return t("relTime.minutesAgo", { count: m });
  const h = Math.round(m / 60);
  if (h < 24) return t("relTime.hoursAgo", { count: h });
  return t("relTime.daysAgo", { count: Math.round(h / 24) });
}

/** Company proxy from the recipient address domain (careers@technova.io → Technova). */
function companyFromEmail(addr: string): string {
  const dom = (addr.split("@")[1] || "").split(".")[0] || addr;
  return dom ? dom.charAt(0).toUpperCase() + dom.slice(1) : "—";
}

function StatusChip({ status, size = "sm" }: { status: Status; size?: "sm" | "md" }) {
  const { t } = useTranslation("mail");
  const s = STATUS[status];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-jn-pill font-semibold whitespace-nowrap", size === "sm" ? "px-2.5 py-[3px] text-[11px]" : "px-[11px] py-[5px] text-[12px]")}
      style={{ color: s.color, background: s.bg }}
    >
      <s.Icon size={size === "sm" ? 11 : 12} />
      {t(s.labelKey)}
    </span>
  );
}

function Avatar({ label, size = 40 }: { label: string; size?: number }) {
  return (
    <span
      className="grid shrink-0 place-items-center font-extrabold text-white"
      style={{ width: size, height: size, borderRadius: size > 30 ? 11 : "50%", fontSize: size * 0.36, background: "linear-gradient(135deg,#0064E5,#16C7B5)" }}
    >
      {(label || "?").charAt(0).toUpperCase()}
    </span>
  );
}

export default function MailPage() {
  const { t } = useTranslation("mail");
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("all");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [counts, setCounts] = useState({ sent: 0, replied: 0, awaiting: 0, bounced: 0 });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<MailLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const reveal = useReveal([threads, loading]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sent, replies, bounces] = await Promise.all([
        mailService.logs({ direction: "out", page: 1 }),
        mailService.logs({ direction: "in", page: 1 }),
        mailService.logs({ direction: "in", is_bounce: "1", page: 1 }),
      ]);
      const replyM = new Set(replies.results.filter((r) => !r.is_bounce && r.match != null).map((r) => r.match));
      const bounceM = new Set(bounces.results.filter((r) => r.match != null).map((r) => r.match));
      const ths: Thread[] = sent.results.map((log) => ({
        log,
        status: log.match != null && bounceM.has(log.match) ? "bounced" : log.match != null && replyM.has(log.match) ? "replied" : "awaiting",
      }));
      setThreads(ths);
      setCounts({
        sent: sent.count,
        replied: replies.count,
        bounced: bounces.count,
        awaiting: Math.max(0, sent.count - replies.count - bounces.count),
      });
    } catch {
      addToast({ title: t("toast.loadFailed"), color: "danger" });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { void load(); }, [load]);

  const visible = useMemo(() => (tab === "all" ? threads : threads.filter((x) => x.status === tab)), [threads, tab]);

  // keep a valid selection
  useEffect(() => {
    if (!visible.length) { setSelectedId(null); return; }
    if (!visible.some((x) => x.log.id === selectedId)) setSelectedId(visible[0].log.id);
  }, [visible, selectedId]);

  // load the selected thread's full detail
  useEffect(() => {
    if (selectedId == null) { setDetail(null); return; }
    let alive = true;
    setDetailLoading(true);
    mailService.logDetail(selectedId)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setDetail(null); })
      .finally(() => { if (alive) setDetailLoading(false); });
    return () => { alive = false; };
  }, [selectedId]);

  const doSync = async () => {
    setSyncing(true);
    try {
      const d = await mailService.sync();
      addToast({ title: d.new > 0 ? t("toast.newMail", { count: d.new }) : t("toast.upToDate"), color: d.new > 0 ? "success" : "default" });
      await load();
    } catch {
      addToast({ title: t("toast.syncFailed"), color: "danger" });
    } finally {
      setSyncing(false);
    }
  };

  const summary = [
    { key: "sent", value: counts.sent, color: "#0064E5" },
    { key: "replied", value: counts.replied, color: "#1F9E6E" },
    { key: "awaiting", value: counts.awaiting, color: "#C77700" },
    { key: "bounced", value: counts.bounced, color: "#E0533A" },
  ];

  return (
    <div ref={reveal} className="flex min-h-0 flex-col gap-[18px]" style={{ height: "calc(100vh - 120px)" }}>
      {/* header */}
      <div className="jn-reveal flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="m-0 text-[24px] font-extrabold tracking-[-0.02em] text-jn-ink">{t("box.title")}</h1>
          <div className="mt-1 text-[13.5px] text-jn-muted">{t("box.subtitle")}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {summary.map((s) => (
            <div key={s.key} className="flex items-center gap-2 rounded-[11px] border border-jn-line-2 bg-jn-surface px-3.5 py-2">
              <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
              <span className="text-[14px] font-extrabold text-jn-ink">{s.value}</span>
              <span className="text-[12.5px] text-jn-muted">{t(`box.summary.${s.key}`)}</span>
            </div>
          ))}
          <Button variant="secondary" size="sm" leftIcon={syncing ? <IconLoader2 size={15} className="animate-spin" /> : <IconRefresh size={15} />} onClick={doSync} disabled={syncing}>
            {syncing ? t("page.syncing") : t("page.syncNow")}
          </Button>
        </div>
      </div>

      {/* two columns */}
      <div className="jn-reveal grid min-h-0 flex-1 items-stretch gap-[18px]" style={{ gridTemplateColumns: "386px 1fr" }}>
        {/* thread list */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-jn-card border border-jn-line-2 bg-jn-surface">
          <div className="flex gap-1.5 border-b border-jn-line-soft p-[14px]">
            {TABS.map((tb) => (
              <button key={tb} type="button" onClick={() => setTab(tb)}
                className={cn("rounded-[8px] px-3 py-1.5 text-[12.5px] font-semibold transition-colors", tab === tb ? "bg-jn-sunken text-jn-ink" : "text-jn-muted hover:text-jn-ink-soft")}>
                {t(`box.tabs.${tb}`)}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {loading ? (
              <div className="grid h-40 place-items-center text-jn-muted"><IconLoader2 size={20} className="animate-spin" /></div>
            ) : visible.length === 0 ? (
              <div className="grid h-40 place-items-center px-6 text-center text-[13px] text-jn-muted">{t("box.empty")}</div>
            ) : (
              visible.map(({ log, status }) => {
                const active = log.id === selectedId;
                return (
                  <button key={log.id} type="button" onClick={() => setSelectedId(log.id)}
                    className="flex w-full gap-3 border-b border-jn-line-soft p-[15px] text-left transition-colors hover:bg-[#FAFBFC]"
                    style={{ background: active ? "#F5F9FF" : undefined, borderLeft: `3px solid ${active ? "#0064E5" : "transparent"}` }}>
                    <Avatar label={companyFromEmail(log.to_addr)} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={cn("min-w-0 flex-1 truncate text-[13.5px]", status === "replied" ? "font-bold" : "font-semibold")}>{companyFromEmail(log.to_addr)}</span>
                        <span className="shrink-0 text-[11px] text-jn-faint">{relTime(log.created_at, t)}</span>
                      </div>
                      <div className={cn("mt-0.5 truncate text-[12.5px] text-jn-ink-soft", status === "replied" ? "font-bold" : "font-semibold")}>{log.job_title || log.subject}</div>
                      <div className="mt-[3px] truncate text-[12px] text-jn-muted">{log.body_text?.split("\n")[0] || log.subject}</div>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <StatusChip status={status} />
                        <span className="shrink-0 truncate text-[11px] text-jn-faint">{log.employee_name}</span>
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* thread detail */}
        <div className="min-h-0 overflow-y-auto rounded-jn-card border border-jn-line-2 bg-jn-surface">
          {detailLoading || !detail ? (
            <div className="grid h-full place-items-center text-jn-faint">
              {detailLoading ? <IconLoader2 size={22} className="animate-spin" /> : <div className="text-center"><IconMail size={30} className="mx-auto mb-2 text-jn-faint" />{t("box.selectThread")}</div>}
            </div>
          ) : (
            <ThreadDetail detail={detail} onReply={() => {
              const m = detail.match?.id, e = detail.employee?.id, j = detail.job?.id;
              if (m && e && j) navigate(`/admin/apply-email?employee=${e}&job=${j}&match=${m}`);
            }} />
          )}
        </div>
      </div>
    </div>
  );
}

function ThreadDetail({ detail, onReply }: { detail: MailLogDetail; onReply: () => void }) {
  const { t } = useTranslation("mail");
  const { log, employee, job } = detail;
  const sent = detail.thread.find((m) => m.direction === "out") ?? log;
  const reply = detail.thread.find((m) => m.direction === "in" && !m.is_bounce);
  const bounce = detail.thread.find((m) => m.is_bounce);
  const status: Status = bounce ? "bounced" : reply ? "replied" : "awaiting";
  const company = companyFromEmail(log.to_addr);

  return (
    <div className="p-[30px]">
      {/* head */}
      <div className="flex items-start justify-between gap-5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-[20px] font-extrabold leading-[1.25] tracking-[-0.01em] text-jn-ink">{log.subject || t("detail.noSubject")}</h2>
          <div className="mt-2.5 flex flex-wrap items-center gap-3">
            <StatusChip status={status} size="md" />
            {employee && (
              <span className="text-[12.5px] text-jn-muted">
                {t("box.appliedFor")} <strong className="font-semibold text-jn-ink-soft">{employee.full_name}</strong>
              </span>
            )}
            <span className="h-[13px] w-px bg-jn-line-3" />
            <span className="text-[12.5px] text-jn-muted">
              {t("box.sentBy")} <strong className="font-semibold text-jn-ink-soft">{sent.from_addr}</strong>
            </span>
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Button variant="primary" size="sm" leftIcon={<IconArrowBackUp size={15} />} onClick={onReply}>{t("box.reply")}</Button>
          <DetailIconBtn title={t("box.forward")} onClick={() => job?.source_url && window.open(job.source_url, "_blank")}><IconArrowForwardUp size={16} /></DetailIconBtn>
          <DetailIconBtn title={t("box.archive")} onClick={() => {}}><IconArchive size={16} /></DetailIconBtn>
        </div>
      </div>

      <div className="my-5 h-px bg-jn-line-soft" />

      {/* sent email */}
      <div className="flex gap-3.5">
        <Avatar label="J" size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2.5">
            <div><span className="text-[13.5px] font-bold text-jn-ink">JobFlow</span> <span className="text-[12.5px] text-jn-muted">{t("box.onBehalf", { name: employee?.full_name ?? "—" })}</span></div>
            <span className="text-[12px] text-jn-faint">{new Date(sent.created_at).toLocaleString("vi-VN")}</span>
          </div>
          <div className="mt-0.5 text-[12px] text-jn-muted">{t("box.to")} {sent.to_addr}</div>
          <div className="mt-3 whitespace-pre-line rounded-[12px] border border-jn-line-soft bg-[#FAFBFC] px-[18px] py-4 text-[14px] leading-[1.65] text-jn-ink-soft">
            {sent.body_text}
            <div className="mt-2.5 flex items-center gap-2 text-[12.5px] font-semibold" style={{ color: bounce ? "#E0533A" : "#1F9E6E" }}>
              {bounce ? <IconAlertTriangle size={14} /> : <IconCheck size={14} />}
              {bounce ? t("box.deliveryFailed") : t("box.delivered")}
              {sent.cv_attached && <span className="text-jn-muted">· {t("box.cvAttached")}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* reply */}
      {reply && (
        <div className="mt-5 flex gap-3.5">
          <Avatar label={company} size={40} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2.5">
              <span className="text-[13.5px] font-bold text-jn-ink">{reply.from_addr}</span>
              <span className="text-[12px] text-jn-faint">{new Date(reply.created_at).toLocaleString("vi-VN")}</span>
            </div>
            <div className="mt-0.5 text-[12px] text-jn-muted">{t("box.toJobflow")}</div>
            <div className="mt-3 whitespace-pre-line rounded-[12px] border border-[#D5EFE2] bg-[#F3FBF7] px-[18px] py-4 text-[14px] leading-[1.65] text-jn-ink">
              {reply.body_text}
            </div>
            <div className="mt-3.5 flex flex-wrap gap-2.5">
              <Button variant="primary" size="sm" leftIcon={<IconArrowBackUp size={15} />} onClick={onReply}>{t("box.reply")}</Button>
              <Button variant="secondary" size="sm" leftIcon={<IconCalendarEvent size={15} className="text-jn-ink-mute" />}>{t("box.scheduleInterview")}</Button>
              <Button variant="secondary" size="sm" leftIcon={<IconArrowForwardUp size={15} className="text-jn-ink-mute" />}>{t("box.forwardToCandidate")}</Button>
            </div>
          </div>
        </div>
      )}

      {/* status note */}
      {!reply && (
        <div className="mt-[18px] flex items-center gap-2.5 rounded-[10px] px-[15px] py-3"
          style={{ background: bounce ? "#FCEFEC" : "#FAFBFC", border: `1px solid ${bounce ? "#F6D8D0" : "#ECEDEF"}` }}>
          <span className="flex shrink-0" style={{ color: bounce ? "#E0533A" : "#C77700" }}>
            {bounce ? <IconAlertTriangle size={16} /> : <IconClock size={16} />}
          </span>
          <span className="flex-1 text-[13px] text-jn-ink-soft">
            {bounce ? t("box.bouncedNote", { addr: log.to_addr }) : t("box.awaitingNote", { time: relTime(sent.created_at, t) })}
          </span>
          <Button variant="secondary" size="sm" onClick={onReply}>{bounce ? t("box.resend") : t("box.sendFollowup")}</Button>
        </div>
      )}
    </div>
  );
}

function DetailIconBtn({ children, onClick, title }: { children: React.ReactNode; onClick: () => void; title: string }) {
  return (
    <button type="button" title={title} onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-[9px] border border-jn-line-3 bg-jn-surface text-jn-ink-mute transition-colors hover:bg-jn-sunken">
      {children}
    </button>
  );
}
