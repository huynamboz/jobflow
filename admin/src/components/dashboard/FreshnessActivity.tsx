import { dashboardService } from "@/services/dashboard.service";
import type { FreshnessActivity as Payload } from "@/types/dashboard.types";

import AreaSeries from "./charts/AreaSeries";
import StackedBar from "./charts/StackedBar";
import SectionCard, { NODE_DESC } from "./SectionCard";
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
      description="Catalog inflow and verifier outcomes over time"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <p style={NODE_DESC}>Jobs added per day, last 30 days</p>
            <div style={{ marginTop: 8 }}>
              <AreaSeries data={data.jobs_added_per_day} ariaLabel="Jobs added per day" color="#3582ff" />
            </div>
          </div>
          <div>
            <p style={NODE_DESC}>Verifier outcomes per day, last 14 days</p>
            <div style={{ marginTop: 8 }}>
              <StackedBar
                data={data.verifier_outcomes_per_day}
                series={VERIFIER_SERIES}
                ariaLabel="Verifier outcomes per day"
              />
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
