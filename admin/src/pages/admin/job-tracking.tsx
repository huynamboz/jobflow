import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { addToast } from "@heroui/toast";
import { Dropdown, DropdownTrigger, DropdownMenu, DropdownItem } from "@heroui/dropdown";
import { Modal, ModalContent, ModalBody, ModalFooter } from "@heroui/modal";
import {
  IconBriefcase,
  IconLoader2,
  IconClock,
  IconDots,
  IconSend,
  IconActivity,
  IconAward,
  IconChecklist,
  IconExternalLink,
  IconMapPin,
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
  const [active, setActive] = useState<EmployeeJobMatch | null>(null);
  // Native HTML5 drag-and-drop between columns.
  const dragId = useRef<number | null>(null);
  const lastDragEnd = useRef(0);
  const [dragOver, setDragOver] = useState<MatchStatus | null>(null);

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

  const dropTo = (colKey: MatchStatus) => {
    const id = dragId.current;
    dragId.current = null;
    setDragOver(null);
    if (id == null) return;
    const m = items.find((x) => x.id === id);
    if (m && m.status !== colKey) void setStatus(m, colKey);
  };

  const applied = byStatus.applied?.length ?? 0;
  const responseRate = items.length ? Math.round(((items.length - applied) / items.length) * 100) : 0;
  const summary = [
    { key: "total", value: `${items.length}`, color: "#0064E5", bg: "rgba(0,100,229,.1)", icon: <IconSend size={19} /> },
    { key: "inProgress", value: `${byStatus.in_progress?.length ?? 0}`, color: "#7C4DD0", bg: "rgba(124,77,208,.12)", icon: <IconActivity size={19} /> },
    { key: "offers", value: `${byStatus.won?.length ?? 0}`, color: "#1F9E6E", bg: "rgba(31,158,110,.12)", icon: <IconAward size={19} /> },
    { key: "responseRate", value: `${responseRate}%`, color: "#0E9CA6", bg: "rgba(14,156,166,.12)", icon: <IconChecklist size={19} /> },
  ];

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
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; if (dragOver !== col.key) setDragOver(col.key); }}
                onDrop={(e) => { e.preventDefault(); dropTo(col.key); }}
                className="flex w-[288px] shrink-0 flex-col gap-[11px] rounded-jn-card p-3 transition-colors"
                style={{
                  background: dragOver === col.key ? "#E4E9F2" : "#EFF1F4",
                  outline: dragOver === col.key ? "2px dashed #9DB6E8" : "none",
                  outlineOffset: -2,
                }}
              >
                {/* column header */}
                <div className="flex items-center gap-2.5 px-1.5 pb-0.5 pt-1.5">
                  <span className="h-[9px] w-[9px] rounded-full" style={{ background: col.color }} />
                  <span className="text-[13.5px] font-bold text-jn-ink">{t(STATUS_LABEL[col.key])}</span>
                  <span className="rounded-jn-pill bg-white px-[9px] py-px text-[12px] font-bold text-jn-ink-mute">
                    {cards.length}
                  </span>
                </div>

                {/* cards */}
                {cards.map((m) => {
                  const pct = Math.round((m.match_score ?? 0) * 100);
                  const ms = matchStyle(pct);
                  return (
                    <div
                      key={m.id}
                      role="button"
                      draggable
                      onDragStart={(e) => { dragId.current = m.id; e.dataTransfer.effectAllowed = "move"; }}
                      onDragEnd={() => { dragId.current = null; setDragOver(null); lastDragEnd.current = Date.now(); }}
                      onClick={() => { if (Date.now() - lastDragEnd.current < 200) return; setActive(m); }}
                      className={cn(
                        "cursor-grab rounded-[13px] border bg-jn-surface p-3.5 active:cursor-grabbing",
                        "transition-[box-shadow,transform,border-color] duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_28px_rgba(20,20,40,.1)]",
                        busy === m.id && "opacity-60",
                        dragId.current === m.id && "opacity-40",
                      )}
                      style={{ borderColor: "#ECECEE" }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#DCDEE2")}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#ECECEE")}
                    >
                      <div className="flex items-start gap-[11px]">
                        <JobLogo src={m.job.company_logo || m.job.platform_logo} name={m.job.company_name || m.job.title} />
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
              </div>
            );
          })}
        </div>
      )}

      <ApplicationDetailModal
        match={active}
        onClose={() => setActive(null)}
        onViewEmployee={(emp) => { setActive(null); navigate(`/admin/employees/${emp}`); }}
      />
    </div>
  );
}

