import { dashboardService } from "@/services/dashboard.service";
import type { OpsHealth } from "@/types/dashboard.types";

import { fmtPct, timeAgo } from "./KpiStrip";
import SectionCard, { NODE_LABEL_STYLE, NODE_NUMBER_STYLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function ProgressBar({ pct, color = "var(--blue)" }: { pct: number; color?: string }) {
  const w = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-node-2"
      style={{ background: "var(--sunken)" }}
    >
      <div className="h-full rounded-node-2" style={{ width: `${w}%`, background: color }} />
    </div>
  );
}

const OUTCOME_PILL = (key: string, n: number) => {
  if (!n) return null;
  const colorMap: Record<string, { fg: string; bg: string }> = {
    active:          { fg: "var(--green)",  bg: "rgba(73,186,97,0.10)" },
    expired:         { fg: "var(--ink-soft)", bg: "var(--c3)" },
    populated:       { fg: "var(--blue)",   bg: "rgba(53,130,255,0.10)" },
    expired_marked:  { fg: "var(--ink-soft)", bg: "var(--c3)" },
    unknown:         { fg: "var(--orange)", bg: "rgba(227,99,35,0.10)" },
    none:            { fg: "var(--orange)", bg: "rgba(227,99,35,0.10)" },
    error:           { fg: "var(--red)",    bg: "rgba(254,89,56,0.10)" },
    session_expired: { fg: "var(--purple)", bg: "rgba(135,85,233,0.10)" },
  };
  const c = colorMap[key] ?? { fg: "var(--ink-soft)", bg: "var(--c3)" };
  return (
    <span
      key={key}
      className="inline-flex items-center gap-1 rounded-node-6 px-1.5 py-0.5 font-node-mono"
      style={{ background: c.bg, color: c.fg, fontSize: 10, fontWeight: 600, letterSpacing: "0.04em" }}
    >
      {key} {n}
    </span>
  );
};

function CoverageCard({
  label, pct, color,
}: { label: string; pct: number; color: string }) {
  return (
    <div
      className="rounded-node-16"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        padding: 14,
      }}
    >
      <p style={NODE_LABEL_STYLE}>{label}</p>
      <p className="mt-2 mb-3" style={{ ...NODE_NUMBER_STYLE, fontSize: 28, lineHeight: 1 }}>
        {fmtPct(pct)}
      </p>
      <ProgressBar pct={pct} color={color} />
    </div>
  );
}

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
      description="Coverage · recent runs"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <CoverageCard
              label="LinkedIn jobs with date_posted"
              pct={data.coverage.linkedin_with_date_posted_pct}
              color="var(--blue)"
            />
            <CoverageCard
              label="Verified in last 30 days"
              pct={data.coverage.linkedin_verified_last_30d_pct}
              color="var(--green)"
            />
          </div>

          <div>
            <p style={NODE_LABEL_STYLE} className="mb-2">
              Recent runs ({data.recent_runs.length})
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr style={NODE_LABEL_STYLE}>
                    <th className="py-2 pr-3 font-normal">When</th>
                    <th className="py-2 pr-3 font-normal">Command</th>
                    <th className="py-2 pr-3 font-normal">Examined</th>
                    <th className="py-2 pr-3 font-normal">Wall</th>
                    <th className="py-2 pr-3 font-normal">Outcomes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.length === 0 && (
                    <tr><td colSpan={5} className="py-4 text-node-muted" style={{ fontSize: 12 }}>No runs yet</td></tr>
                  )}
                  {data.recent_runs.map((r) => (
                    <tr key={r.id} style={{ borderTop: "1px solid var(--line)" }}>
                      <td
                        className="py-2.5 pr-3 whitespace-nowrap font-node-mono text-node-ink-soft"
                        style={{ fontSize: 12 }}
                        title={r.started_at}
                      >
                        {timeAgo(r.started_at)} ago
                      </td>
                      <td className="py-2.5 pr-3 whitespace-nowrap text-node-ink" style={{ fontSize: 12, fontWeight: 500 }}>
                        {r.command === "verify_job_status" ? "verify" : "extract"}
                        {r.dry_run && (
                          <span
                            className="ml-1.5 font-node-mono text-node-muted"
                            style={{ fontSize: 10, letterSpacing: "0.05em", textTransform: "uppercase" }}
                          >
                            dry
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 font-node-mono text-node-ink" style={{ fontSize: 12 }}>
                        {r.total_examined}
                      </td>
                      <td className="py-2.5 pr-3 font-node-mono text-node-muted" style={{ fontSize: 12 }}>
                        {r.wall_clock_s.toFixed(1)}s
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(r.counts_by_outcome).map(([k, n]) => OUTCOME_PILL(k, n as number))}
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
