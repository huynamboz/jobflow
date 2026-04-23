import { Briefcase, Check, ChevronRight, MapPin } from "lucide-react";
import type { JobListItem } from "@/types/job.types";
import {
  CompanyLogo, JOB_TYPE_LABEL, PlatformChip, PlatformDot,
  StatusBadge, WORK_MODES, WorkModeBadge,
  daysAgo, fmtSalary,
} from "./_primitives";

// ── Grid card ─────────────────────────────────────────────────────
export function JobCard({
  job, selected, onToggle, onOpen,
}: {
  job: JobListItem;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const isWorkMode = WORK_MODES.has(job.job_type);
  const statusKind = job.is_active ? "active" : "inactive";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      className={`flex cursor-pointer flex-col gap-2.5 rounded-2xl border bg-white p-4 transition-all duration-150 hover:border-violet-200 ${
        selected
          ? "border-violet-600 ring-2 ring-violet-50"
          : "border-default-200"
      }`}
    >
      {/* ── Row 1: logo + company + checkbox ── */}
      <div className="flex items-center gap-2.5">
        <CompanyLogo name={job.company_name || "?"} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold text-default-900">
            {job.company_name || "—"}
          </div>
          {job.platform_name && (
            <div className="mt-0.5 text-[11px] text-default-400">{job.platform_name}</div>
          )}
        </div>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          className="shrink-0 cursor-pointer border-0 bg-transparent p-1"
          title={selected ? "Deselect" : "Select"}
        >
          <div
            className={`grid size-5 place-items-center rounded-[6px] border-[1.5px] text-white transition-colors ${
              selected ? "border-violet-600 bg-violet-600" : "border-default-300 bg-white"
            }`}
          >
            {selected && <Check className="size-3" strokeWidth={3.2} />}
          </div>
        </button>
      </div>

      {/* ── Row 2: title ── */}
      <div className="text-[15.5px] font-semibold leading-[1.3] tracking-[-0.01em] text-default-900">
        {job.title}
      </div>

      {/* ── Row 3: meta (location + work mode + employment type) ── */}
      <div className="flex flex-wrap items-center gap-2.5 text-[11.5px] text-default-500">
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
            {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
          </span>
        )}
      </div>

      {/* ── Row 4: footer (salary + status) ── */}
      <div className="flex items-center justify-between border-t border-dashed border-default-100 pt-2.5">
        <div className="text-[13px] font-bold tabular-nums text-default-900">
          {fmtSalary(job.salary_min, job.salary_max, job.salary_currency)}
        </div>
        <StatusBadge kind={statusKind} />
      </div>

      {/* ── Row 5: source (platform chip + date + applicants) ── */}
      <div className="flex items-center gap-2 text-[11px] text-default-400">
        {job.platform_name && <PlatformChip name={job.platform_name} />}
        <span>· {daysAgo(job.date_posted)}</span>
        {job.applicant_count != null && (
          <span className="ml-auto">{job.applicant_count} applicants</span>
        )}
      </div>
    </div>
  );
}

// ── Table row ─────────────────────────────────────────────────────
export function JobRow({
  job, selected, onToggle, onOpen,
}: {
  job: JobListItem;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const isWorkMode = WORK_MODES.has(job.job_type);
  const statusKind = job.is_active ? "active" : "inactive";

  return (
    <tr
      onClick={onOpen}
      className={`cursor-pointer transition-colors hover:bg-default-50 ${selected ? "bg-violet-50" : ""}`}
    >
      {/* Checkbox */}
      <td className="px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="cursor-pointer rounded accent-violet-600"
        />
      </td>

      {/* Job: logo + title + company */}
      <td className="px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <CompanyLogo name={job.company_name || "?"} size="sm" />
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-semibold text-default-900">
              {job.title}
            </div>
            <div className="text-[12px] text-default-500">{job.company_name || "—"}</div>
          </div>
        </div>
      </td>

      {/* Provider */}
      <td className="px-4 py-3.5">
        {job.platform_name ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-default-100 pl-[3px] pr-2 py-[3px] text-[11.5px] font-semibold text-default-700">
            <PlatformDot name={job.platform_name} size="sm" />
            {job.platform_name}
          </span>
        ) : (
          <span className="text-default-400">—</span>
        )}
      </td>

      {/* Location + work mode */}
      <td className="px-4 py-3.5">
        <div className="text-[12.5px] text-default-700">{job.location || "—"}</div>
        {isWorkMode && (
          <div className="mt-0.5">
            <WorkModeBadge mode={job.job_type} />
          </div>
        )}
      </td>

      {/* Posted */}
      <td className="px-4 py-3.5 font-mono text-[12px] text-default-500">
        {daysAgo(job.date_posted)}
      </td>

      {/* Salary */}
      <td className="px-4 py-3.5 font-mono text-[12px] text-default-800">
        {fmtSalary(job.salary_min, job.salary_max, job.salary_currency)}
      </td>

      {/* Status */}
      <td className="px-4 py-3.5">
        <StatusBadge kind={statusKind} />
      </td>

      {/* Arrow */}
      <td className="px-4 py-3.5 text-right">
        <ChevronRight className="ml-auto size-3.5 text-default-400" />
      </td>
    </tr>
  );
}
