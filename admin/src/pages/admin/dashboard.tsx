import { useCallback, useState } from "react";
import { RefreshCcw } from "lucide-react";

import AuthStateBanner from "@/components/dashboard/AuthStateBanner";
import CatalogComposition from "@/components/dashboard/CatalogComposition";
import FreshnessActivity from "@/components/dashboard/FreshnessActivity";
import KpiStrip from "@/components/dashboard/KpiStrip";
import LabelingProgress from "@/components/dashboard/LabelingProgress";
import ModelStatus from "@/components/dashboard/ModelStatus";
import VerifierExtractorOps from "@/components/dashboard/VerifierExtractorOps";

export default function DashboardPage() {
  // Bumping refreshKey re-fetches every section in parallel.
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1
            className="font-node-sans text-node-ink"
            style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.025em", lineHeight: 1.05, margin: 0 }}
          >
            Dashboard
          </h1>
          <p
            className="font-node-mono text-node-muted mt-1.5"
            style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}
          >
            System health · Catalog · Ops
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-2 rounded-node-10 px-3 py-2 font-node-sans transition-colors hover:bg-node-c3"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--line-2)",
            boxShadow: "var(--shadow-btn)",
            fontSize: 12.5,
            fontWeight: 600,
            color: "var(--ink)",
          }}
        >
          <RefreshCcw className="size-3.5" strokeWidth={1.75} />
          Refresh
        </button>
      </header>

      <AuthStateBanner refreshKey={refreshKey} />
      <KpiStrip refreshKey={refreshKey} />

      <div className="grid gap-4 xl:grid-cols-2">
        <CatalogComposition refreshKey={refreshKey} />
        <FreshnessActivity refreshKey={refreshKey} />
      </div>

      <VerifierExtractorOps refreshKey={refreshKey} />

      <div className="grid gap-4 xl:grid-cols-2">
        <LabelingProgress refreshKey={refreshKey} />
        <ModelStatus refreshKey={refreshKey} />
      </div>
    </div>
  );
}
