import {
  Briefcase, CheckCircle2, Clock, Cpu, FileText, KeyRound, ShieldAlert,
} from "lucide-react";

import { dashboardService } from "@/services/dashboard.service";
import type { Freshness, KpiSnapshot } from "@/types/dashboard.types";

import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const FRESHNESS_LABEL: Record<Freshness, string> = {
  fresh:      "fresh · ≤24h",
  stale:      "stale · ≤72h",
  very_stale: "stale · >72h",
  never:      "never run",
};

const FRESHNESS_DOT: Record<Freshness, string> = {
  fresh:      "var(--green)",
  stale:      "var(--yellow)",
  very_stale: "var(--red)",
  never:      "var(--c5)",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h`;
  return `${Math.round(sec / 86400)}d`;
}

function fmtNumber(n: number) {
  return new Intl.NumberFormat().format(n);
}

function fmtPct(n: number | null | undefined, digits = 1) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

/* ─── NODE canonical card — KPI tile ─────────────────────────────────
 * Mirrors preview/components-cards.html .card shell exactly:
 *   bg c1, 1px line, radius 16, shadow-card, padding 16, gap 8.
 *   title: 600 13px/18px sans -0.01em
 *   display number: 500 28px/1 sans -0.03em
 *   meta: 400 11px/16px mono muted
 */
function Tile({
  icon: Icon,
  title,
  value,
  meta,
  dotColor,
  iconColor,
  iconBg,
}: {
  icon: React.ElementType;
  title: string;
  value: string;
  meta?: string;
  dotColor?: string;
  iconColor?: string;
  iconBg?: string;
}) {
  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid var(--line)",
        borderRadius: 16,
        boxShadow: "var(--shadow-card)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div className="flex items-center gap-2">
        <span
          style={{
            font: "600 13px/18px var(--font-node-sans)",
            letterSpacing: "-0.01em",
            color: "var(--ink)",
          }}
        >
          {title}
        </span>
        {dotColor && (
          <span
            aria-hidden
            style={{ width: 6, height: 6, borderRadius: 999, background: dotColor }}
          />
        )}
        <div className="flex-1" />
        <span
          className="inline-flex items-center justify-center shrink-0"
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: iconBg ?? "var(--c3)",
            color: iconColor ?? "var(--ink-soft)",
          }}
        >
          <Icon className="size-3.5" strokeWidth={1.75} />
        </span>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span
          className="truncate"
          style={{
            font: "500 28px/1 var(--font-node-sans)",
            letterSpacing: "-0.03em",
            color: "var(--ink)",
          }}
          title={value}
        >
          {value}
        </span>
      </div>

      {meta && (
        <p
          style={{
            font: "400 11px/16px var(--font-node-mono)",
            color: "var(--muted)",
            margin: 0,
          }}
          className="truncate"
        >
          {meta}
        </p>
      )}
    </div>
  );
}

function TileSkeleton() {
  return (
    <div
      className="animate-pulse"
      style={{
        background: "#ffffff",
        border: "1px solid var(--line)",
        borderRadius: 16,
        boxShadow: "var(--shadow-card)",
        height: 104,
      }}
    />
  );
}

export default function KpiStrip({ refreshKey }: Props) {
  const { data, loading } = useDashboardSection<KpiSnapshot>(
    () => dashboardService.getKpi(),
    refreshKey,
  );

  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => <TileSkeleton key={i} />)}
      </div>
    );
  }

  const {
    jobs_total, jobs_by_lifecycle, cv_total, cv_uploads_last_7d,
    verifier_last_run, extractor_last_run, auth_state, model,
  } = data;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Tile
        icon={Briefcase}
        title="Jobs"
        value={fmtNumber(jobs_total)}
        meta={`${fmtNumber(jobs_by_lifecycle.active)} active · ${fmtNumber(jobs_by_lifecycle.expired)} expired`}
        iconBg="rgba(53,130,255,0.10)"
        iconColor="var(--blue)"
      />
      <Tile
        icon={FileText}
        title="CVs"
        value={fmtNumber(cv_total)}
        meta={`+${fmtNumber(cv_uploads_last_7d)} last 7d`}
        iconBg="rgba(73,186,97,0.10)"
        iconColor="var(--green)"
      />
      <Tile
        icon={CheckCircle2}
        title="Verifier"
        value={timeAgo(verifier_last_run.started_at)}
        meta={FRESHNESS_LABEL[verifier_last_run.freshness]}
        dotColor={FRESHNESS_DOT[verifier_last_run.freshness]}
        iconBg="rgba(73,186,97,0.10)"
        iconColor="var(--green)"
      />
      <Tile
        icon={Clock}
        title="Extractor"
        value={timeAgo(extractor_last_run.started_at)}
        meta={FRESHNESS_LABEL[extractor_last_run.freshness]}
        dotColor={FRESHNESS_DOT[extractor_last_run.freshness]}
        iconBg="rgba(227,99,35,0.10)"
        iconColor="var(--orange)"
      />
      <Tile
        icon={auth_state.has_li_at ? KeyRound : ShieldAlert}
        title="Auth"
        value={auth_state.has_li_at ? "Valid" : "Missing"}
        meta={auth_state.has_li_at ? "li_at present" : "run linkedin_auth.py"}
        dotColor={auth_state.has_li_at ? "var(--green)" : "var(--red)"}
        iconBg={auth_state.has_li_at ? "rgba(73,186,97,0.10)" : "rgba(254,89,56,0.10)"}
        iconColor={auth_state.has_li_at ? "var(--green)" : "var(--red)"}
      />
      <Tile
        icon={Cpu}
        title="Model"
        value={model.checkpoint_name ?? "—"}
        meta={model.metrics.test_auc_roc != null ? `auc ${model.metrics.test_auc_roc.toFixed(3)}` : "no metrics"}
        iconBg="rgba(135,85,233,0.10)"
        iconColor="var(--purple)"
      />
    </div>
  );
}

export { fmtNumber, fmtPct, timeAgo };
