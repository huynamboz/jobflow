import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Spinner } from "@heroui/spinner";
import {
  IconAlertTriangle,
  IconBriefcase,
  IconChevronRight,
  IconClockHour4,
  IconFileAlert,
  IconHourglassHigh,
  IconSparkles,
  IconTargetArrow,
  IconTrophy,
  IconUsers,
} from "@tabler/icons-react";

import { staffingDashboardService } from "@/services/staffing-dashboard.service";
import type { StaffingDashboard as TDashboard } from "@/types/staffing-dashboard.types";

/* ---------- small building blocks ---------- */

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  tone?: "default" | "primary" | "success" | "warning" | "danger";
}) {
  const toneRing: Record<string, string> = {
    default: "bg-default-100 text-default-600",
    primary: "bg-primary-100 text-primary-600",
    success: "bg-success-100 text-success-700",
    warning: "bg-warning-100 text-warning-700",
    danger: "bg-danger-100 text-danger-700",
  };
  const toneText: Record<string, string> = {
    default: "text-foreground",
    primary: "text-primary-600",
    success: "text-success-700",
    warning: "text-warning-700",
    danger: "text-danger-700",
  };
  return (
    <Card shadow="sm" radius="lg">
      <CardBody className="flex flex-row items-center gap-3 p-4">
        <div className={`grid size-10 shrink-0 place-items-center rounded-xl ${toneRing[tone]}`}>
          {icon}
        </div>
        <div className="min-w-0">
          <div className={`text-2xl font-bold leading-none ${toneText[tone]}`}>{value}</div>
          <div className="mt-1 truncate text-xs font-medium text-default-500">{label}</div>
          {hint && <div className="truncate text-[11px] text-default-400">{hint}</div>}
        </div>
      </CardBody>
    </Card>
  );
}

function SectionTitle({
  icon,
  children,
  count,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="text-default-500">{icon}</span>
      <h3 className="text-sm font-semibold text-foreground">{children}</h3>
      {count != null && count > 0 && (
        <span className="rounded-full bg-default-100 px-2 py-0.5 text-xs font-medium text-default-600">
          {count}
        </span>
      )}
    </div>
  );
}

