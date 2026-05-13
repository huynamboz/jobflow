import { Card, CardBody } from "@heroui/card";

import { dashboardService } from "@/services/dashboard.service";
import type { OpsHealth } from "@/types/dashboard.types";

import { fmtPct, timeAgo } from "./KpiStrip";
import SectionCard from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function ProgressBar({ pct }: { pct: number }) {
  const w = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-default-100">
      <div className="h-full rounded-full bg-primary-500" style={{ width: `${w}%` }} />
    </div>
  );
}

const OUTCOME_BADGE = (key: string, n: number) => {
  if (!n) return null;
  const cls: Record<string, string> = {
    active: "bg-success-100 text-success-700",
    expired: "bg-default-200 text-default-700",
    populated: "bg-primary-100 text-primary-700",
    expired_marked: "bg-default-200 text-default-700",
    unknown: "bg-warning-100 text-warning-700",
    none: "bg-warning-100 text-warning-700",
    error: "bg-danger-100 text-danger-700",
    session_expired: "bg-secondary-100 text-secondary-700",
  };
  return (
    <span key={key} className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls[key] ?? "bg-default-100 text-default-700"}`}>
      {key} {n}
    </span>
  );
};

export default function VerifierExtractorOps({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<OpsHealth>(
    () => dashboardService.getOps(),
    refreshKey,
  );

  const empty = !!data && data.recent_runs.length === 0
    && data.coverage.linkedin_with_date_posted_pct === 0
    && data.coverage.linkedin_verified_last_30d_pct === 0;

  return (
    <SectionCard
      title="Verifier & extractor ops"
      description="Coverage and recent run history"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="space-y-4">
          {/* Coverage cards */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Card className="shadow-sm">
              <CardBody className="p-3">
                <p className="mb-1 text-xs uppercase tracking-wide text-default-500">
                  LinkedIn jobs with date_posted
                </p>
                <p className="mb-2 text-2xl font-semibold text-default-900">
                  {fmtPct(data.coverage.linkedin_with_date_posted_pct)}
                </p>
                <ProgressBar pct={data.coverage.linkedin_with_date_posted_pct} />
              </CardBody>
            </Card>
            <Card className="shadow-sm">
              <CardBody className="p-3">
                <p className="mb-1 text-xs uppercase tracking-wide text-default-500">
                  Verified in last 30 days
                </p>
                <p className="mb-2 text-2xl font-semibold text-default-900">
                  {fmtPct(data.coverage.linkedin_verified_last_30d_pct)}
                </p>
                <ProgressBar pct={data.coverage.linkedin_verified_last_30d_pct} />
              </CardBody>
            </Card>
          </div>

          {/* Recent runs */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">
              Recent runs ({data.recent_runs.length})
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-default-500">
                  <tr>
                    <th className="py-2 pr-3 font-medium">When</th>
                    <th className="py-2 pr-3 font-medium">Command</th>
                    <th className="py-2 pr-3 font-medium">Examined</th>
                    <th className="py-2 pr-3 font-medium">Wall</th>
                    <th className="py-2 pr-3 font-medium">Outcomes</th>
                  </tr>
                </thead>
                <tbody className="text-default-700">
                  {data.recent_runs.length === 0 && (
                    <tr><td colSpan={5} className="py-3 text-default-400">No runs yet</td></tr>
                  )}
                  {data.recent_runs.map((r) => (
                    <tr key={r.id} className="border-t border-default-100">
                      <td className="py-2 pr-3 whitespace-nowrap" title={r.started_at}>
                        {timeAgo(r.started_at)}
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {r.command === "verify_job_status" ? "verify" : "extract"}
                        {r.dry_run && <span className="ml-1 text-default-400">(dry-run)</span>}
                      </td>
                      <td className="py-2 pr-3">{r.total_examined}</td>
                      <td className="py-2 pr-3">{r.wall_clock_s.toFixed(1)}s</td>
                      <td className="py-2 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(r.counts_by_outcome).map(([k, n]) => OUTCOME_BADGE(k, n as number))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
