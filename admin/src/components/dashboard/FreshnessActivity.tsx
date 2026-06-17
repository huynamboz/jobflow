import { useTranslation } from "react-i18next";

import { dashboardService } from "@/services/dashboard.service";
import type { FreshnessActivity as Payload } from "@/types/dashboard.types";

import AreaSeries from "./charts/AreaSeries";
import StackedBar from "./charts/StackedBar";
import SectionCard, { NODE_DESC } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const VERIFIER_SERIES = [
  { key: "active",          color: "#49ba61", labelKey: "freshness.series.active" },
  { key: "expired",         color: "#7b7b7b", labelKey: "freshness.series.expired" },
  { key: "unknown",         color: "#ffb73a", labelKey: "freshness.series.unknown" },
  { key: "error",           color: "#fe5938", labelKey: "freshness.series.error" },
  { key: "session_expired", color: "#8755e9", labelKey: "freshness.series.sessionExpired" },
];

export default function FreshnessActivity({ refreshKey }: Props) {
  const { t } = useTranslation("dashboard");
  const { data, loading, error, reload } = useDashboardSection<Payload>(
    () => dashboardService.getFreshness(),
    refreshKey,
  );

  const empty = !!data && data.jobs_added_per_day.length === 0 && data.verifier_outcomes_per_day.length === 0;
  const verifierSeries = VERIFIER_SERIES.map((s) => ({ key: s.key, color: s.color, label: t(s.labelKey) }));

  return (
    <SectionCard
      title={t("freshness.title")}
      description={t("freshness.description")}
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <p style={NODE_DESC}>{t("freshness.jobsAddedPerDay")}</p>
            <div style={{ marginTop: 8 }}>
              <AreaSeries data={data.jobs_added_per_day} ariaLabel={t("freshness.aria.jobsAddedPerDay")} color="#167a7a" />
            </div>
          </div>
          <div>
            <p style={NODE_DESC}>{t("freshness.verifierOutcomesPerDay")}</p>
            <div style={{ marginTop: 8 }}>
              <StackedBar
                data={data.verifier_outcomes_per_day}
                series={verifierSeries}
                ariaLabel={t("freshness.aria.verifierOutcomesPerDay")}
              />
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
