import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Briefcase, ChevronLeft, ChevronRight,
  Download, Grid3x3, List, Plus, RefreshCw, Search, Sparkles, Tag,
} from "lucide-react";

import { jobService } from "@/services/job.service";
import type { JobListItem } from "@/types/job.types";
import { PlatformDot, SENIORITY_LABEL } from "./_primitives";
import { JobCard, JobRow } from "./_job-card";
import { DetailDrawer } from "./_job-drawer";

type ViewMode = "grid" | "list";
const PAGE_SIZE = 20;

// ── Segmented control ──────────────────────────────────────────────
function Seg({
  value, onChange, options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: React.ReactNode }[];
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-xl bg-default-100 p-[3px]">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-[10px] px-3 py-1.5 text-[12.5px] font-semibold transition-colors ${
            value === o.value
              ? "bg-white text-default-900 shadow-sm"
              : "text-default-600 hover:text-default-900"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── Ghost / accent buttons ─────────────────────────────────────────
function GhostBtn({
  icon, children, onClick, disabled,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-transparent bg-transparent px-3.5 py-[9px] text-[13px] font-semibold text-default-700 transition-colors hover:bg-default-100 disabled:opacity-50"
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

function AccentBtn({
  icon, children, onClick,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-violet-600 bg-violet-600 px-3.5 py-[9px] text-[13px] font-semibold text-white transition-colors hover:bg-violet-700"
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

// ── Platform filter pill ───────────────────────────────────────────
function ProviderPill({
  name, count, active, onClick,
}: {
  name: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-[7px] rounded-full border py-1.5 pl-[6px] pr-2.5 text-[12.5px] font-semibold transition-colors ${
        active
          ? "border-violet-200 bg-violet-50 text-violet-700"
          : "border-default-200 bg-white text-default-700 hover:bg-white hover:text-default-900"
      }`}
    >
      <PlatformDot name={name} />
      <span>{name}</span>
      <span
        className={`rounded-full px-[7px] py-[1px] text-[11px] font-bold tabular-nums ${
          active ? "bg-violet-100 text-violet-700" : "bg-default-100 text-default-500"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

// ── Main page ──────────────────────────────────────────────────────
export default function JobsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<JobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [seniority, setSeniority] = useState("");
  const [jobType, setJobType] = useState("");
  const [activeFilter, setActiveFilter] = useState(""); // "" | "active" | "inactive"
  const [selectedIds, setSelectedIds] = useState(new Set<number>());
  const [openId, setOpenId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [view, setView] = useState<ViewMode>("grid");
  const [platformFilter, setPlatformFilter] = useState("");

  // Derived: unique platforms from current page items
  const platforms = useMemo(() => {
    const map = new Map<string, number>();
    items.forEach((j) => {
      if (j.platform_name) map.set(j.platform_name, (map.get(j.platform_name) ?? 0) + 1);
    });
    return [...map.entries()].map(([name, count]) => ({ name, count }));
  }, [items]);

  // Derived stats for seg control labels
  const activeCount = items.filter((j) => j.is_active).length;
  const inactiveCount = items.length - activeCount;

  // Client-side filters (platform + active status)
  const filtered = useMemo(() => {
    let result = items;
    if (platformFilter) result = result.filter((j) => j.platform_name === platformFilter);
    if (activeFilter === "active") result = result.filter((j) => j.is_active);
    if (activeFilter === "inactive") result = result.filter((j) => !j.is_active);
    return result;
  }, [items, platformFilter, activeFilter]);

  const load = useCallback((p: number, s: string, sen: string, jt: string) => {
    setLoading(true);
    jobService
      .listJobs({ search: s, seniority: sen, job_type: jt, page: p, page_size: PAGE_SIZE })
      .then((res) => { setItems(res.data ?? []); setTotal(res.total ?? 0); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(page, search, seniority, jobType); }, [page, load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    load(1, search, seniority, jobType);
  };

  const handleWorkMode = (v: string) => {
    setJobType(v); setPage(1); load(1, search, seniority, v);
  };

  const toggleSel = (id: number) =>
    setSelectedIds((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelectedIds(new Set(filtered.map((j) => j.id)));
  const clearSel = () => setSelectedIds(new Set());

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Page header ──────────────────────────────────────── */}
      <div className="mb-6 flex items-end gap-4">
        <div className="flex-1">
          <h1 className="m-0 text-[32px] font-bold leading-none tracking-[-0.025em] text-default-900">
            All{" "}
            <em className="font-serif font-normal not-italic italic text-violet-600">
              jobs
            </em>
          </h1>
          <div className="mt-1 text-[14px] text-default-500">
            {total.toLocaleString()} postings · {platforms.length} platform{platforms.length !== 1 ? "s" : ""} · {activeCount} active, {inactiveCount} inactive
          </div>
        </div>
        <div className="flex items-center gap-2">
          <GhostBtn icon={<RefreshCw className="size-[13px]" />}>Re-scrape</GhostBtn>
          <GhostBtn
            icon={<Download className="size-[14px]" />}
            onClick={async () => { setExporting(true); try { await jobService.exportJDs(); } finally { setExporting(false); } }}
            disabled={exporting}
          >
            {exporting ? "Exporting…" : "Export"}
          </GhostBtn>
          <AccentBtn
            icon={<Plus className="size-[14px]" strokeWidth={2.4} />}
            onClick={() => navigate("/admin/jd-batch/new")}
          >
            New batch from jobs
          </AccentBtn>
        </div>
      </div>

      {/* ── Provider filter strip ─────────────────────────────── */}
      {platforms.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {platforms.map((p) => (
            <ProviderPill
              key={p.name}
              name={p.name}
              count={p.count}
              active={platformFilter === p.name}
              onClick={() => setPlatformFilter((prev) => (prev === p.name ? "" : p.name))}
            />
          ))}
        </div>
      )}

      {/* ── Toolbar ──────────────────────────────────────────── */}
      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        {/* Search */}
        <form onSubmit={handleSearch} className="relative">
          <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-default-400" />
          <input
            type="text"
            placeholder="Search title, company, skill…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-[38px] w-[360px] rounded-xl border border-default-200 bg-white pl-[34px] pr-3 text-[13px] text-default-800 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-50"
          />
        </form>

        {/* Status segmented: All · N | Active · N | Inactive · N */}
        <Seg
          value={activeFilter}
          onChange={setActiveFilter}
          options={[
            { value: "", label: `All · ${total}` },
            { value: "active", label: `Active · ${activeCount}` },
            { value: "inactive", label: `Inactive · ${inactiveCount}` },
          ]}
        />

        {/* Work-mode segmented: Any | Remote | Hybrid | On-site */}
        <Seg
          value={jobType}
          onChange={handleWorkMode}
          options={[
            { value: "", label: "Any" },
            { value: "remote", label: "Remote" },
            { value: "hybrid", label: "Hybrid" },
            { value: "on-site", label: "On-site" },
          ]}
        />

        {/* Seniority select */}
        <select
          value={seniority}
          onChange={(e) => { setSeniority(e.target.value); setPage(1); load(1, search, e.target.value, jobType); }}
          className="h-[38px] rounded-xl border border-default-200 bg-white px-3 text-[13px] text-default-700 outline-none focus:border-violet-400"
        >
          <option value="">All levels</option>
          {Object.entries(SENIORITY_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>

        {/* View toggle */}
        <div className="ml-auto">
          <Seg
            value={view}
            onChange={(v) => setView(v as ViewMode)}
            options={[
              { value: "grid", label: <Grid3x3 className="size-3.5" /> },
              { value: "list", label: <List className="size-3.5" /> },
            ]}
          />
        </div>
      </div>

      {/* ── Selection bar ─────────────────────────────────────── */}
      {selectedIds.size > 0 && (
        <div className="mb-3.5 flex items-center gap-2.5 rounded-xl border border-violet-200 bg-violet-50 px-3.5 py-2.5 text-[13px] font-semibold text-violet-700">
          <span><strong>{selectedIds.size}</strong> selected</span>
          <button type="button" onClick={clearSel} className="font-semibold text-violet-400 hover:text-violet-700">
            Clear
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-lg border border-default-200 bg-white px-2.5 py-1.5 text-[12px] font-semibold text-default-700 hover:bg-default-50"
            >
              <Tag className="size-3" /> Tag…
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-lg border border-default-200 bg-white px-2.5 py-1.5 text-[12px] font-semibold text-default-700 hover:bg-default-50"
            >
              <Download className="size-3" /> Export {selectedIds.size}
            </button>
            <button
              type="button"
              onClick={() => navigate("/admin/jd-batch/new")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-2.5 py-1.5 text-[12px] font-semibold text-white hover:bg-violet-700"
            >
              <Sparkles className="size-3" /> Extract {selectedIds.size} jobs
            </button>
          </div>
        </div>
      )}

      {/* ── Content ───────────────────────────────────────────── */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-default-200 bg-white py-16 text-default-400 shadow-sm">
          <Briefcase className="size-8" />
          <p className="text-sm">No jobs match these filters.</p>
        </div>
      ) : view === "grid" ? (
        /* Grid view */
        <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-3.5">
          {filtered.map((j) => (
            <JobCard
              key={j.id}
              job={j}
              selected={selectedIds.has(j.id)}
              onToggle={() => toggleSel(j.id)}
              onOpen={() => setOpenId(j.id)}
            />
          ))}
        </div>
      ) : (
        /* Table / list view */
        <div className="overflow-hidden rounded-2xl border border-default-200 bg-white">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th className="w-10 border-b border-default-100 bg-default-50 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.size === filtered.length}
                      onChange={(e) => (e.target.checked ? selectAll() : clearSel())}
                      className="cursor-pointer rounded accent-violet-600"
                    />
                  </th>
                  {["Job", "Provider", "Location", "Posted", "Salary", "Status", ""].map((h, i) => (
                    <th
                      key={i}
                      className={`border-b border-default-100 bg-default-50 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-default-500 ${i === 5 || i === 6 ? "text-right" : "text-left"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    selected={selectedIds.has(job.id)}
                    onToggle={() => toggleSel(job.id)}
                    onOpen={() => setOpenId(job.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Pagination (shared across grid + list) ────────────── */}
      {!loading && totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-[12.5px] text-default-500">
            Page {page} of {totalPages} · {total.toLocaleString()} total
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-lg border border-default-200 bg-white p-1.5 text-default-500 transition-colors hover:bg-default-50 disabled:opacity-40"
            >
              <ChevronLeft className="size-4" />
            </button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const p = totalPages <= 7 ? i + 1
                : page <= 4 ? i + 1
                : page >= totalPages - 3 ? totalPages - 6 + i
                : page - 3 + i;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  className={`min-w-[32px] rounded-lg border px-2 py-1.5 text-[12.5px] font-semibold transition-colors ${
                    p === page
                      ? "border-violet-600 bg-violet-600 text-white"
                      : "border-default-200 bg-white text-default-600 hover:bg-default-50"
                  }`}
                >
                  {p}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-lg border border-default-200 bg-white p-1.5 text-default-500 transition-colors hover:bg-default-50 disabled:opacity-40"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}

      {/* ── Detail drawer ─────────────────────────────────────── */}
      <DetailDrawer jobId={openId} isOpen={openId !== null} onClose={() => setOpenId(null)} />
    </div>
  );
}
