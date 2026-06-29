import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { addToast } from "@heroui/toast";
import { Dropdown, DropdownTrigger, DropdownMenu, DropdownItem } from "@heroui/dropdown";
import {
  IconBriefcase,
  IconLoader2,
  IconClock,
  IconDots,
  IconPlus,
  IconFilter,
  IconSend,
  IconActivity,
  IconAward,
  IconChecklist,
  IconExternalLink,
  IconUser,
} from "@tabler/icons-react";

import { Avatar, Button, useReveal } from "@/components/ui";
import { cn } from "@/lib/utils";
import { matchService } from "@/services/match.service";
import type { EmployeeJobMatch, MatchStatus } from "@/types/match.types";

const TRACKED = "applied,in_progress,won,completed,lost";

type Col = {
  key: MatchStatus;
  color: string;
  next: MatchStatus | null;
  actionBg: string;
  actionBorder: string;
  actionColor: string;
};
// Per-column colours + action-button tints — exact values from the mockup.
const COLUMNS: Col[] = [
  { key: "applied",     color: "#0064E5", next: "in_progress", actionBg: "#EEF4FE", actionBorder: "#D5E5FC", actionColor: "#0064E5" },
  { key: "in_progress", color: "#0E9CA6", next: "won",         actionBg: "#E6F6F7", actionBorder: "#CDEAEC", actionColor: "#0E9CA6" },
  { key: "won",         color: "#7C4DD0", next: "completed",   actionBg: "#F2ECFB", actionBorder: "#E2D6F6", actionColor: "#7C4DD0" },
  { key: "completed",   color: "#1F9E6E", next: null,          actionBg: "#E7F6EF", actionBorder: "#CFEBDD", actionColor: "#1F9E6E" },
  { key: "lost",        color: "#E0533A", next: "applied",     actionBg: "#F4F5F7", actionBorder: "#E4E5E8", actionColor: "#5B6470" },
];

const STATUS_LABEL: Record<MatchStatus, string> = {
  applied: "tracking.status.applied",
  won: "tracking.status.won",
  in_progress: "tracking.status.inProgress",
  completed: "tracking.status.completed",
  lost: "tracking.status.lost",
  suggested: "tracking.status.applied",
  pursuing: "tracking.status.applied",
  dismissed: "tracking.status.lost",
};
const MENU_STATUSES: MatchStatus[] = ["applied", "in_progress", "won", "completed", "lost"];

// match-badge palette (exact hex from the mockup's mc())
function matchStyle(pct: number): { color: string; bg: string } {
  if (pct >= 95) return { color: "#1F9E6E", bg: "#E7F6EF" };
  if (pct >= 85) return { color: "#0064E5", bg: "#E8F1FE" };
  return { color: "#E8961E", bg: "#FBF1DC" };
}

function dateFor(m: EmployeeJobMatch): string | null {
  if (m.status === "lost") return m.lost_at;
  if (m.status === "won" || m.status === "in_progress" || m.status === "completed") return m.won_at;
  return m.applied_at ?? m.created_at;
}

function relTime(iso: string | null, t: TFunction): string {
  if (!iso) return t("tracking.dash");
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return t("tracking.time.today");
  if (days < 7) return t("tracking.time.daysAgo", { count: days });
  return t("tracking.time.weeksAgo", { count: Math.floor(days / 7) });
}

/** Company/platform logo tile (34px, 1px hairline) with an initial fallback. */
function JobLogo({ src, name }: { src?: string; name?: string }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return (
      <span
        className="grid h-[34px] w-[34px] shrink-0 place-items-center overflow-hidden rounded-[9px]"
        style={{ border: "1px solid #EFEFEF", background: "#f2f2f2" }}
      >
        <img src={src} alt="" loading="lazy" className="h-5 w-5 object-contain" onError={() => setFailed(true)} />
      </span>
    );
  }
  return (
    <span
      className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[9px] text-[13px] font-bold text-jn-ink-mute"
      style={{ border: "1px solid #EFEFEF", background: "#f2f2f2" }}
    >
      {(name || "?").charAt(0).toUpperCase()}
    </span>
  );
}

