import { useTranslation } from "react-i18next";

import { dashboardService } from "@/services/dashboard.service";
import type { ModelSnapshot } from "@/types/dashboard.types";

import SectionCard, { NODE_DESC, NODE_META, NODE_TITLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

/** Mini metric card — canonical NODE card spec, small scale. */
function Metric({ title, value }: { title: string; value: number | null }) {
  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid var(--line)",
        borderRadius: 16,
        boxShadow: "var(--shadow-card)",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <p style={NODE_TITLE}>{title}</p>
      <p style={{ font: "500 22px/1 var(--font-node-sans)", letterSpacing: "-0.03em", color: "var(--ink)", margin: 0 }}>
        {value == null ? "—" : value.toFixed(3)}
      </p>
    </div>
  );
}

export default function ModelStatus({ refreshKey }: Props) {
  const { t } = useTranslation("dashboard");
  const { data, loading, error, reload } = useDashboardSection<ModelSnapshot>(
    () => dashboardService.getModel(),
    refreshKey,
  );

  const empty = !!data && data.checkpoint_name == null;

  return (
    <SectionCard
      title={t("model.title")}
      description={t("model.description")}
      loading={loading} error={error} empty={empty}
      emptyMessage={t("model.emptyMessage")}
      onRetry={reload}
    >
      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <p style={NODE_TITLE}>{t("model.checkpoint")}</p>
            <p style={{ font: "500 16px/22px var(--font-node-mono)", letterSpacing: "-0.02em", color: "var(--ink)", margin: 0 }}>
              {data.checkpoint_name}
            </p>
            {data.trained_at && (
              <p style={{ ...NODE_META, marginTop: 2 }} title={data.trained_at}>
                {t("model.trained", { date: new Date(data.trained_at).toLocaleDateString() })}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric title={t("model.aucRoc")} value={data.metrics.test_auc_roc} />
            <Metric title={t("model.ndcg5")}  value={data.metrics.ndcg_at_5} />
            <Metric title={t("model.mrr")}     value={data.metrics.mrr} />
            <Metric title={t("model.p5")}     value={data.metrics.precision_at_5} />
          </div>

          {data.calibration && (
            <p style={NODE_DESC}>
              <span style={NODE_META}>
                {t("model.calibration", { a: data.calibration.a.toFixed(3), b: data.calibration.b.toFixed(3) })}
              </span>
            </p>
          )}
        </div>
      )}
    </SectionCard>
  );
}
