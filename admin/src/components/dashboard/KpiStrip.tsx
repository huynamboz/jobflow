import { Card, CardBody } from "@heroui/card";
import {
  Briefcase, CheckCircle2, Clock, Cpu, FileText, KeyRound, ShieldAlert,
} from "lucide-react";

import { dashboardService } from "@/services/dashboard.service";
import type { Freshness, KpiSnapshot } from "@/types/dashboard.types";

import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const FRESHNESS_COLORS: Record<Freshness, string> = {
  fresh: "bg-success-500",
  stale: "bg-warning-500",
  very_stale: "bg-danger-500",
  never: "bg-default-300",
};

const FRESHNESS_LABEL: Record<Freshness, string> = {
  fresh: "Fresh (≤24h)",
  stale: "Stale (≤72h)",
  very_stale: "Very stale (>72h)",
  never: "Never run",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return `${Math.round(sec)}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

function fmtNumber(n: number) {
  return new Intl.NumberFormat().format(n);
}

function fmtPct(n: number | null | undefined, digits = 1) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function Kpi({
  icon: Icon, label, value, sub, accent, tone = "default",
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  tone?: "default" | "ok" | "warn" | "danger";
}) {
  const toneRing = {
    default: "bg-default-100 text-default-600",
    ok: "bg-success-100 text-success-700",
    warn: "bg-warning-100 text-warning-700",
    danger: "bg-danger-100 text-danger-700",
  }[tone];
  return (
    <Card className="shadow-sm">
      <CardBody className="flex flex-col gap-1 p-4">
        <div className="flex items-center gap-3">
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${toneRing}`}>
            <Icon className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-wide text-default-500">{label}</p>
            <p className="truncate text-xl font-semibold text-default-900">{value}</p>
          </div>
        </div>
        {sub && (
          <p className="ml-12 truncate text-xs text-default-500" title={accent}>
            {sub}
          </p>
        )}
      </CardBody>
    </Card>
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
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="shadow-sm"><CardBody className="h-20 animate-pulse" /></Card>
        ))}
      </div>
    );
  }

  const { jobs_total, jobs_by_lifecycle, cv_total, cv_uploads_last_7d,
          verifier_last_run, extractor_last_run, auth_state, model } = data;

  const verifierTone: "ok" | "warn" | "danger" | "default" = {
    fresh: "ok", stale: "warn", very_stale: "danger", never: "default",
  }[verifier_last_run.freshness] as any;
  const extractorTone = {
    fresh: "ok", stale: "warn", very_stale: "danger", never: "default",
  }[extractor_last_run.freshness] as any;
  const authTone = auth_state.has_li_at ? "ok" : "danger";

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Kpi icon={Briefcase} label="Jobs" value={fmtNumber(jobs_total)}
           sub={`${fmtNumber(jobs_by_lifecycle.active)} active · ${fmtNumber(jobs_by_lifecycle.expired)} expired`} />
      <Kpi icon={FileText}  label="CVs" value={fmtNumber(cv_total)}
           sub={`+${fmtNumber(cv_uploads_last_7d)} last 7d`} />
      <Kpi icon={CheckCircle2} label="Verifier" value={timeAgo(verifier_last_run.started_at)}
           sub={FRESHNESS_LABEL[verifier_last_run.freshness]} accent={verifier_last_run.started_at ?? undefined} tone={verifierTone} />
      <Kpi icon={Clock} label="Extractor" value={timeAgo(extractor_last_run.started_at)}
           sub={FRESHNESS_LABEL[extractor_last_run.freshness]} accent={extractor_last_run.started_at ?? undefined} tone={extractorTone} />
      <Kpi icon={auth_state.has_li_at ? KeyRound : ShieldAlert}
           label="Auth state"
           value={auth_state.has_li_at ? "Valid" : "Missing li_at"}
           sub={auth_state.file_exists ? "state file present" : "no state file"}
           tone={authTone} />
      <Kpi icon={Cpu} label="Model"
           value={model.checkpoint_name ?? "—"}
           sub={model.metrics.test_auc_roc != null ? `AUC ${model.metrics.test_auc_roc.toFixed(3)}` : "no metrics"} />
    </div>
  );
}

export { FRESHNESS_COLORS, fmtNumber, fmtPct, timeAgo };
