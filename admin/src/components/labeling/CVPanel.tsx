import { useState, useEffect, useCallback } from "react";
import { FileText, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/lib/api-client";
import type { LabelingCV } from "@/types/labeling.types";

interface CVPanelProps {
  cv: LabelingCV;
}

const SENIORITY_COLOR: Record<string, string> = {
  INTERN:  "bg-gray-100 text-gray-600",
  JUNIOR:  "bg-blue-100 text-blue-700",
  MID:     "bg-indigo-100 text-indigo-700",
  SENIOR:  "bg-purple-100 text-purple-700",
  LEAD:    "bg-pink-100 text-pink-700",
  MANAGER: "bg-rose-100 text-rose-700",
};

export function CVPanel({ cv }: CVPanelProps) {
  const { t } = useTranslation("labeling");
  const seniorityClass = SENIORITY_COLOR[cv.seniority] ?? "bg-default-100 text-default-600";
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const handleOpenPdf = async () => {
    setPdfLoading(true);
    try {
      const res = await apiClient.get<Blob>(`/labeling/cvs/${cv.cv_id}/pdf/`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      setPdfUrl(url);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleClosePdf = useCallback(() => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    setPdfUrl(null);
  }, [pdfUrl]);

  // Close on Escape key
  useEffect(() => {
    if (!pdfUrl) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") handleClosePdf(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pdfUrl, handleClosePdf]);

  return (
    <>
    <div className="rounded-2xl border border-default-200 bg-white p-5 space-y-4 sticky top-4">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${seniorityClass}`}>
            {cv.seniority}
          </span>
          <span className="text-xs text-default-500">{t("cvPanel.cvNumber", { id: cv.cv_id })}</span>
          {cv.pdf_path && (
            <button
              type="button"
              onClick={handleOpenPdf}
              disabled={pdfLoading}
              className="ml-auto flex items-center gap-1 rounded-lg border border-default-200 bg-white px-2 py-1 text-xs text-default-600 hover:bg-default-50 disabled:opacity-50 transition-colors"
            >
              <FileText className="size-3.5" />
              {pdfLoading ? t("cvPanel.loadingPdf") : t("cvPanel.pdf")}
            </button>
          )}
        </div>
        <div className="flex gap-4 text-sm text-default-600 mt-2">
          <span>{t("cvPanel.expYears", { count: cv.experience_years })}</span>
          <span>·</span>
          <span>{cv.education}</span>
          <span>·</span>
          <span className="capitalize">{cv.source}</span>
        </div>
      </div>

      {/* Skills */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-400">{t("cvPanel.skills")}</p>
        <div className="flex flex-wrap gap-1.5">
          {cv.skills.slice(0, 20).map((s) => (
            <span key={s} className="rounded-lg border border-default-200 bg-default-50 px-2 py-0.5 text-xs text-default-600">
              {s}
            </span>
          ))}
          {cv.skills.length > 20 && (
            <span className="text-xs text-default-400">{t("cvPanel.morePlus", { count: cv.skills.length - 20 })}</span>
          )}
        </div>
      </div>

      {/* Summary */}
      {cv.text_summary && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-400">{t("cvPanel.summary")}</p>
          <p className="text-xs leading-relaxed text-default-500 line-clamp-6">{cv.text_summary}</p>
        </div>
      )}
    </div>

    {/* PDF Dialog */}
    {pdfUrl && (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        onClick={handleClosePdf}
      >
        <div
          className="relative flex flex-col w-[90vw] h-[90vh] rounded-2xl bg-white overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-default-200">
            <span className="text-sm font-medium text-default-700">{t("cvPanel.pdfTitle", { id: cv.cv_id })}</span>
            <button
              type="button"
              onClick={handleClosePdf}
              className="rounded-lg p-1.5 text-default-400 hover:bg-default-100 transition-colors"
            >
              <X className="size-4" />
            </button>
          </div>
          <iframe
            src={pdfUrl}
            className="flex-1 w-full"
            title={t("cvPanel.pdfIframeTitle", { id: cv.cv_id })}
          />
        </div>
      </div>
    )}
    </>
  );
}
