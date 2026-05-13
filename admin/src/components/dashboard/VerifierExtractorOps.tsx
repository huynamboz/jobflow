import { dashboardService } from "@/services/dashboard.service";
import type { OpsHealth } from "@/types/dashboard.types";

import { fmtPct, timeAgo } from "./KpiStrip";
import SectionCard, { NODE_DESC, NODE_META, NODE_TITLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function ProgressBar({ pct, color = "var(--blue)" }: { pct: number; color?: string }) {
  const w = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div style={{ height: 6, width: "100%", background: "var(--sunken)", borderRadius: 2, overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${w}%`, background: color, borderRadius: 2 }} />
    </div>
  );
}

const OUTCOME_PILL = (key: string, n: number) => {
  if (!n) return null;
  const map: Record<string, { fg: string; bg: string }> = {
    active:          { fg: "var(--green)",    bg: "rgba(73,186,97,0.10)" },
    expired:         { fg: "var(--ink-soft)", bg: "var(--c3)" },
    populated:       { fg: "var(--blue)",     bg: "rgba(53,130,255,0.10)" },
    expired_marked:  { fg: "var(--ink-soft)", bg: "var(--c3)" },
    unknown:         { fg: "var(--orange)",   bg: "rgba(227,99,35,0.10)" },
    none:            { fg: "var(--orange)",   bg: "rgba(227,99,35,0.10)" },
    error:           { fg: "var(--red)",      bg: "rgba(254,89,56,0.10)" },
    session_expired: { fg: "var(--purple)",   bg: "rgba(135,85,233,0.10)" },
  };
  const c = map[key] ?? { fg: "var(--ink-soft)", bg: "var(--c3)" };
  return (
    <span
      key={key}
      style={{
        background: c.bg,
        color: c.fg,
        font: "500 10.5px/14px var(--font-node-mono)",
        padding: "1px 6px",
        borderRadius: 5,
      }}
    >
      {key} {n}
    </span>
  );
};

/** Inner stat card — canonical NODE card spec at smaller scale. */
function CoverageCard({
  title, pct, color,
}: { title: string; pct: number; color: string }) {
  return (
    <div
      style={{
        background: "var(--c1)",
        border: "1px solid var(--line)",
        borderRadius: 16,
        boxShadow: "var(--shadow-card)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <p style={NODE_TITLE}>{title}</p>
      <p
        style={{
          font: "500 28px/1 var(--font-node-sans)",
          letterSpacing: "-0.03em",
          color: "var(--ink)",
          margin: 0,
        }}
      >
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
      description="Coverage and recent runs"
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid gap-3 sm:grid-cols-2">
            <CoverageCard
              title="LinkedIn jobs with date_posted"
              pct={data.coverage.linkedin_with_date_posted_pct}
              color="var(--blue)"
            />
            <CoverageCard
              title="Verified in last 30 days"
              pct={data.coverage.linkedin_verified_last_30d_pct}
              color="var(--green)"
            />
          </div>

          <div>
            <p style={NODE_DESC}>Recent runs ({data.recent_runs.length})</p>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-left">
                <thead>
                  <tr style={{ font: "500 11px/16px var(--font-node-sans)", color: "var(--muted)" }}>
                    <th className="py-2 pr-3 font-normal">When</th>
                    <th className="py-2 pr-3 font-normal">Command</th>
                    <th className="py-2 pr-3 font-normal">Examined</th>
                    <th className="py-2 pr-3 font-normal">Wall</th>
                    <th className="py-2 pr-3 font-normal">Outcomes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ ...NODE_DESC, padding: "12px 0" }}>No runs yet</td>
                    </tr>
                  )}
                  {data.recent_runs.map((r) => (
                    <tr key={r.id} style={{ borderTop: "1px solid var(--line)" }}>
                      <td
                        className="py-2.5 pr-3 whitespace-nowrap"
                        style={NODE_META}
                        title={r.started_at}
                      >
                        {timeAgo(r.started_at)} ago
                      </td>
                      <td
                        className="py-2.5 pr-3 whitespace-nowrap"
                        style={{ font: "500 12px/16px var(--font-node-sans)", color: "var(--ink)" }}
                      >
                        {r.command === "verify_job_status" ? "verify" : "extract"}
                        {r.dry_run && (
                          <span style={{ marginLeft: 6, ...NODE_META }}>dry</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--ink)" }}>
                        {r.total_examined}
                      </td>
                      <td className="py-2.5 pr-3" style={NODE_META}>
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
