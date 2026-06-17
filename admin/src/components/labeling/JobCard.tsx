import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp, SkipForward, Check } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

import type { PairQueueItem, DimScores, DimScore, OverallScore } from "@/types/labeling.types";
import { computeSuggestedOverall } from "@/services/labeling.service";
import { DimScoreInput } from "./DimScoreInput";
import { OverallSelector } from "./OverallSelector";

const REASON_BADGE: Record<string, string> = {
  medium_overlap: "bg-amber-50 border-amber-200 text-amber-700",
  high_overlap:   "bg-emerald-50 border-emerald-200 text-emerald-700",
  hard_negative:  "bg-red-50 border-red-200 text-red-700",
  random:         "bg-gray-50 border-gray-200 text-gray-600",
};

const NULL_DIMS: DimScores = { skill_fit: 0, seniority_fit: 0, experience_fit: 0, domain_fit: 0 };

interface JobCardProps {
  pair: PairQueueItem;
  isActive: boolean;
  onToggle: () => void;
  onSubmit: (pairId: number, dims: DimScores, overall: OverallScore, note: string) => Promise<void>;
  onSkip: (pairId: number) => Promise<void>;
}

export function JobCard({ pair, isActive, onToggle, onSubmit, onSkip }: JobCardProps) {
  const { t } = useTranslation("labeling");
  const [dims, setDims] = useState<DimScores>(NULL_DIMS);
  const [dimsSet, setDimsSet] = useState({ skill_fit: false, seniority_fit: false, experience_fit: false, domain_fit: false });
  const [overall, setOverall] = useState<OverallScore | null>(null);
  const [note, setNote] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset form when card becomes active
  useEffect(() => {
    if (isActive) {
      setDims(NULL_DIMS);
      setDimsSet({ skill_fit: false, seniority_fit: false, experience_fit: false, domain_fit: false });
      setOverall(null);
      setNote("");
    }
  }, [isActive, pair.id]);

  const allDimsSet = Object.values(dimsSet).every(Boolean);
  const suggested = allDimsSet ? computeSuggestedOverall(dims) : null;
  const canSubmit = allDimsSet && overall !== null;

  const setDim = (key: keyof DimScores) => (v: DimScore) => {
    setDims((d) => ({ ...d, [key]: v }));
    setDimsSet((d) => ({ ...d, [key]: true }));
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsSubmitting(true);
    try {
      await onSubmit(pair.id, dims, overall!, note);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSkip = async () => {
    setIsSubmitting(true);
    try { await onSkip(pair.id); } finally { setIsSubmitting(false); }
  };

  const { job } = pair;
  const salaryText = job.salary_min && job.salary_max
    ? `$${job.salary_min.toLocaleString()}–$${job.salary_max.toLocaleString()}`
    : null;

  return (
    <div className={clsx(
      "rounded-2xl border bg-white transition-all duration-150",
      isActive ? "border-blue-300" : "border-default-200",
    )}>
      {/* Card Header — always visible */}
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-5 py-4 text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-default-900 truncate">{job.title || t("jobCard.jobNumber", { id: job.job_id })}</span>
            <span className={clsx(
              "shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize",
              REASON_BADGE[pair.selection_reason],
            )}>
              {pair.selection_reason.replace(/_/g, " ")}
            </span>
          </div>
          <div className="mt-0.5 flex gap-3 text-xs text-default-500">
            <span>{job.seniority}</span>
            {salaryText && <><span>·</span><span>{salaryText}</span></>}
            {pair.skill_overlap_score > 0 && (
              <><span>·</span><span>{t("jobCard.overlap", { percent: Math.round(pair.skill_overlap_score * 100) })}</span></>
            )}
          </div>
        </div>
        <span className="shrink-0 text-default-400">
          {isActive ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </span>
      </button>

      {/* Expanded form */}
      {isActive && (
        <div className="border-t border-default-100 px-5 pb-5 pt-4 space-y-5">
          {/* Job skills */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-default-400">{t("jobCard.jobSkills")}</p>
              {pair.common_skills.length > 0 && (
                <span className="text-xs text-emerald-600">
                  {t("jobCard.common", { count: pair.common_skills.length })}
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((s) => {
                const isCommon = pair.common_skills.includes(s);
                return (
                  <span
                    key={s}
                    className={clsx(
                      "rounded-lg border px-2 py-0.5 text-xs",
                      isCommon
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700 font-medium"
                        : "border-default-200 bg-default-50 text-default-600",
                    )}
                  >
                    {s}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Job summary */}
          {job.text_summary && (
            <p className="text-xs leading-relaxed text-default-500 line-clamp-3 border-l-2 border-default-200 pl-3">
              {job.text_summary}
            </p>
          )}

          {/* Dimension scores */}
          <div className="space-y-2.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-default-400">{t("jobCard.dimensions")}</p>
            <DimScoreInput label={t("jobCard.skillFit")}      value={dimsSet.skill_fit      ? dims.skill_fit      : null} onChange={setDim("skill_fit")} />
            <DimScoreInput label={t("jobCard.seniorityFit")}  value={dimsSet.seniority_fit  ? dims.seniority_fit  : null} onChange={setDim("seniority_fit")} />
            <DimScoreInput label={t("jobCard.experienceFit")} value={dimsSet.experience_fit ? dims.experience_fit : null} onChange={setDim("experience_fit")} />
            <DimScoreInput label={t("jobCard.domainFit")}     value={dimsSet.domain_fit     ? dims.domain_fit     : null} onChange={setDim("domain_fit")} />
          </div>

          {/* Overall */}
          <OverallSelector value={overall} suggested={suggested} onChange={setOverall} />

          {/* Note */}
          <div>
            <textarea
              rows={2}
              placeholder={t("jobCard.notePlaceholder")}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-xl border border-default-200 bg-default-50 px-3 py-2 text-sm text-default-700 placeholder:text-default-400 resize-none focus:outline-none focus:border-blue-300 focus:bg-white transition-colors"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSkip}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded-xl border border-default-200 bg-white px-4 py-2 text-sm text-default-600 hover:bg-default-50 disabled:opacity-50 transition-colors"
            >
              <SkipForward className="size-4" />
              {t("jobCard.skip")}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit || isSubmitting}
              className={clsx(
                "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium transition-all",
                canSubmit
                  ? "bg-blue-500 text-white hover:bg-blue-600"
                  : "border border-default-200 bg-default-100 text-default-400 cursor-not-allowed",
              )}
            >
              <Check className="size-4" />
              {t("jobCard.submit")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
