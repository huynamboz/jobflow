import { dashboardService } from "@/services/dashboard.service";
import type { CatalogComposition as Payload } from "@/types/dashboard.types";

import BarH from "./charts/BarH";
import Donut from "./charts/Donut";
import SectionCard, { NODE_LABEL_STYLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const NODE_PALETTE = [
  "#3582ff", // blue
  "#49ba61", // green
  "#e36323", // orange
  "#ffb73a", // yellow
  "#8755e9", // purple
  "#fe5938", // red
  "#7b7b7b", // muted
  "#323232", // ink-soft
];

const LIFECYCLE_COLOR_MAP: Record<string, string> = {
  active:     "#49ba61",
  stale:      "#ffb73a",
  expired:    "#7b7b7b",
  unverified: "#8755e9",
};

function Pane({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p style={NODE_LABEL_STYLE} className="mb-2">{label}</p>
      {children}
    </div>
  );
}

export default function CatalogComposition({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<Payload>(
    () => dashboardService.getCatalog(),
    refreshKey,
  );

  const empty = !!data && data.by_platform.length === 0 && data.by_lifecycle.length === 0;

  return (
    <SectionCard
      title="Catalog composition"
      description="Platform · lifecycle · role · seniority"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="grid gap-5 sm:grid-cols-2">
          <Pane label="By platform">
            <Donut data={data.by_platform} ariaLabel="Jobs by platform" colors={NODE_PALETTE} />
          </Pane>
          <Pane label="By lifecycle">
            <Donut
              data={data.by_lifecycle}
              ariaLabel="Jobs by lifecycle"
              colors={data.by_lifecycle.map((d) => LIFECYCLE_COLOR_MAP[d.key] ?? NODE_PALETTE[0])}
            />
          </Pane>
          <Pane label={`By role category${data.by_role_category.length ? ` (${data.by_role_category.length})` : ""}`}>
            <BarH data={data.by_role_category} ariaLabel="Jobs by role category" color="#3582ff" />
          </Pane>
          <Pane label="By seniority">
            <BarH
              data={data.by_seniority.map((d) => ({ key: String(d.key), label: d.label, count: d.count }))}
              ariaLabel="Jobs by seniority"
              color="#8755e9"
            />
          </Pane>
        </div>
      )}
    </SectionCard>
  );
}
