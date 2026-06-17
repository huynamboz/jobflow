import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Select, SelectItem } from "@heroui/select";
import { Spinner } from "@heroui/spinner";
import { IconBriefcase, IconExternalLink } from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import { matchService } from "@/services/match.service";
import type { EmployeeJobMatch, MatchStatus } from "@/types/match.types";

const T = {
  accent: "#167a7a",
  success: "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger: "oklch(0.60 0.22 25)", danger50: "oklch(0.96 0.03 25)",
  warning: "oklch(0.55 0.12 70)", warning50: "oklch(0.96 0.05 75)",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  line: "rgba(226,232,240,0.7)",
};

const PAGE_SIZE = 20;
const TRACKED = "applied,won,in_progress,completed,lost";

type TrackTab = "all" | "applied" | "won" | "in_progress" | "completed" | "lost";
const TABS: { key: TrackTab; labelKey: string }[] = [
  { key: "all", labelKey: "tracking.tabs.all" },
  { key: "applied", labelKey: "tracking.tabs.applied" },
  { key: "won", labelKey: "tracking.tabs.won" },
  { key: "in_progress", labelKey: "tracking.tabs.inProgress" },
  { key: "completed", labelKey: "tracking.tabs.completed" },
  { key: "lost", labelKey: "tracking.tabs.lost" },
];

const TAB_FILTER: Record<TrackTab, { status?: MatchStatus; statuses?: string }> = {
  all: { statuses: TRACKED },
  applied: { status: "applied" },
  won: { status: "won" },
  in_progress: { status: "in_progress" },
  completed: { status: "completed" },
  lost: { status: "lost" },
};

const STATUS_CHIP: Record<string, { labelKey: string; bg: string; color: string }> = {
  applied: { labelKey: "tracking.status.applied", bg: "oklch(0.94 0.05 280)", color: "oklch(0.45 0.16 280)" },
  won: { labelKey: "tracking.status.won", bg: "#e8f4f4", color: "#0e5353" },
  in_progress: { labelKey: "tracking.status.inProgress", bg: T.warning50, color: T.warning },
  completed: { labelKey: "tracking.status.completed", bg: T.success50, color: T.success },
  lost: { labelKey: "tracking.status.lost", bg: T.danger50, color: T.danger },
};

const STATUS_OPTIONS: { key: MatchStatus; labelKey: string }[] = [
  { key: "applied", labelKey: "tracking.status.applied" },
  { key: "won", labelKey: "tracking.status.won" },
  { key: "in_progress", labelKey: "tracking.status.inProgress" },
  { key: "completed", labelKey: "tracking.status.completed" },
  { key: "lost", labelKey: "tracking.status.lost" },
];

function initials(name: string): string {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("vi-VN", { dateStyle: "medium" });
}

function dateFor(m: EmployeeJobMatch): string | null {
  if (m.status === "lost") return m.lost_at;
  if (m.status === "won" || m.status === "in_progress" || m.status === "completed") return m.won_at;
  return m.applied_at;
}

