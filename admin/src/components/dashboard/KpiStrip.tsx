import {
  Briefcase, CheckCircle2, Clock, Cpu, FileText, KeyRound, ShieldAlert,
} from "lucide-react";

import { dashboardService } from "@/services/dashboard.service";
import type { Freshness, KpiSnapshot } from "@/types/dashboard.types";

import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const FRESHNESS_LABEL: Record<Freshness, string> = {
  fresh:      "Fresh · ≤24h",
  stale:      "Stale · ≤72h",
  very_stale: "Stale · >72h",
  never:      "Never run",
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

/* ─── NODE Tile (KPI card) ──────────────────────────────────────────── */

function Tile({
  icon: Icon,
  label,
  value,
  sub,
  dotColor,
  iconColor,
  iconBg,
  valueMono = true,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  dotColor?: string;
  iconColor?: string;
  iconBg?: string;
  valueMono?: boolean;
}) {
  return (
    <div
      className="rounded-node-20"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        boxShadow: "var(--shadow-card)",
        padding: 16,
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="font-node-mono text-node-muted"
          style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}
        >
          {label}
        </span>
        {dotColor && (
          <span
            aria-hidden
            className="inline-block"
            style={{ width: 6, height: 6, borderRadius: 999, background: dotColor }}
          />
        )}
        <div className="flex-1" />
        <span
          className="inline-flex items-center justify-center shrink-0"
          style={{
            width: 28,
            height: 28,
            borderRadius: "var(--r-8)",
            background: iconBg ?? "var(--c3)",
            color: iconColor ?? "var(--ink-soft)",
          }}
        >
          <Icon className="size-3.5" strokeWidth={1.75} />
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span
          className="truncate"
          style={{
            fontFamily: valueMono ? "var(--font-node-mono)" : "var(--font-node-sans)",
            fontSize: 26,
            fontWeight: 500,
            letterSpacing: "-0.03em",
            color: "var(--ink)",
            lineHeight: 1.05,
          }}
          title={value}
        >
          {value}
        </span>
      </div>

      {sub && (
        <p
          className="font-node-sans text-node-muted mt-1 truncate"
          style={{ fontSize: 11.5, letterSpacing: "-0.005em" }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

function TileSkeleton() {
  return (
    <div
      className="rounded-node-20 animate-pulse"
      style={{ background: "var(--surface)", border: "1px solid var(--line)", height: 116 }}
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
        label="Jobs"
        value={fmtNumber(jobs_total)}
        sub={`${fmtNumber(jobs_by_lifecycle.active)} active · ${fmtNumber(jobs_by_lifecycle.expired)} expired`}
        iconBg="rgba(53,130,255,0.10)"
        iconColor="var(--blue)"
      />
      <Tile
        icon={FileText}
        label="CVs"
        value={fmtNumber(cv_total)}
        sub={`+${fmtNumber(cv_uploads_last_7d)} last 7d`}
        iconBg="rgba(73,186,97,0.10)"
        iconColor="var(--green)"
      />
      <Tile
        icon={CheckCircle2}
        label="Verifier"
        value={timeAgo(verifier_last_run.started_at)}
        sub={FRESHNESS_LABEL[verifier_last_run.freshness]}
        dotColor={FRESHNESS_DOT[verifier_last_run.freshness]}
        iconBg="rgba(73,186,97,0.10)"
        iconColor="var(--green)"
      />
      <Tile
        icon={Clock}
        label="Extractor"
        value={timeAgo(extractor_last_run.started_at)}
        sub={FRESHNESS_LABEL[extractor_last_run.freshness]}
        dotColor={FRESHNESS_DOT[extractor_last_run.freshness]}
        iconBg="rgba(227,99,35,0.10)"
        iconColor="var(--orange)"
      />
      <Tile
        icon={auth_state.has_li_at ? KeyRound : ShieldAlert}
        label="Auth state"
        value={auth_state.has_li_at ? "Valid" : "Missing"}
        sub={auth_state.has_li_at ? "li_at present" : "run linkedin_auth.py"}
        dotColor={auth_state.has_li_at ? "var(--green)" : "var(--red)"}
        iconBg={auth_state.has_li_at ? "rgba(73,186,97,0.10)" : "rgba(254,89,56,0.10)"}
        iconColor={auth_state.has_li_at ? "var(--green)" : "var(--red)"}
        valueMono={false}
      />
      <Tile
        icon={Cpu}
        label="Model"
        value={model.checkpoint_name ?? "—"}
        sub={model.metrics.test_auc_roc != null ? `AUC ${model.metrics.test_auc_roc.toFixed(3)}` : "no metrics"}
        iconBg="rgba(135,85,233,0.10)"
        iconColor="var(--purple)"
        valueMono={false}
      />
    </div>
  );
}

export { fmtNumber, fmtPct, timeAgo };
