import { dashboardService } from "@/services/dashboard.service";
import type { ModelSnapshot } from "@/types/dashboard.types";

import SectionCard, { NODE_LABEL_STYLE, NODE_NUMBER_STYLE } from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div
      className="rounded-node-12"
      style={{ background: "var(--c2)", border: "1px solid var(--line)", padding: "10px 12px" }}
    >
      <p style={NODE_LABEL_STYLE}>{label}</p>
      <p className="mt-1" style={{ ...NODE_NUMBER_STYLE, fontSize: 20, lineHeight: 1 }}>
        {value == null ? "—" : value.toFixed(3)}
      </p>
    </div>
  );
}

export default function ModelStatus({ refreshKey }: Props) {
  const { data, loading, error, reload } = useDashboardSection<ModelSnapshot>(
    () => dashboardService.getModel(),
    refreshKey,
  );

  const empty = !!data && data.checkpoint_name == null;

  return (
    <SectionCard
      title="Model"
      description="Active GNN checkpoint"
      loading={loading} error={error} empty={empty}
      emptyMessage="No model active (set ML_CHECKPOINT_DIR + meta.json)"
      onRetry={reload}
    >
      {data && (
        <div className="space-y-3">
          <div>
            <p style={NODE_LABEL_STYLE}>Checkpoint</p>
            <p
              className="font-node-mono text-node-ink mt-1"
              style={{ fontSize: 14, fontWeight: 500, letterSpacing: "-0.02em" }}
            >
              {data.checkpoint_name}
            </p>
            {data.trained_at && (
              <p className="text-node-muted" style={{ fontSize: 11, marginTop: 2 }} title={data.trained_at}>
                trained {new Date(data.trained_at).toLocaleDateString()}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="AUC-ROC" value={data.metrics.test_auc_roc} />
            <Metric label="NDCG@5"  value={data.metrics.ndcg_at_5} />
            <Metric label="MRR"     value={data.metrics.mrr} />
            <Metric label="P@5"     value={data.metrics.precision_at_5} />
          </div>
          {data.calibration && (
            <p
              className="font-node-mono text-node-muted"
              style={{ fontSize: 11, letterSpacing: "0.02em" }}
            >
              calibration · a={data.calibration.a.toFixed(3)} · b={data.calibration.b.toFixed(3)}
            </p>
          )}
        </div>
      )}
    </SectionCard>
  );
}