export default function JobTrackingPage() {
  const navigate = useNavigate();
  const { t } = useTranslation("jobs");
  const [tab, setTab] = useState<TrackTab>("all");
  const [items, setItems] = useState<EmployeeJobMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);

  const load = useCallback(
    async (pg = 1, append = false) => {
      if (!append) setLoading(true);
      try {
        const m = await matchService.list({ ...TAB_FILTER[tab], page: pg, page_size: PAGE_SIZE });
        setItems((prev) => (append ? [...prev, ...m.results] : m.results));
        setHasMore(!!m.next);
        setTotal(m.count ?? m.results.length);
        setPage(pg);
      } catch {
        addToast({ title: t("tracking.loadError"), color: "danger" });
      } finally {
        setLoading(false);
      }
    },
    [tab, t],
  );

  useEffect(() => { void load(1, false); }, [load]);

  const setStatus = async (m: EmployeeJobMatch, status: MatchStatus, label: string) => {
    setBusy(m.id);
    try {
      await matchService.update(m.id, { status });
      addToast({ title: t("tracking.marked", { label }), color: "success" });
      await load(1, false);
    } catch {
      addToast({ title: t("tracking.updateFailed"), color: "danger" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.025em", margin: 0, color: T.ink }}>
          {t("tracking.titlePrefix")} <span style={{ fontStyle: "italic", color: T.accent, fontWeight: 400 }}>{t("tracking.titleEmphasis")}</span>
        </h1>
        <p style={{ margin: "4px 0 0", color: T.ink3, fontSize: 14 }}>
          {t("tracking.subtitle")}
        </p>
      </div>

      {/* tabs */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {TABS.map((tabItem) => {
          const active = tab === tabItem.key;
          return (
            <button key={tabItem.key} type="button" onClick={() => setTab(tabItem.key)}
              style={{
                padding: "7px 14px", borderRadius: 999, fontSize: 13, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${active ? T.accent : T.line}`,
                background: active ? T.accent : "#fff", color: active ? "#fff" : T.ink2,
              }}>
              {t(tabItem.labelKey)}{active && total ? ` (${total})` : ""}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div style={{ display: "grid", placeItems: "center", height: 200 }}><Spinner /></div>
      ) : items.length === 0 ? (
        <Card style={{ display: "grid", placeItems: "center", height: 240, color: T.ink3 }}>
          <div style={{ textAlign: "center" }}>
            <IconBriefcase size={30} style={{ margin: "0 auto 10px", color: T.ink4 }} />
            <div style={{ fontWeight: 600 }}>{t("tracking.emptyTitle")}</div>
            <div style={{ fontSize: 13 }}>{t("tracking.emptyHint")}</div>
          </div>
        </Card>
      ) : (
        <Card padding={0}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {items.map((m, i) => {
              const chip = STATUS_CHIP[m.status] ?? STATUS_CHIP.applied;
              return (
                <li key={m.id} style={{ borderTop: i ? `1px solid ${T.line}` : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px" }}>
                    <button
                      type="button"
                      onClick={() => navigate(`/admin/employees/${m.employee}`)}
                      style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
                    >
                      <span style={{ width: 38, height: 38, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: "#e8f4f4", color: T.accent, fontWeight: 700, fontSize: 13 }}>
                        {initials(m.employee_name)}
                      </span>
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: "block", fontWeight: 600, fontSize: 14, color: T.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.employee_name} · {m.job.title}
                        </span>
                        <span style={{ display: "block", fontSize: 12.5, color: T.ink3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.job.company_name || t("tracking.dash")} · {(STATUS_CHIP[m.status] ? t(STATUS_CHIP[m.status].labelKey) : m.status).toLowerCase()} {fmtDate(dateFor(m))}
                        </span>
                      </span>
                    </button>

                    <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, background: chip.bg, color: chip.color, flexShrink: 0 }}>
                      {t(chip.labelKey)}
                    </span>

                    {m.job.source_url && (
                      <a href={m.job.source_url} target="_blank" rel="noreferrer"
                        style={{ flexShrink: 0, color: T.ink4, display: "flex" }} title={t("tracking.openPosting")}>
                        <IconExternalLink size={16} />
                      </a>
                    )}

                    <Select
                      aria-label={t("tracking.changeStatus")}
                      size="sm"
                      selectedKeys={[m.status]}
                      isDisabled={busy === m.id}
                      onSelectionChange={(keys) => {
                        const next = Array.from(keys)[0] as MatchStatus;
                        if (next && next !== m.status) {
                          const opt = STATUS_OPTIONS.find((o) => o.key === next);
                          setStatus(m, next, opt ? t(opt.labelKey) : next);
                        }
                      }}
                      className="w-[150px] shrink-0"
                    >
                      {STATUS_OPTIONS.map((o) => <SelectItem key={o.key}>{t(o.labelKey)}</SelectItem>)}
                    </Select>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {hasMore && !loading && (
        <Button color="primary" variant="flat" onPress={() => void load(page + 1, true)}>
          {t("tracking.viewMore", { count: Math.max(0, total - items.length) })}
        </Button>
      )}
    </div>
  );
}
