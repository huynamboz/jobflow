import { useTranslation } from "react-i18next";

import { dashboardService } from "@/services/dashboard.service";
import type { CatalogComposition as Payload } from "@/types/dashboard.types";

import BarH from "./charts/BarH";
import Donut from "./charts/Donut";
import SectionCard, { NODE_DESC } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

const NODE_PALETTE = [
  "#167a7a", "#49ba61", "#e36323", "#ffb73a", "#8755e9", "#fe5938", "#7b7b7b", "#323232",
];

const LIFECYCLE_COLOR_MAP: Record<string, string> = {
  active:     "#49ba61",
  stale:      "#ffb73a",
  expired:    "#7b7b7b",
  unverified: "#8755e9",
};

function Pane({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p style={NODE_DESC}>{label}</p>
      <div style={{ marginTop: 8 }}>{children}</div>
    </div>
  );
}

export default function CatalogComposition({ refreshKey }: Props) {
  const { t } = useTranslation("dashboard");
  const { data, loading, error, reload } = useDashboardSection<Payload>(
    () => dashboardService.getCatalog(),
    refreshKey,
  );

  const empty = !!data && data.by_platform.length === 0 && data.by_lifecycle.length === 0;

  return (
    <SectionCard
      title={t("catalog.title")}
      description={t("catalog.description")}
      loading={loading} error={error} empty={empty}
      onRetry={reload}
    >
      {data && (
        <div className="grid gap-5 sm:grid-cols-2">
          <Pane label={t("catalog.byPlatform")}>
            <Donut data={data.by_platform} ariaLabel={t("catalog.aria.byPlatform")} colors={NODE_PALETTE} />
          </Pane>
          <Pane label={t("catalog.byLifecycle")}>
            <Donut
              data={data.by_lifecycle}
              ariaLabel={t("catalog.aria.byLifecycle")}
              colors={data.by_lifecycle.map((d) => LIFECYCLE_COLOR_MAP[d.key] ?? NODE_PALETTE[0])}
            />
          </Pane>
          <Pane label={data.by_role_category.length ? t("catalog.byRoleCategoryCount", { count: data.by_role_category.length }) : t("catalog.byRoleCategory")}>
            <BarH data={data.by_role_category} ariaLabel={t("catalog.aria.byRoleCategory")} color="#167a7a" />
          </Pane>
          <Pane label={t("catalog.bySeniority")}>
            <BarH
              data={data.by_seniority.map((d) => ({ key: String(d.key), label: d.label, count: d.count }))}
              ariaLabel={t("catalog.aria.bySeniority")}
              color="#8755e9"
            />
          </Pane>
        </div>
      )}
    </SectionCard>
  );
}
