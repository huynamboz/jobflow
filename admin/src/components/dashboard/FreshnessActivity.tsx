import { dashboardService } from "@/services/dashboard.service";
import type { FreshnessActivity as Payload } from "@/types/dashboard.types";

import AreaSeries from "./charts/AreaSeries";
import StackedBar from "./charts/StackedBar";
import SectionCard, { NODE_LABEL_STYLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const VERIFIER_SERIES = [
  { key: "active",          color: "#49ba61", label: "Active" },
  { key: "expired",         color: "#7b7b7b", label: "Expired" },
  { key: "unknown",         color: "#ffb73a", label: "Unknown" },
  { key: "error",           color: "#fe5938", label: "Error" },
  { key: "session_expired", color: "#8755e9", label: "Session expired" },
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
      description="Inflow · verifier outcomes"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="space-y-5">
          <div>
            <p style={NODE_LABEL_STYLE} className="mb-2">Jobs added per day · 30d</p>
            <AreaSeries
              data={data.jobs_added_per_day}
              ariaLabel="Jobs added per day"
              color="#3582ff"
            />
          </div>
          <div>
            <p style={NODE_LABEL_STYLE} className="mb-2">Verifier outcomes per day · 14d</p>
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
