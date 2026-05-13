import { dashboardService } from "@/services/dashboard.service";
import type { CatalogComposition as Payload } from "@/types/dashboard.types";

import BarH from "./charts/BarH";
import Donut from "./charts/Donut";
import SectionCard from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const LIFECYCLE_COLORS: Record<string, string> = {
  active: "#22c55e",
  stale: "#eab308",
  expired: "#94a3b8",
  unverified: "#a855f7",
};

export default function CatalogComposition({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<Payload>(
    () => dashboardService.getCatalog(),
    refreshKey,
  );

  const empty = !!data && data.by_platform.length === 0 && data.by_lifecycle.length === 0;

  return (
    <SectionCard
      title="Catalog composition"
      description="Where jobs come from and how they break down"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">By platform</p>
            <Donut data={data.by_platform} ariaLabel="Jobs by platform" />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">By lifecycle</p>
            <Donut
              data={data.by_lifecycle}
              ariaLabel="Jobs by lifecycle"
              colors={data.by_lifecycle.map((d) => LIFECYCLE_COLORS[d.key] ?? "#0ea5e9")}
            />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">
              By role category {data.by_role_category.length ? `(${data.by_role_category.length})` : ""}
            </p>
            <BarH data={data.by_role_category} ariaLabel="Jobs by role category" />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-500">By seniority</p>
            <BarH
              data={data.by_seniority.map((d) => ({ key: String(d.key), label: d.label, count: d.count }))}
              ariaLabel="Jobs by seniority"
              color="#a855f7"
            />
          </div>
        </div>
      )}
    </SectionCard>
  );
}