function ActionRow({
  name,
  sub,
  chip,
  onClick,
}: {
  name: string;
  sub?: string;
  chip?: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-default-100"
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary-100 text-xs font-semibold text-primary-700">
        {initials(name)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{name}</span>
        {sub && <span className="block truncate text-xs text-default-500">{sub}</span>}
      </span>
      {chip}
      <IconChevronRight
        size={16}
        className="shrink-0 text-default-300 transition-colors group-hover:text-default-500"
      />
    </button>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return <p className="px-2 py-3 text-sm text-default-400">{children}</p>;
}

/* ---------- main ---------- */

export default function StaffingDashboard({ refreshKey }: { refreshKey?: number }) {
  const navigate = useNavigate();
  const [data, setData] = useState<TDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    staffingDashboardService
      .get()
      .then((d) => alive && setData(d))
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  if (loading) {
    return (
      <Card><CardBody className="flex items-center justify-center py-12"><Spinner /></CardBody></Card>
    );
  }
  if (error || !data) {
    return (
      <Card><CardBody className="py-6 text-sm text-danger">Không tải được dashboard staffing.</CardBody></Card>
    );
  }

  const { kpi, action_queue, funnel, alerts, recent } = data;
  const goEmp = (id: number) => navigate(`/admin/employees/${id}`);
  const utilTone = kpi.utilization_pct >= 70 ? "success" : kpi.utilization_pct >= 40 ? "warning" : "danger";
  const funnelRows = [
    { key: "suggested", label: "Gợi ý", color: "bg-default-400" },
    { key: "pursuing", label: "Sẽ apply", color: "bg-primary-400" },
    { key: "applied", label: "Đã apply", color: "bg-secondary-400" },
    { key: "won", label: "Thắng", color: "bg-success-500" },
    { key: "lost", label: "Thua", color: "bg-default-300" },
  ] as const;
  const funnelMax = Math.max(1, ...funnelRows.map((f) => funnel[f.key]));

  const totalActions =
    action_queue.top_new_matches.length +
    action_queue.bench_stale.length +
    action_queue.stale_applied.length;
  const totalAlerts =
    alerts.parse_failed.length + alerts.high_score_unapplied.length + alerts.expiring_pursuing.length;

  return (
    <div className="space-y-5">
      {/* ---- KPI row ---- */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <StatCard
          label="Bench utilization"
          value={`${kpi.utilization_pct}%`}
          hint="nhân viên có cơ hội"
          tone={utilTone}
          icon={<IconTargetArrow size={20} />}
        />
        <StatCard label="Đang bench" value={kpi.bench_count} hint="cần kiếm việc" icon={<IconUsers size={20} />} />
        <StatCard label="Cơ hội đang chạy" value={kpi.in_progress} hint="pursuing + applied" tone="primary" icon={<IconClockHour4 size={20} />} />
        <StatCard label="Thắng tuần này" value={kpi.won_this_week} hint={`${kpi.lost_this_week} thua`} tone="success" icon={<IconTrophy size={20} />} />
        <StatCard label="Job mới 24h" value={kpi.new_jobs_24h} hint={`${kpi.new_jobs_7d} trong 7 ngày`} icon={<IconBriefcase size={20} />} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* ---- FOCAL: action queue (2/3) ---- */}
        <Card className="lg:col-span-2" radius="lg">
          <CardBody className="gap-5 p-5">
            <div className="flex items-center gap-2">
              <IconSparkles size={18} className="text-primary-600" />
              <h2 className="text-base font-bold text-foreground">Cần xử lý hôm nay</h2>
              {totalActions > 0 && (
                <Chip size="sm" color="primary" variant="flat">{totalActions} việc</Chip>
              )}
            </div>

            {totalActions === 0 && (
              <EmptyHint>Tuyệt vời — không có việc nào cần xử lý ngay.</EmptyHint>
            )}

            {action_queue.top_new_matches.length > 0 && (
              <div>
                <SectionTitle icon={<IconSparkles size={15} />} count={action_queue.top_new_matches.length}>
                  Nhân viên có job mới
                </SectionTitle>
                <div className="space-y-0.5">
                  {action_queue.top_new_matches.map((e) => (
                    <ActionRow
                      key={e.id}
                      name={e.full_name}
                      sub="có job phù hợp mới — xem & quyết định apply"
                      onClick={() => goEmp(e.id)}
                      chip={<Chip size="sm" color="primary" variant="flat">{e.new_count} job mới</Chip>}
                    />
                  ))}
                </div>
              </div>
            )}

            {action_queue.bench_stale.length > 0 && (
              <div>
                <SectionTitle icon={<IconHourglassHigh size={15} />} count={action_queue.bench_stale.length}>
                  Bench lâu, chưa có cơ hội
                </SectionTitle>
                <div className="space-y-0.5">
                  {action_queue.bench_stale.map((e) => (
                    <ActionRow
                      key={e.id}
                      name={e.full_name}
                      sub="chưa có cơ hội nào — cần chủ động kiếm job"
                      onClick={() => goEmp(e.id)}
                      chip={<Chip size="sm" color="warning" variant="flat">{e.days_on_bench} ngày</Chip>}
                    />
                  ))}
                </div>
              </div>
            )}

            {action_queue.stale_applied.length > 0 && (
              <div>
                <SectionTitle icon={<IconClockHour4 size={15} />} count={action_queue.stale_applied.length}>
                  Đã apply lâu chưa cập nhật
                </SectionTitle>
                <div className="space-y-0.5">
                  {action_queue.stale_applied.map((m) => (
                    <ActionRow
                      key={m.match_id}
                      name={m.employee_name}
                      sub={m.job_title}
                      onClick={() => goEmp(m.employee_id)}
                      chip={<Chip size="sm" variant="flat">{m.days_since_applied}d chờ</Chip>}
                    />
                  ))}
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        {/* ---- Funnel (1/3) ---- */}
        <Card radius="lg">
          <CardBody className="gap-3 p-5">
            <div className="flex items-center gap-2">
              <IconClockHour4 size={16} className="text-default-500" />
              <h3 className="text-sm font-semibold text-foreground">Phễu pipeline</h3>
            </div>
            <div className="space-y-3 pt-1">
              {funnelRows.map((f) => (
                <div key={f.key}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="text-default-600">{f.label}</span>
                    <span className="font-semibold tabular-nums text-foreground">{funnel[f.key]}</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-default-100">
                    <div
                      className={`h-2 rounded-full ${f.color} transition-all`}
                      style={{ width: `${(funnel[f.key] / funnelMax) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      {/* ---- Alerts ---- */}
      {totalAlerts > 0 && (
        <Card radius="lg" className="border border-warning-200 bg-warning-50/40">
          <CardBody className="gap-4 p-5">
            <div className="flex items-center gap-2">
              <IconAlertTriangle size={16} className="text-warning-600" />
              <h3 className="text-sm font-semibold text-warning-700">Cảnh báo &amp; rủi ro</h3>
              <Chip size="sm" color="warning" variant="flat">{totalAlerts}</Chip>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <AlertColumn
                icon={<IconFileAlert size={14} />}
                title="CV parse lỗi"
                empty={alerts.parse_failed.length === 0}
                items={alerts.parse_failed.map((e) => ({
                  key: e.id, name: e.full_name, onClick: () => goEmp(e.id),
                }))}
              />
              <AlertColumn
                icon={<IconSparkles size={14} />}
                title="Job điểm cao chưa apply"
                empty={alerts.high_score_unapplied.length === 0}
                items={alerts.high_score_unapplied.map((m) => ({
                  key: m.match_id, name: m.employee_name, sub: m.job_title,
                  chip: <Chip size="sm" color="success" variant="flat">{Math.round((m.score ?? 0) * 100)}</Chip>,
                  onClick: () => goEmp(m.employee_id),
                }))}
              />
              <AlertColumn
                icon={<IconHourglassHigh size={14} />}
                title="Job đang theo sắp hết hạn"
                empty={alerts.expiring_pursuing.length === 0}
                items={alerts.expiring_pursuing.map((m) => ({
                  key: m.match_id, name: m.employee_name, sub: m.job_title,
                  chip: <Chip size="sm" color="danger" variant="flat">{m.lifecycle}</Chip>,
                  onClick: () => goEmp(m.employee_id),
                }))}
              />
            </div>
          </CardBody>
        </Card>
      )}

      {/* ---- Recent activity ---- */}
      <Card radius="lg">
        <CardBody className="gap-4 p-5">
          <h3 className="text-sm font-semibold text-foreground">Hoạt động gần đây</h3>
          <div className="grid gap-5 text-sm md:grid-cols-3">
            <div>
              <p className="mb-2 text-xs font-medium text-default-500">Cơ hội won / lost</p>
              {recent.won_lost.length === 0 && <p className="text-default-400">—</p>}
              <ul className="space-y-1.5">
                {recent.won_lost.map((m) => (
                  <li key={m.match_id} className="flex items-center justify-between gap-2">
                    <span className="truncate text-default-700">{m.employee_name} · {m.job_title}</span>
                    <Chip size="sm" color={m.status === "won" ? "success" : "default"} variant="flat">{m.status}</Chip>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-default-500">Job mới crawl</p>
              {recent.new_jobs.length === 0 && <p className="text-default-400">—</p>}
              <ul className="space-y-1.5">
                {recent.new_jobs.map((j) => (
                  <li key={j.id} className="truncate text-default-700">
                    {j.title}{j.company && <span className="text-default-400"> · {j.company}</span>}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-default-500">Nhân viên mới</p>
              {recent.new_employees.length === 0 && <p className="text-default-400">—</p>}
              <ul className="space-y-1.5">
                {recent.new_employees.map((e) => (
                  <li key={e.id}>
                    <button onClick={() => goEmp(e.id)} className="cursor-pointer truncate text-primary-600 hover:underline">
                      {e.full_name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function AlertColumn({
  icon,
  title,
  items,
  empty,
}: {
  icon: React.ReactNode;
  title: string;
  empty: boolean;
  items: { key: number; name: string; sub?: string; chip?: React.ReactNode; onClick: () => void }[];
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-default-600">
        <span className="text-warning-600">{icon}</span>
        {title}
      </div>
      {empty && <p className="text-sm text-default-400">Không có</p>}
      <ul className="space-y-0.5">
        {items.map((it) => (
          <li key={it.key}>
            <button
              type="button"
              onClick={it.onClick}
              className="group flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-warning-100/60"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-foreground">{it.name}</span>
                {it.sub && <span className="block truncate text-xs text-default-500">{it.sub}</span>}
              </span>
              {it.chip}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
