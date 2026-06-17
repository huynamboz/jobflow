import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { OverallScore } from "@/types/labeling.types";

const OPTIONS: { value: OverallScore; labelKey: string; desc: string; active: string; suggested: string }[] = [
  { value: 0, labelKey: "overall.notSuitable", desc: "0", active: "bg-red-50 border-red-400 text-red-700",     suggested: "border-red-300 bg-red-50/50" },
  { value: 1, labelKey: "overall.suitable",    desc: "1", active: "bg-blue-50 border-blue-400 text-blue-700",  suggested: "border-blue-300 bg-blue-50/50" },
  { value: 2, labelKey: "overall.strongFit",   desc: "2", active: "bg-emerald-50 border-emerald-400 text-emerald-700", suggested: "border-emerald-300 bg-emerald-50/50" },
];

interface OverallSelectorProps {
  value: OverallScore | null;
  suggested: OverallScore | null;
  onChange: (v: OverallScore) => void;
}

export function OverallSelector({ value, suggested, onChange }: OverallSelectorProps) {
  const { t } = useTranslation("labeling");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-default-700">{t("overall.label")}</span>
        {suggested !== null && value === null && (
          <span className="text-xs text-default-400">{t("overall.suggested", { label: t(OPTIONS[suggested].labelKey) })}</span>
        )}
      </div>
      <div className="flex gap-2">
        {OPTIONS.map((opt) => {
          const isSelected = value === opt.value;
          const isSuggested = suggested === opt.value && value === null;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              className={clsx(
                "flex-1 rounded-xl border px-3 py-2.5 text-sm font-medium transition-all",
                isSelected
                  ? opt.active
                  : isSuggested
                    ? opt.suggested + " text-default-600"
                    : "border-default-200 bg-white text-default-500 hover:border-default-300 hover:bg-default-50",
              )}
            >
              <span className="block text-xs font-normal text-current opacity-60">{opt.desc}</span>
              {t(opt.labelKey)}
              {isSuggested && !isSelected && <span className="ml-1 text-[10px] opacity-60">✦</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
