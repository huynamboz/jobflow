import { dashboardService } from "@/services/dashboard.service";
import type { FreshnessActivity as Payload } from "@/types/dashboard.types";

import AreaSeries from "./charts/AreaSeries";
import StackedBar from "./charts/StackedBar";
import SectionCard from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const VERIFIER_SERIES = [
  { key: "active",          color: "#22c55e", label: "Active" },
  { key: "expired",         color: "#94a3b8", label: "Expired" },
  { key: "unknown",         color: "#eab308", label: "Unknown" },
  { key: "error",           color: "#ef4444", label: "Error" },
  { key: "session_expired", color: "#0ea5e9", label: "Session expired" },
];

export default function FreshnessActivity({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<Payload>(
    () => dashboardService.getFreshness(),
    refreshKey,
  );

  const empty = !!data && data.jobs_added_per_day.length === 0 && data.verifier_outcomes_per_day.length === 0;

  return (
    <SectionCard
      title="Freshness & activity"
      description="Catalog growth + verifier outcomes over time"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">
              Jobs added per day (30d)
            </p>
            <AreaSeries data={data.jobs_added_per_day} ariaLabel="Jobs added per day" />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">
              Verifier outcomes per day (14d)
            </p>
            <StackedBar
              data={data.verifier_outcomes_per_day}
              series={VERIFIER_SERIES}
              ariaLabel="Verifier outcomes per day"
            />
          </div>
        </div>
      )}
    </SectionCard>
  );
}
