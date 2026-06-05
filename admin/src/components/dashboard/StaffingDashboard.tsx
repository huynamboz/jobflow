import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Spinner } from "@heroui/spinner";
import {
  IconAlertTriangle,
  IconBriefcase,
  IconClockHour4,
  IconTrendingUp,
  IconUsers,
} from "@tabler/icons-react";

import { staffingDashboardService } from "@/services/staffing-dashboard.service";
import type { StaffingDashboard as TDashboard } from "@/types/staffing-dashboard.types";

const FUNNEL_ORDER: { key: keyof TDashboard["funnel"]; label: string }[] = [
  { key: "suggested", label: "Gợi ý" },
  { key: "pursuing", label: "Sẽ apply" },
  { key: "applied", label: "Đã apply" },
  { key: "won", label: "Thắng" },
  { key: "lost", label: "Thua" },
];

function Kpi({
  label,
  value,
  hint,
  icon,
  color = "text-foreground",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  color?: string;
}) {
  return (
    <Card shadow="sm">
      <CardBody className="gap-1">
        <div className="flex items-center gap-2 text-default-500">
          {icon}
          <span className="text-xs">{label}</span>
        </div>
        <div className={`text-2xl font-bold ${color}`}>{value}</div>
        {hint && <div className="text-xs text-default-400">{hint}</div>}
      </CardBody>
    </Card>
  );
}

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
      <Card><CardBody className="flex items-center justify-center py-10"><Spinner /></CardBody></Card>
    );
  }
  if (error || !data) {
    return (
      <Card><CardBody className="text-sm text-danger">Không tải được dashboard staffing.</CardBody></Card>
    );
  }

  const { kpi, action_queue, funnel, alerts, recent } = data;
  const funnelMax = Math.max(1, ...FUNNEL_ORDER.map((f) => funnel[f.key]));
  const goEmp = (id: number) => navigate(`/admin/employees/${id}`);

  return (
    <div className="space-y-4">
      {/* Block 1: KPI strip */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi
          label="Bench utilization"
          value={`${kpi.utilization_pct}%`}
          icon={<IconTrendingUp size={15} />}
          color={kpi.utilization_pct >= 70 ? "text-success" : kpi.utilization_pct >= 40 ? "text-warning" : "text-danger"}
        />
        <Kpi label="Đang bench" value={kpi.bench_count} hint="cần kiếm việc" icon={<IconUsers size={15} />} />
        <Kpi label="Cơ hội đang chạy" value={kpi.in_progress} hint="pursuing + applied" icon={<IconClockHour4 size={15} />} />
        <Kpi label="Thắng / tuần" value={kpi.won_this_week} icon={<IconTrendingUp size={15} />} color="text-success" />
        <Kpi label="Thua / tuần" value={kpi.lost_this_week} icon={<IconTrendingUp size={15} />} color="text-default-500" />
        <Kpi label="Job mới 24h" value={kpi.new_jobs_24h} hint={`${kpi.new_jobs_7d} trong 7 ngày`} icon={<IconBriefcase size={15} />} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* Block 2: Action queue */}
        <Card>
          <CardHeader className="font-semibold">⭐ Cần xử lý sáng nay</CardHeader>
          <CardBody className="space-y-4 text-sm">
            <div>
              <p className="mb-1 text-xs uppercase text-default-400">Nhiều job mới nhất</p>
              {action_queue.top_new_matches.length === 0 && <p className="text-default-400">Không có job mới.</p>}
              {action_queue.top_new_matches.map((e) => (
                <button key={e.id} onClick={() => goEmp(e.id)}
                  className="flex w-full items-center justify-between rounded px-1 py-1 text-left hover:bg-default-100">
                  <span>{e.full_name}</span>
                  <Chip size="sm" color="primary" variant="flat">{e.new_count} job mới</Chip>
                </button>
              ))}
            </div>
            <div>
              <p className="mb-1 text-xs uppercase text-default-400">Bench lâu, chưa có cơ hội</p>
              {action_queue.bench_stale.length === 0 && <p className="text-default-400">Không có.</p>}
              {action_queue.bench_stale.map((e) => (
                <button key={e.id} onClick={() => goEmp(e.id)}
                  className="flex w-full items-center justify-between rounded px-1 py-1 text-left hover:bg-default-100">
                  <span>{e.full_name}</span>
                  <Chip size="sm" color="warning" variant="flat">{e.days_on_bench} ngày</Chip>
                </button>
              ))}
            </div>
            <div>
              <p className="mb-1 text-xs uppercase text-default-400">Đã apply lâu chưa cập nhật</p>
              {action_queue.stale_applied.length === 0 && <p className="text-default-400">Không có.</p>}
              {action_queue.stale_applied.map((m) => (
                <button key={m.match_id} onClick={() => goEmp(m.employee_id)}
                  className="flex w-full items-center justify-between rounded px-1 py-1 text-left hover:bg-default-100">
                  <span className="truncate">{m.employee_name} → {m.job_title}</span>
                  <Chip size="sm" variant="flat">{m.days_since_applied}d</Chip>
                </button>
              ))}
            </div>
          </CardBody>
        </Card>

        {/* Block 3: Funnel */}
        <Card>
          <CardHeader className="font-semibold">Phễu pipeline</CardHeader>
          <CardBody className="space-y-2">
            {FUNNEL_ORDER.map((f) => (
              <div key={f.key} className="flex items-center gap-2 text-sm">
                <span className="w-20 text-default-500">{f.label}</span>
                <div className="h-4 flex-1 rounded bg-default-100">
                  <div
                    className="h-4 rounded bg-primary/70"
                    style={{ width: `${(funnel[f.key] / funnelMax) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right font-medium">{funnel[f.key]}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>

      {/* Block 4: Alerts */}
      <Card className="border border-warning-200">
        <CardHeader className="flex items-center gap-2 font-semibold text-warning-700">
          <IconAlertTriangle size={16} /> Cảnh báo &amp; rủi ro
        </CardHeader>
        <CardBody className="grid gap-4 text-sm md:grid-cols-3">
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">CV parse lỗi ({alerts.parse_failed.length})</p>
            {alerts.parse_failed.length === 0 && <p className="text-default-400">Không có.</p>}
            {alerts.parse_failed.map((e) => (
              <button key={e.id} onClick={() => goEmp(e.id)} className="block text-left text-primary hover:underline">
                {e.full_name}
              </button>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">Job điểm cao chưa apply</p>
            {alerts.high_score_unapplied.length === 0 && <p className="text-default-400">Không có.</p>}
            {alerts.high_score_unapplied.map((m) => (
              <button key={m.match_id} onClick={() => goEmp(m.employee_id)}
                className="flex w-full items-center justify-between text-left hover:bg-default-100">
                <span className="truncate">{m.employee_name} → {m.job_title}</span>
                <Chip size="sm" color="success" variant="flat">{Math.round((m.score ?? 0) * 100)}</Chip>
              </button>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">Job đang theo sắp hết hạn</p>
            {alerts.expiring_pursuing.length === 0 && <p className="text-default-400">Không có.</p>}
            {alerts.expiring_pursuing.map((m) => (
              <button key={m.match_id} onClick={() => goEmp(m.employee_id)}
                className="flex w-full items-center justify-between text-left hover:bg-default-100">
                <span className="truncate">{m.employee_name} → {m.job_title}</span>
                <Chip size="sm" color="danger" variant="flat">{m.lifecycle}</Chip>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Block 5: Recent activity */}
      <Card>
        <CardHeader className="font-semibold">Hoạt động gần đây</CardHeader>
        <CardBody className="grid gap-4 text-sm md:grid-cols-3">
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">Cơ hội won/lost</p>
            {recent.won_lost.length === 0 && <p className="text-default-400">—</p>}
            {recent.won_lost.map((m) => (
              <div key={m.match_id} className="flex items-center justify-between">
                <span className="truncate">{m.employee_name} → {m.job_title}</span>
                <Chip size="sm" color={m.status === "won" ? "success" : "default"} variant="flat">{m.status}</Chip>
              </div>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">Job mới crawl</p>
            {recent.new_jobs.length === 0 && <p className="text-default-400">—</p>}
            {recent.new_jobs.map((j) => (
              <div key={j.id} className="truncate">
                {j.title} <span className="text-default-400">{j.company}</span>
              </div>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs uppercase text-default-400">Nhân viên mới</p>
            {recent.new_employees.length === 0 && <p className="text-default-400">—</p>}
            {recent.new_employees.map((e) => (
              <button key={e.id} onClick={() => goEmp(e.id)} className="block text-left text-primary hover:underline">
                {e.full_name}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
