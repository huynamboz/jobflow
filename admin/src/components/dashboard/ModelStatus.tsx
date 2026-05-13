import { dashboardService } from "@/services/dashboard.service";
import type { ModelSnapshot } from "@/types/dashboard.types";

import SectionCard from "./SectionCard";
import { useDashboardSection } from "./useDashboardSection";

interface Props { refreshKey: number }

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-md border border-default-100 bg-default-50 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-default-500">{label}</p>
      <p className="text-base font-semibold text-default-900">{value == null ? "—" : value.toFixed(3)}</p>
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
            <p className="text-xs uppercase tracking-wide text-default-500">Checkpoint</p>
            <p className="font-mono text-sm text-default-900">{data.checkpoint_name}</p>
            {data.trained_at && (
              <p className="text-xs text-default-500" title={data.trained_at}>
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
            <p className="text-xs text-default-500">
              Calibration: a={data.calibration.a.toFixed(3)}, b={data.calibration.b.toFixed(3)}
            </p>
          )}
        </div>
      )}
    </SectionCard>
  );
}
