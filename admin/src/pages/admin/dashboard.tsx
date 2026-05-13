import { useCallback, useState } from "react";
import { Button } from "@heroui/button";
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
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-default-900">Dashboard</h1>
          <p className="text-default-500">System health, catalog, ops</p>
        </div>
        <Button
          size="sm"
          variant="flat"
          startContent={<RefreshCcw className="size-4" />}
          onPress={refresh}
        >
          Refresh
        </Button>
      </div>

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
