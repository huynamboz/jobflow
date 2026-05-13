import { dashboardService } from "@/services/dashboard.service";
import type { LabelingSnapshot } from "@/types/dashboard.types";

import { fmtNumber } from "./KpiStrip";
import SectionCard, { NODE_LABEL_STYLE, NODE_NUMBER_STYLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function MiniStat({
  label, value, accent,
}: { label: string; value: number; accent: string }) {
  return (
    <div
      className="rounded-node-12"
      style={{
        background: "var(--c2)",
        border: "1px solid var(--line)",
        padding: "10px 12px",
      }}
    >
      <div className="flex items-center gap-1.5">
        <span aria-hidden style={{ width: 5, height: 5, borderRadius: 999, background: accent }} />
        <span style={NODE_LABEL_STYLE}>{label}</span>
      </div>
      <p className="mt-1" style={{ ...NODE_NUMBER_STYLE, fontSize: 20, lineHeight: 1 }}>
        {fmtNumber(value)}
      </p>
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
      description="Pairs · by reason · by split"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MiniStat label="Total"   value={data.total_pairs} accent="var(--ink-soft)" />
            <MiniStat label="Labeled" value={data.labeled}     accent="var(--green)" />
            <MiniStat label="Skipped" value={data.skipped}     accent="var(--yellow)" />
            <MiniStat label="Pending" value={data.pending}     accent="var(--blue)" />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p style={NODE_LABEL_STYLE} className="mb-2">By reason</p>
              <ul className="space-y-1.5">
                {Object.entries(data.by_reason).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between" style={{ fontSize: 12 }}>
                    <span className="capitalize text-node-ink-soft">{k.replace(/_/g, " ")}</span>
                    <span className="font-node-mono text-node-ink" style={{ fontWeight: 500 }}>
                      {fmtNumber(v.labeled)} / {fmtNumber(v.total)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p style={NODE_LABEL_STYLE} className="mb-2">By split</p>
              <ul className="space-y-1.5">
                {Object.entries(data.by_split).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between" style={{ fontSize: 12 }}>
                    <span className="capitalize text-node-ink-soft">{k}</span>
                    <span className="font-node-mono text-node-ink" style={{ fontWeight: 500 }}>
                      {fmtNumber(v.labeled)} / {fmtNumber(v.total)}
                    </span>
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
