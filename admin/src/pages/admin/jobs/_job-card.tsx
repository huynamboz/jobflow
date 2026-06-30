import { Briefcase, Check, ChevronRight, MapPin } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { JobListItem } from "@/types/job.types";
import {
  CompanyLogo, JOB_TYPE_LABEL_KEY,
  StatusBadge, WORK_MODES, WorkModeBadge,
  daysAgo, fmtSalary,
} from "./_primitives";

/* ── NODE-styled job card (grid view) ──────────────────────────────────
 * Mirrors preview/components-cards.html .card recipe with our radius bump.
 *   background: #ffffff
 *   border: 1px solid var(--line)
 *   border-radius: 24
 *   box-shadow: var(--shadow-card)
 *   padding: 16
 *   gap: 8
 */
export function JobCard({
  job, selected, onToggle, onOpen,
}: {
  job: JobListItem;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const { t } = useTranslation("jobs");
  const isWorkMode = WORK_MODES.has(job.job_type);
  const statusKind = job.is_active ? "active" : "inactive";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      style={{
        background: "#ffffff",
        border: selected ? "1px solid var(--blue)" : "1px solid var(--line)",
        borderRadius: 24,
        boxShadow: selected
          ? "0 0 0 3px rgba(53,130,255,0.12), var(--shadow-card)"
          : "var(--shadow-card)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        cursor: "pointer",
        transition: "border-color 0.14s, box-shadow 0.14s",
      }}
    >
      {/* Row 1: logo + company + checkbox */}
      <div className="flex items-center gap-2.5">
        <CompanyLogo
          name={job.company_name || job.platform_name || "?"}
          logo={job.company_logo}
          fallbackLogo={job.platform_logo}
        />
        <div className="min-w-0 flex-1">
          <div
            className="truncate"
            style={{ font: "700 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)" }}
          >
            {job.company_name || "—"}
          </div>
          {job.platform_name && (
            <div
              className="mt-0.5"
              style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}
            >
              {job.platform_name}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          className="shrink-0 cursor-pointer border-0 bg-transparent p-1"
          title={selected ? t("card.deselect") : t("card.select")}
        >
          <div
            className="grid size-5 place-items-center"
            style={{
              borderRadius: 6,
              border: selected ? "1.5px solid var(--blue)" : "1.5px solid var(--line-2)",
              background: selected ? "var(--blue)" : "#ffffff",
              color: "#ffffff",
              transition: "border-color 0.14s, background 0.14s",
            }}
          >
            {selected && <Check className="size-3" strokeWidth={3.2} />}
          </div>
        </button>
      </div>

      {/* Row 2: job title */}
      <div
        style={{
          font: "600 15.5px/1.3 var(--font-node-sans)",
          letterSpacing: "-0.01em",
          color: "var(--ink)",
        }}
      >
        {job.title}
      </div>

      {/* Row 3: meta (location + work mode + employment type) */}
      <div
        className="flex flex-wrap items-center gap-2.5"
        style={{ font: "400 11.5px/16px var(--font-node-sans)", color: "var(--muted)" }}
      >
        {job.location && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="size-3 shrink-0" />
            {job.location}
          </span>
        )}
        {isWorkMode && <WorkModeBadge mode={job.job_type} />}
        {job.job_type && (
          <span className="inline-flex items-center gap-1">
            <Briefcase className="size-3 shrink-0" />
            {JOB_TYPE_LABEL_KEY[job.job_type] ? t(JOB_TYPE_LABEL_KEY[job.job_type]) : job.job_type}
          </span>
        )}
      </div>

      {/* Row 4: footer (salary + status) */}
      <div
        className="flex items-center justify-between"
        style={{ paddingTop: 10, borderTop: "1px dashed var(--line)" }}
      >
        <div
          style={{
            font: "500 14px/1 var(--font-node-sans)",
            letterSpacing: "-0.02em",
            color: "var(--ink)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {fmtSalary(t, job.salary_min, job.salary_max, job.salary_currency, job.salary_period)}
        </div>
        <StatusBadge kind={statusKind} />
      </div>

      {/* Row 5: source (date + applicants) */}
      <div
        className="flex items-center gap-2"
        style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}
      >
        <span>{daysAgo(t, job.date_posted)}</span>
        {job.applicant_count != null && (
          <span className="ml-auto">{t("card.applicants", { count: job.applicant_count })}</span>
        )}
      </div>
    </div>
  );
}

/* ── Table row (list view) ──────────────────────────────────────────── */
export function JobRow({
  job, selected, onToggle, onOpen, isFirst,
}: {
  job: JobListItem;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
  isFirst?: boolean;
}) {
  const { t } = useTranslation("jobs");
  const isWorkMode = WORK_MODES.has(job.job_type);
  const statusKind = job.is_active ? "active" : "inactive";

  return (
    <tr
      onClick={onOpen}
      style={{
        cursor: "pointer",
        background: selected ? "rgba(53,130,255,0.05)" : "transparent",
        borderTop: isFirst ? "none" : "1px solid var(--line)",
        transition: "background 0.14s",
      }}
      onMouseEnter={(e) => {
        if (!selected) e.currentTarget.style.background = "var(--c2)";
      }}
      onMouseLeave={(e) => {
        if (!selected) e.currentTarget.style.background = "transparent";
      }}
    >
      <td className="px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="cursor-pointer rounded"
          style={{ accentColor: "var(--blue)" }}
        />
      </td>

      <td className="px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <CompanyLogo
            name={job.company_name || job.platform_name || "?"}
            logo={job.company_logo}
            fallbackLogo={job.platform_logo}
            size="sm"
          />
          <div className="min-w-0">
            <div
              className="truncate"
              style={{ font: "600 13.5px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)" }}
            >
              {job.title}
            </div>
            <div style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)" }}>
              {job.company_name || "—"}
            </div>
          </div>
        </div>
      </td>

      <td className="px-4 py-3.5">
        <div style={{ font: "400 12.5px/16px var(--font-node-sans)", color: "var(--ink-soft)" }}>
          {job.location || "—"}
        </div>
        {isWorkMode && (
          <div className="mt-0.5">
            <WorkModeBadge mode={job.job_type} />
          </div>
        )}
      </td>

      <td className="px-4 py-3.5" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--muted)" }}>
        {daysAgo(t, job.date_posted)}
      </td>

      <td className="px-4 py-3.5" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--ink)" }}>
        {fmtSalary(t, job.salary_min, job.salary_max, job.salary_currency, job.salary_period)}
      </td>

      <td className="px-4 py-3.5">
        <StatusBadge kind={statusKind} />
      </td>

      <td className="px-4 py-3.5 text-right">
        <ChevronRight className="ml-auto size-3.5" style={{ color: "var(--muted)" }} />
      </td>
    </tr>
  );
}
