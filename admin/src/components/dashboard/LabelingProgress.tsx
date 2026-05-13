import { dashboardService } from "@/services/dashboard.service";
import type { LabelingSnapshot } from "@/types/dashboard.types";

import { fmtNumber } from "./KpiStrip";
import SectionCard from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`rounded-md px-3 py-2 ${color}`}>
      <p className="text-[10px] uppercase tracking-wide opacity-75">{label}</p>
      <p className="text-base font-semibold">{fmtNumber(value)}</p>
    </div>
  );
}

export default function LabelingProgress({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<LabelingSnapshot>(
    () => dashboardService.getLabeling(),
    refreshKey,
  );

  const empty = !!data && data.total_pairs === 0;

  return (
    <SectionCard
      title="Labeling progress"
      description="Pair queue + selection breakdown"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MiniStat label="Total"   value={data.total_pairs} color="bg-default-100 text-default-700" />
            <MiniStat label="Labeled" value={data.labeled}     color="bg-success-100 text-success-700" />
            <MiniStat label="Skipped" value={data.skipped}     color="bg-warning-100 text-warning-700" />
            <MiniStat label="Pending" value={data.pending}     color="bg-primary-100 text-primary-700" />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-500">By reason</p>
              <ul className="space-y-1 text-xs">
                {Object.entries(data.by_reason).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between">
                    <span className="capitalize text-default-600">{k.replace(/_/g, " ")}</span>
                    <span className="font-medium text-default-800">{fmtNumber(v.labeled)} / {fmtNumber(v.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-500">By split</p>
              <ul className="space-y-1 text-xs">
                {Object.entries(data.by_split).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between">
                    <span className="capitalize text-default-600">{k}</span>
                    <span className="font-medium text-default-800">{fmtNumber(v.labeled)} / {fmtNumber(v.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
