import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, Send, Sparkles, Layers } from "lucide-react";

import { Card } from "@/components/ui/card";
import { dashboardService } from "@/services/dashboard.service";
import type { JobsOverview as JobsOverviewData } from "@/types/dashboard.types";
import AreaSeries from "@/components/dashboard/charts/AreaSeries";
import BarH from "@/components/dashboard/charts/BarH";
import Donut from "@/components/dashboard/charts/Donut";

const fmt = new Intl.NumberFormat();

/* ── Stat card (reference style: colored icon circle + label + big number) ── */
function StatCard({
  icon, label, value, accent, sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  accent: string;
  sub?: React.ReactNode;
}) {
  return (
    <Card padding={18}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div
          style={{
            width: 44, height: 44, borderRadius: 12, display: "grid", placeItems: "center",
            background: accent, color: "#fff", boxShadow: `0 6px 16px ${accent}33`,
          }}
        >
          {icon}
        </div>
        <div>
          <div style={{ font: "500 13px/18px var(--font-node-sans)", color: "var(--muted)" }}>{label}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 2 }}>
            <span style={{ font: "700 28px/1.1 var(--font-node-sans)", letterSpacing: "-0.02em", color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>
              {fmt.format(value)}
            </span>
            {sub}
          </div>
        </div>
      </div>
    </Card>
  );
}

function CardTitle({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ font: "700 15px/1.2 var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)" }}>{title}</div>
      {hint && <div style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)", marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

const RANGES = [30, 7, 3] as const;

export default function JobsOverview({ refreshKey = 0 }: { refreshKey?: number }) {
  const { t } = useTranslation("dashboard");
  const [data, setData] = useState<JobsOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<number>(30);

  // Initial / refresh: full load (uses the current range). The range chips do a
  // light refetch (no full spinner) so the stat cards don't flicker.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    dashboardService.getJobsOverview(range)
      .then((d) => { if (alive) setData(d); })
      .catch(console.error)
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const onRange = (d: number) => {
    setRange(d);
    dashboardService.getJobsOverview(d).then(setData).catch(console.error);
  };

  if (loading || !data) {
    return (
      <Card style={{ display: "grid", placeItems: "center", height: 200, color: "var(--muted)" }}>
        {t("jobsOverview.loading")}
      </Card>
    );
  }

  const s = data.stats;
  const donut = [
    { key: t("jobsOverview.statusActive"), count: data.stats.active },
    { key: t("jobsOverview.statusInactive"), count: data.stats.inactive },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── stat cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <StatCard icon={<Briefcase size={20} />} label={t("jobsOverview.statNewToday")} value={s.new_today} accent="#6366f1" />
        <StatCard icon={<Send size={20} />} label={t("jobsOverview.statApplied")} value={s.applied} accent="#15803d" />
        <StatCard icon={<Sparkles size={20} />} label={t("jobsOverview.statSuitable")} value={s.suitable_today} accent="#f59e0b" />
        <StatCard
          icon={<Layers size={20} />} label={t("jobsOverview.statActive")} value={s.active} accent="#167a7a"
          sub={<span style={{ font: "600 12px/16px var(--font-node-sans)", color: "var(--muted)" }}>{t("jobsOverview.ofTotal", { total: fmt.format(s.total) })}</span>}
        />
      </div>

      {/* ── chart row: growth + status ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 16 }}>
        <Card>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
            <div>
              <div style={{ font: "700 15px/1.2 var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)" }}>{t("jobsOverview.growthTitle")}</div>
              <div style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)", marginTop: 2 }}>{t("jobsOverview.growthHint", { count: range })}</div>
            </div>
            <div style={{ display: "inline-flex", gap: 2, background: "var(--c3)", borderRadius: 10, padding: 3, flexShrink: 0 }}>
              {RANGES.map((d) => {
                const active = range === d;
                return (
                  <button key={d} type="button" onClick={() => onRange(d)}
                    style={{
                      border: "none", borderRadius: 8, padding: "5px 10px", cursor: active ? "default" : "pointer",
                      font: "600 12px/16px var(--font-node-sans)",
                      background: active ? "#fff" : "transparent",
                      color: active ? "var(--ink)" : "var(--muted)",
                      boxShadow: active ? "var(--shadow-1)" : "none",
                    }}>
                    {t("jobsOverview.rangeDays", { count: d })}
                  </button>
                );
              })}
            </div>
          </div>
          <AreaSeries data={data.per_day} ariaLabel={t("jobsOverview.ariaGrowth")} color="#6366f1" height={260} />
        </Card>
        <Card>
          <CardTitle title={t("jobsOverview.statusTitle")} hint={t("jobsOverview.statusHint", { count: fmt.format(s.total) })} />
          <Donut data={donut} ariaLabel={t("jobsOverview.ariaStatus")} colors={["#167a7a", "#cbd5e1"]} height={180} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            <LegendRow color="#167a7a" label={t("jobsOverview.statusActive")} value={s.active} />
            <LegendRow color="#cbd5e1" label={t("jobsOverview.statusInactive")} value={s.inactive} />
          </div>
        </Card>
      </div>

      {/* ── provider breakdown ── */}
      <Card>
        <CardTitle title={t("jobsOverview.providerTitle")} hint={t("jobsOverview.providerHint")} />
        <BarH data={data.by_provider} ariaLabel={t("jobsOverview.ariaProvider")} color="#167a7a" height={Math.max(180, data.by_provider.length * 42)} />
      </Card>
    </div>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, font: "500 13px/18px var(--font-node-sans)", color: "var(--ink-soft)" }}>
      <span style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
      <span>{label}</span>
      <span style={{ marginLeft: "auto", fontWeight: 700, color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>{fmt.format(value)}</span>
    </div>
  );
}
