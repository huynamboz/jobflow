import { dashboardService } from "@/services/dashboard.service";
import type { LabelingSnapshot } from "@/types/dashboard.types";

import { fmtNumber } from "./KpiStrip";
import SectionCard, { NODE_DESC, NODE_META, NODE_TITLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

/** Mini stat card — canonical NODE card spec, slightly smaller scale. */
function MiniStat({
  title, value, accent,
}: { title: string; value: number; accent: string }) {
  return (
    <div
      style={{
        background: "var(--c1)",
        border: "1px solid var(--line)",
        borderRadius: 12,
        boxShadow: "var(--shadow-card)",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div className="flex items-center gap-1.5">
        <span aria-hidden style={{ width: 6, height: 6, borderRadius: 999, background: accent }} />
        <span style={NODE_TITLE}>{title}</span>
      </div>
      <p style={{ font: "500 22px/1 var(--font-node-sans)", letterSpacing: "-0.03em", color: "var(--ink)", margin: 0 }}>
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
      description="Pair queue and selection breakdown"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MiniStat title="Total"   value={data.total_pairs} accent="var(--ink-soft)" />
            <MiniStat title="Labeled" value={data.labeled}     accent="var(--green)" />
            <MiniStat title="Skipped" value={data.skipped}     accent="var(--yellow)" />
            <MiniStat title="Pending" value={data.pending}     accent="var(--blue)" />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p style={NODE_DESC}>By reason</p>
              <ul style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                {Object.entries(data.by_reason).map(([k, v]) => (
                  <li
                    key={k}
                    className="flex items-center justify-between"
                    style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--ink-soft)" }}
                  >
                    <span className="capitalize">{k.replace(/_/g, " ")}</span>
                    <span style={NODE_META}>{fmtNumber(v.labeled)} / {fmtNumber(v.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p style={NODE_DESC}>By split</p>
              <ul style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                {Object.entries(data.by_split).map(([k, v]) => (
                  <li
                    key={k}
                    className="flex items-center justify-between"
                    style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--ink-soft)" }}
                  >
                    <span className="capitalize">{k}</span>
                    <span style={NODE_META}>{fmtNumber(v.labeled)} / {fmtNumber(v.total)}</span>
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