export default function JobTrackingPage() {
  const navigate = useNavigate();
  const { t } = useTranslation("jobs");
  const [items, setItems] = useState<EmployeeJobMatch[]>([]);
  const [loading, setLoading] = useState(true);
  // Re-scan reveals when the board mounts after the async load.
  const reveal = useReveal([items, loading]);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const m = await matchService.list({ statuses: TRACKED, page: 1, page_size: 200 } as never);
      setItems(m.results);
    } catch {
      addToast({ title: t("tracking.loadError"), color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const setStatus = async (m: EmployeeJobMatch, status: MatchStatus) => {
    setBusy(m.id);
    setItems((prev) => prev.map((x) => (x.id === m.id ? { ...x, status } : x))); // optimistic
    try {
      await matchService.update(m.id, { status });
      addToast({ title: t("tracking.marked", { label: t(STATUS_LABEL[status]) }), color: "success" });
    } catch {
      addToast({ title: t("tracking.updateFailed"), color: "danger" });
      await load();
    } finally {
      setBusy(null);
    }
  };

  const byStatus = useMemo(() => {
    const map: Record<string, EmployeeJobMatch[]> = {};
    for (const c of COLUMNS) map[c.key] = [];
    for (const m of items) (map[m.status] ??= []).push(m);
    return map;
  }, [items]);

  const applied = byStatus.applied?.length ?? 0;
  const responseRate = items.length ? Math.round(((items.length - applied) / items.length) * 100) : 0;
  const summary = [
    { key: "total", value: `${items.length}`, color: "#0064E5", bg: "rgba(0,100,229,.1)", icon: <IconSend size={19} /> },
    { key: "inProgress", value: `${byStatus.in_progress?.length ?? 0}`, color: "#7C4DD0", bg: "rgba(124,77,208,.12)", icon: <IconActivity size={19} /> },
    { key: "offers", value: `${byStatus.won?.length ?? 0}`, color: "#1F9E6E", bg: "rgba(31,158,110,.12)", icon: <IconAward size={19} /> },
    { key: "responseRate", value: `${responseRate}%`, color: "#0E9CA6", bg: "rgba(14,156,166,.12)", icon: <IconChecklist size={19} /> },
  ];

  const goApply = () => navigate("/admin/employees");

  return (
    <div ref={reveal} className="flex min-h-0 flex-col gap-5">
      {/* Header */}
      <div className="jn-reveal flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em] text-jn-ink">
            {t("tracking.titlePrefix")} {t("tracking.titleEmphasis")}
          </h1>
          <div className="mt-[5px] text-[14px] text-jn-muted">{t("tracking.subtitle")}</div>
        </div>
        <div className="flex gap-2.5">
          <Button variant="secondary" leftIcon={<IconFilter size={15} className="text-jn-ink-mute" />}>
            {t("tracking.filter")}
          </Button>
          <Button variant="primary" leftIcon={<IconPlus size={15} />} onClick={goApply}>
            {t("tracking.addApplication")}
          </Button>
        </div>
      </div>

      {/* Summary pills */}
      <div className="jn-reveal flex flex-wrap gap-3.5">
        {summary.map((s) => (
          <div
            key={s.key}
            className="flex min-w-[170px] items-center gap-3 rounded-[13px] border border-jn-line-2 bg-jn-surface px-[18px] py-[13px]"
          >
            <span className="grid h-[38px] w-[38px] place-items-center rounded-[11px]" style={{ color: s.color, background: s.bg }}>
              {s.icon}
            </span>
            <div>
              <div className="text-[21px] font-extrabold leading-none tracking-[-0.02em] text-jn-ink">{s.value}</div>
              <div className="mt-[3px] text-[12px] text-jn-muted">{t(`tracking.summary.${s.key}`)}</div>
            </div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="grid h-[240px] place-items-center text-jn-muted">
          <IconLoader2 size={22} className="animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="grid h-[240px] place-items-center rounded-jn-card border border-jn-line bg-jn-surface text-center text-jn-ink-mute">
          <div>
            <IconBriefcase size={30} className="mx-auto mb-2.5 text-jn-faint" />
            <div className="font-semibold text-jn-ink">{t("tracking.emptyTitle")}</div>
            <div className="text-[13px] text-jn-muted">{t("tracking.emptyHint")}</div>
          </div>
        </div>
      ) : (
        /* ===== Kanban board ===== */
        <div className="jn-reveal flex flex-1 items-start gap-4 overflow-x-auto pb-2.5">
          {COLUMNS.map((col) => {
            const cards = byStatus[col.key] ?? [];
            return (
              <div
                key={col.key}
                className="flex w-[288px] shrink-0 flex-col gap-[11px] rounded-jn-card p-3"
                style={{ background: "#EFF1F4" }}
              >
                {/* column header */}
                <div className="flex items-center gap-2.5 px-1.5 pb-0.5 pt-1.5">
                  <span className="h-[9px] w-[9px] rounded-full" style={{ background: col.color }} />
                  <span className="text-[13.5px] font-bold text-jn-ink">{t(STATUS_LABEL[col.key])}</span>
                  <span className="rounded-jn-pill bg-white px-[9px] py-px text-[12px] font-bold text-jn-ink-mute">
                    {cards.length}
                  </span>
                  <button
                    type="button"
                    onClick={goApply}
                    className="ml-auto grid h-[26px] w-[26px] place-items-center rounded-[7px] text-jn-muted transition-colors hover:bg-[#F2F3F5]"
                  >
                    <IconPlus size={15} />
                  </button>
                </div>

                {/* cards */}
                {cards.map((m) => {
                  const pct = Math.round((m.match_score ?? 0) * 100);
                  const ms = matchStyle(pct);
                  return (
                    <div
                      key={m.id}
                      role="button"
                      onClick={() => navigate(`/admin/employees/${m.employee}`)}
                      className={cn(
                        "cursor-pointer rounded-[13px] border bg-jn-surface p-3.5",
                        "transition-[box-shadow,transform,border-color] duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_28px_rgba(20,20,40,.1)]",
                        busy === m.id && "opacity-60",
                      )}
                      style={{ borderColor: "#ECECEE" }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#DCDEE2")}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#ECECEE")}
                    >
                      <div className="flex items-start gap-[11px]">
                        <JobLogo src={m.job.platform_logo} name={m.job.company_name || m.job.title} />
                        <div className="min-w-0 flex-1">
                          <div className="text-[13.5px] font-bold leading-[1.3] text-jn-ink">{m.job.title}</div>
                          <div className="mt-px truncate text-[12px] text-jn-muted">
                            {m.job.company_name || t("tracking.dash")}
                          </div>
                        </div>
                        <span
                          className="shrink-0 rounded-[11px] px-2 py-[3px] text-[11.5px] font-extrabold"
                          style={{ color: ms.color, background: ms.bg }}
                        >
                          {pct}%
                        </span>
                      </div>

                      <div
                        className="mt-3 flex items-center gap-2 pt-[11px]"
                        style={{ borderTop: "1px solid #F2F3F5" }}
                      >
                        <Avatar name={m.employee_name} size={24} />
                        <span className="min-w-0 flex-1 truncate text-[12px] font-medium" style={{ color: "#5B6470" }}>
                          {m.employee_name}
                        </span>
                        <span className="flex shrink-0 items-center gap-1 text-[11px]" style={{ color: "#A2A8B0" }}>
                          <IconClock size={11} />
                          {relTime(dateFor(m), t)}
                        </span>
                      </div>

                      <div className="mt-[11px] flex items-center gap-2">
                        <button
                          type="button"
                          disabled={busy === m.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (col.next) void setStatus(m, col.next);
                          }}
                          className="flex flex-1 items-center justify-center rounded-[8px] border px-2 py-[7px] text-[12px] font-semibold transition-[filter] hover:brightness-[0.97] disabled:opacity-60"
                          style={{ color: col.actionColor, background: col.actionBg, borderColor: col.actionBorder }}
                        >
                          {col.key === "lost"
                            ? t("tracking.reopen")
                            : col.next
                              ? t("tracking.moveTo", { label: t(STATUS_LABEL[col.next]) })
                              : t("tracking.status.completed")}
                        </button>

                        <Dropdown placement="bottom-end">
                          <DropdownTrigger>
                            <button
                              type="button"
                              onClick={(e) => e.stopPropagation()}
                              className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[8px] text-jn-muted transition-colors hover:bg-jn-sunken"
                              style={{ border: "1px solid #ECECEE" }}
                            >
                              <IconDots size={16} />
                            </button>
                          </DropdownTrigger>
                          <DropdownMenu
                            aria-label={t("tracking.changeStatus")}
                            onAction={(key) => {
                              const k = String(key);
                              if (k === "employee") { navigate(`/admin/employees/${m.employee}`); return; }
                              if (k === "open" && m.job.source_url) { window.open(m.job.source_url, "_blank"); return; }
                              if (k !== m.status) void setStatus(m, k as MatchStatus);
                            }}
                          >
                            <>
                              {MENU_STATUSES.map((s) => (
                                <DropdownItem key={s}>{t(STATUS_LABEL[s])}</DropdownItem>
                              ))}
                              <DropdownItem key="employee" startContent={<IconUser size={15} />} showDivider>
                                {t("tracking.viewEmployee")}
                              </DropdownItem>
                              {m.job.source_url ? (
                                <DropdownItem key="open" startContent={<IconExternalLink size={15} />}>
                                  {t("tracking.openPosting")}
                                </DropdownItem>
                              ) : null}
                            </>
                          </DropdownMenu>
                        </Dropdown>
                      </div>
                    </div>
                  );
                })}

                {/* add card */}
                <button
                  type="button"
                  onClick={goApply}
                  className="flex items-center justify-center gap-1.5 rounded-[11px] border-[1.5px] border-dashed px-3 py-[11px] text-[12.5px] font-semibold text-jn-muted transition-colors hover:bg-[#EEF0F3] hover:text-jn-ink-mute"
                  style={{ borderColor: "#D5D8DC" }}
                >
                  <IconPlus size={14} />
                  {t("tracking.addCard")}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
