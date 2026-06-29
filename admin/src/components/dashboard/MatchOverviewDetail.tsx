import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  IconAlertTriangle,
  IconFileAlert,
  IconSparkles,
  IconHourglassHigh,
  IconClockHour4,
} from "@tabler/icons-react";

import { Badge, Card, SectionLabel } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { StaffingDashboard } from "@/types/staffing-dashboard.types";

/**
 * JobNest-styled lower section of the dashboard: pipeline funnel, the
 * stale-applications + alerts worklist, and recent activity. Consumes the
 * staffing payload already fetched by the dashboard page (no extra request).
 */
export interface MatchOverviewDetailProps {
  staffing: StaffingDashboard;
}

const FUNNEL_BARS = [
  { key: "suggested", color: "bg-jn-faint" },
  { key: "pursuing", color: "bg-jn-primary" },
  { key: "applied", color: "bg-jn-violet" },
  { key: "won", color: "bg-jn-green" },
  { key: "lost", color: "bg-jn-line-3" },
] as const;

export default function MatchOverviewDetail({ staffing }: MatchOverviewDetailProps) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const { funnel, action_queue, alerts, recent } = staffing;
  const goEmp = (id: number) => navigate(`/admin/employees/${id}`);

  const funnelMax = Math.max(1, ...FUNNEL_BARS.map((f) => funnel[f.key]));
  const totalAlerts =
    alerts.parse_failed.length + alerts.high_score_unapplied.length + alerts.expiring_pursuing.length;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Pipeline funnel */}
        <Card padding={22}>
          <div className="mb-4 flex items-center gap-2">
            <IconClockHour4 size={16} className="text-jn-muted" />
            <h3 className="text-[14px] font-bold text-jn-ink">{t("staffing.pipelineFunnel")}</h3>
          </div>
          <div className="flex flex-col gap-3.5">
            {FUNNEL_BARS.map((f) => (
              <div key={f.key}>
                <div className="mb-1.5 flex items-center justify-between text-[12.5px]">
                  <span className="text-jn-ink-mute">{t(`staffing.funnel.${f.key}`)}</span>
                  <span className="font-bold tabular-nums text-jn-ink">{funnel[f.key]}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-jn-sunken">
                  <div
                    className={cn("h-2 rounded-full transition-all duration-700", f.color)}
                    style={{ width: `${(funnel[f.key] / funnelMax) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Alerts / stale (2 cols) */}
        <Card padding={22} className="lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <IconAlertTriangle size={16} className="text-jn-amber" />
            <h3 className="text-[14px] font-bold text-jn-ink">{t("staffing.alertsTitle")}</h3>
            {totalAlerts > 0 && <Badge color="amber">{totalAlerts}</Badge>}
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            <AlertColumn
              icon={<IconFileAlert size={13} />}
              title={t("staffing.alerts.parseFailed")}
              items={alerts.parse_failed.map((e) => ({ key: e.id, name: e.full_name, onClick: () => goEmp(e.id) }))}
            />
            <AlertColumn
              icon={<IconSparkles size={13} />}
              title={t("staffing.alerts.highScoreUnapplied")}
              items={alerts.high_score_unapplied.map((m) => ({
                key: m.match_id,
                name: m.employee_name,
                sub: m.job_title,
                chip: <Badge color="green">{Math.round((m.score ?? 0) * 100)}</Badge>,
                onClick: () => goEmp(m.employee_id),
              }))}
            />
            <AlertColumn
              icon={<IconHourglassHigh size={13} />}
              title={t("staffing.alerts.expiringPursuing")}
              items={alerts.expiring_pursuing.map((m) => ({
                key: m.match_id,
                name: m.employee_name,
                sub: m.job_title,
                chip: <Badge color="red">{m.lifecycle}</Badge>,
                onClick: () => goEmp(m.employee_id),
              }))}
            />
          </div>

          {action_queue.stale_applied.length > 0 && (
            <div className="mt-5 border-t border-jn-line pt-4">
              <SectionLabel className="mb-2.5">{t("staffing.staleApplied")}</SectionLabel>
              <div className="flex flex-col">
                {action_queue.stale_applied.map((m) => (
                  <button
                    key={m.match_id}
                    type="button"
                    onClick={() => goEmp(m.employee_id)}
                    className="flex items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-jn-sunken"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-semibold text-jn-ink">{m.employee_name}</span>
                      <span className="block truncate text-[12px] text-jn-muted">{m.job_title}</span>
                    </span>
                    {m.days_since_applied != null && (
                      <Badge color="neutral">{t("staffing.daysWaiting", { count: m.days_since_applied })}</Badge>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Recent activity */}
      <Card padding={22}>
        <h3 className="mb-4 text-[14px] font-bold text-jn-ink">{t("staffing.recentActivity")}</h3>
        <div className="grid gap-6 md:grid-cols-3">
          <RecentColumn title={t("staffing.recent.wonLost")} empty={recent.won_lost.length === 0}>
            {recent.won_lost.map((m) => (
              <li key={m.match_id} className="flex items-center justify-between gap-2">
                <span className="truncate text-[13px] text-jn-ink-soft">
                  {m.employee_name} · {m.job_title}
                </span>
                <Badge color={m.status === "won" ? "green" : "neutral"}>
                  {m.status === "won" ? t("staffing.recent.accepted") : t("staffing.recent.rejected")}
                </Badge>
              </li>
            ))}
          </RecentColumn>
          <RecentColumn title={t("staffing.recent.newJobs")} empty={recent.new_jobs.length === 0}>
            {recent.new_jobs.map((j) => (
              <li key={j.id} className="truncate text-[13px] text-jn-ink-soft">
                {j.title}
                {j.company && <span className="text-jn-faint"> · {j.company}</span>}
              </li>
            ))}
          </RecentColumn>
          <RecentColumn title={t("staffing.recent.newEmployees")} empty={recent.new_employees.length === 0}>
            {recent.new_employees.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  onClick={() => goEmp(e.id)}
                  className="truncate text-[13px] font-medium text-jn-primary hover:underline"
                >
                  {e.full_name}
                </button>
              </li>
            ))}
          </RecentColumn>
        </div>
      </Card>
    </div>
  );
}

function AlertColumn({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: { key: number; name: string; sub?: string; chip?: React.ReactNode; onClick: () => void }[];
}) {
  const { t } = useTranslation("dashboard");
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-jn-ink-mute">
        <span className="text-jn-amber">{icon}</span>
        {title}
      </div>
      {items.length === 0 && <p className="text-[13px] text-jn-muted">{t("staffing.alerts.none")}</p>}
      <ul className="flex flex-col gap-0.5">
        {items.map((it) => (
          <li key={it.key}>
            <button
              type="button"
              onClick={it.onClick}
              className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-jn-sunken"
            >
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium text-jn-ink">{it.name}</span>
                {it.sub && <span className="block truncate text-[12px] text-jn-muted">{it.sub}</span>}
              </span>
              {it.chip}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecentColumn({ title, empty, children }: { title: string; empty: boolean; children: React.ReactNode }) {
  return (
    <div>
      <SectionLabel className="mb-2.5">{title}</SectionLabel>
      {empty ? <p className="text-[13px] text-jn-muted">—</p> : <ul className="flex flex-col gap-1.5">{children}</ul>}
    </div>
  );
}
