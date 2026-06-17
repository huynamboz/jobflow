import { useEffect, useCallback } from "react";
import { Download, RefreshCw, Tag } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

import { labelingService } from "@/services/labeling.service";
import { useLabelingStore } from "@/stores/labeling.store";
import type { DimScores, OverallScore } from "@/types/labeling.types";
import { CVPanel } from "@/components/labeling/CVPanel";
import { JobCard } from "@/components/labeling/JobCard";
import { LabelingProgressBar } from "@/components/labeling/LabelingProgress";

export default function LabelingPage() {
  const { t } = useTranslation("labeling");
  const {
    currentCV, pairs, progress, activePairId, isLoading, isEmpty,
    setQueue, setEmpty, setLoading, setActivePair, markLabeled, markSkipped,
  } = useLabelingStore();

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await labelingService.getQueue();
      if (!data) { setEmpty(); return; }
      setQueue(data);
    } catch (err) {
      console.error("Failed to fetch queue:", err);
      setLoading(false);
    }
  }, [setQueue, setEmpty, setLoading]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  // When current CV's pairs are all done, fetch next CV
  useEffect(() => {
    if (!isLoading && currentCV && pairs.length === 0) {
      fetchQueue();
    }
  }, [pairs.length, currentCV, isLoading, fetchQueue]);

  const handleSubmit = async (pairId: number, dims: DimScores, overall: OverallScore, note: string) => {
    await labelingService.submitLabel(pairId, { ...dims, overall, note });
    markLabeled(pairId);
  };

  const handleSkip = async (pairId: number) => {
    await labelingService.skipPair(pairId);
    markSkipped(pairId);
  };

  const handleExport = async () => {
    try {
      const data = await labelingService.exportLabels();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `human_labels_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
    }
  };

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-default-900">{t("page.title")}</h1>
          <p className="text-sm text-default-500">{t("page.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={fetchQueue}
            className="flex items-center gap-1.5 rounded-xl border border-default-200 bg-white px-3 py-2 text-sm text-default-600 hover:bg-default-50 transition-colors"
          >
            <RefreshCw className="size-4" />
            {t("page.refresh")}
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-xl border border-default-200 bg-white px-3 py-2 text-sm text-default-600 hover:bg-default-50 transition-colors"
          >
            <Download className="size-4" />
            {t("page.export")}
          </button>
        </div>
      </div>

      {/* Progress bar */}
      {progress && <LabelingProgressBar progress={progress} />}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 text-default-400">
          <RefreshCw className="size-5 animate-spin mr-2" />
          <span className="text-sm">{t("page.loadingQueue")}</span>
        </div>
      )}

      {/* Empty state */}
      {isEmpty && !isLoading && (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-default-200 bg-white py-20 gap-3 text-center">
          <Tag className="size-10 text-default-300" />
          <p className="text-lg font-semibold text-default-700">{t("page.allLabeledTitle")}</p>
          <p className="text-sm text-default-500 max-w-xs">
            <Trans
              i18nKey="page.allLabeledHint"
              t={t}
              components={[<code className="rounded bg-default-100 px-1.5 py-0.5 text-xs" />]}
            />
          </p>
        </div>
      )}

      {/* Main labeling layout */}
      {!isLoading && currentCV && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
          {/* Left: CV Panel */}
          <div>
            <CVPanel cv={currentCV} />
          </div>

          {/* Right: Job cards */}
          <div className="space-y-3">
            {pairs.length === 0 ? (
              <div className="flex items-center justify-center rounded-2xl border border-default-200 bg-white py-12 text-default-400">
                <RefreshCw className="size-4 animate-spin mr-2" />
                <span className="text-sm">{t("page.loadingNextCV")}</span>
              </div>
            ) : (
              pairs.map((pair) => (
                <JobCard
                  key={pair.id}
                  pair={pair}
                  isActive={activePairId === pair.id}
                  onToggle={() => setActivePair(activePairId === pair.id ? null : pair.id)}
                  onSubmit={handleSubmit}
                  onSkip={handleSkip}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