/* ── Application detail dialog (opened by clicking a kanban card) ────────── */
function ApplicationDetailModal({
  match, onClose, onViewEmployee,
}: {
  match: EmployeeJobMatch | null;
  onClose: () => void;
  onViewEmployee: (employee: number) => void;
}) {
  const { t } = useTranslation("jobs");
  const m = match;
  const pct = m ? Math.round((m.match_score ?? 0) * 100) : 0;
  const ms = matchStyle(pct);
  const col = COLUMNS.find((c) => c.key === m?.status);

  return (
    <Modal isOpen={!!m} onClose={onClose} size="lg" scrollBehavior="inside">
      <ModalContent>
        {m && (
          <>
            <ModalBody className="gap-4 px-6 py-6">
              {/* job header */}
              <div className="flex items-start gap-3.5">
                <JobLogo src={m.job.company_logo || m.job.platform_logo} name={m.job.company_name || m.job.title} />
                <div className="min-w-0 flex-1">
                  <div className="text-[16px] font-extrabold leading-snug tracking-[-0.01em] text-jn-ink">{m.job.title}</div>
                  <div className="mt-0.5 truncate text-[13px] text-jn-muted">{m.job.company_name || t("tracking.dash")}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-jn-muted">
                    {m.job.location && <span className="inline-flex items-center gap-1"><IconMapPin size={13} />{m.job.location}</span>}
                    {m.job.job_type && <span className="inline-flex items-center gap-1"><IconBriefcase size={13} />{m.job.job_type}</span>}
                  </div>
                </div>
                <span className="shrink-0 rounded-[11px] px-2.5 py-1 text-[13px] font-extrabold" style={{ color: ms.color, background: ms.bg }}>{pct}%</span>
              </div>

              {/* status + employee */}
              <div className="flex flex-wrap items-center gap-2.5 rounded-[12px] border border-jn-line-2 bg-jn-surface px-3.5 py-3">
                {col && (
                  <span className="inline-flex items-center gap-1.5 rounded-jn-pill px-2.5 py-[3px] text-[12px] font-bold" style={{ color: col.actionColor, background: col.actionBg }}>
                    <span className="h-2 w-2 rounded-full" style={{ background: col.color }} />
                    {t(STATUS_LABEL[m.status])}
                  </span>
                )}
                <span className="h-3.5 w-px bg-jn-line-3" />
                <Avatar name={m.employee_name} size={22} />
                <span className="truncate text-[13px] font-medium text-jn-ink-soft">{m.employee_name}</span>
              </div>

              {/* matched skills */}
              {m.matched_skills?.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[12px] font-semibold text-jn-ink">{t("tracking.dialog.matchedSkills")}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {m.matched_skills.map((s) => (
                      <span key={s} className="rounded-jn-pill bg-[#E7F6EF] px-2.5 py-1 text-[11.5px] font-medium text-[#1F9E6E]">{s}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* missing skills */}
              {m.missing_skills?.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[12px] font-semibold text-jn-ink">{t("tracking.dialog.missingSkills")}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {m.missing_skills.map((s) => (
                      <span key={s} className="rounded-jn-pill bg-jn-sunken px-2.5 py-1 text-[11.5px] font-medium text-jn-muted">{s}</span>
                    ))}
                  </div>
                </div>
              )}

              {m.notes && (
                <div>
                  <div className="mb-1.5 text-[12px] font-semibold text-jn-ink">{t("tracking.dialog.notes")}</div>
                  <div className="whitespace-pre-line rounded-[10px] border border-jn-line-soft bg-[#FAFBFC] px-3.5 py-2.5 text-[13px] text-jn-ink-soft">{m.notes}</div>
                </div>
              )}
            </ModalBody>
            <ModalFooter className="gap-2 px-6 pb-5">
              {m.job.source_url && (
                <Button variant="secondary" size="sm" leftIcon={<IconExternalLink size={15} />} onClick={() => window.open(m.job.source_url, "_blank", "noopener")}>
                  {t("tracking.openPosting")}
                </Button>
              )}
              <Button variant="primary" size="sm" leftIcon={<IconUser size={15} />} onClick={() => onViewEmployee(m.employee)}>
                {t("tracking.viewEmployee")}
              </Button>
            </ModalFooter>
          </>
        )}
      </ModalContent>
    </Modal>
  );
}
