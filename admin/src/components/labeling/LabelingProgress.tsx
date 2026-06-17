import { useTranslation } from "react-i18next";
import type { LabelingProgress } from "@/types/labeling.types";

interface LabelingProgressProps {
  progress: LabelingProgress;
}

export function LabelingProgressBar({ progress }: LabelingProgressProps) {
  const { t } = useTranslation("labeling");
  const pct = progress.total > 0 ? Math.round((progress.labeled / progress.total) * 100) : 0;

  return (
    <div className="rounded-2xl border border-default-200 bg-white px-5 py-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-default-700">
          {t("progress.labeled", { labeled: progress.labeled, total: progress.total })}
        </span>
        <div className="flex gap-4 text-xs text-default-500">
          <span>{t("progress.skipped", { count: progress.skipped })}</span>
          <span>{t("progress.remaining", { count: progress.pending })}</span>
          <span className="font-semibold text-default-700">{pct}%</span>
        </div>
      </div>
      <div className="h-2 rounded-full bg-default-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
