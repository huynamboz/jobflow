import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { DimScore } from "@/types/labeling.types";

const OPTIONS: { value: DimScore; emoji: string; labelKey: string; active: string }[] = [
  { value: 0, emoji: "✗", labelKey: "dimScore.bad",  active: "bg-red-50 border-red-300 text-red-600" },
  { value: 1, emoji: "~", labelKey: "dimScore.ok",   active: "bg-amber-50 border-amber-300 text-amber-600" },
  { value: 2, emoji: "✓", labelKey: "dimScore.good", active: "bg-emerald-50 border-emerald-400 text-emerald-700" },
];

interface DimScoreInputProps {
  label: string;
  value: DimScore | null;
  onChange: (v: DimScore) => void;
}

export function DimScoreInput({ label, value, onChange }: DimScoreInputProps) {
  const { t } = useTranslation("labeling");
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-sm text-default-600">{label}</span>
      <div className="flex gap-1.5">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={clsx(
              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all",
              value === opt.value
                ? opt.active
                : "border-default-200 bg-white text-default-500 hover:border-default-300 hover:bg-default-50",
            )}
          >
            <span className="font-mono text-sm">{opt.emoji}</span>
            {t(opt.labelKey)}
          </button>
        ))}
      </div>
    </div>
  );
}
