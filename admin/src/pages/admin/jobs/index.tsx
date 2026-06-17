import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Briefcase, ChevronLeft, ChevronRight,
  Download, Grid3x3, List, Plus, RefreshCw, Search, Sparkles, Tag,
} from "lucide-react";

import { jobService } from "@/services/job.service";
import type { AdminPlatform, JobListItem } from "@/types/job.types";
import { PlatformDot, SENIORITY_LABEL } from "./_primitives";
import { JobCard, JobRow } from "./_job-card";
import { DetailDrawer } from "./_job-drawer";

type ViewMode = "grid" | "list";
const PAGE_SIZE = 20;

/* ── NODE-styled segmented control ─────────────────────────────────── */
function Seg({
  value, onChange, options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: React.ReactNode }[];
}) {
  return (
    <div
      className="inline-flex gap-0.5"
      style={{ background: "var(--c3)", borderRadius: 12, padding: 3 }}
    >
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={String(o.value)}
            type="button"
            onClick={() => onChange(o.value)}
            style={{
              borderRadius: 10,
              padding: "6px 12px",
              font: "600 12.5px/16px var(--font-node-sans)",
              color: active ? "var(--ink)" : "var(--muted)",
              background: active ? "#ffffff" : "transparent",
              boxShadow: active ? "var(--shadow-1)" : "none",
              border: "none",
              cursor: "pointer",
              transition: "background 0.12s, color 0.12s",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ── Ghost button (NODE recipe) ────────────────────────────────────── */
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
      className="inline-flex items-center gap-2"
      style={{
        background: "transparent",
        border: "none",
        borderRadius: 12,
        padding: "8px 12px",
        font: "600 13px/16px var(--font-node-sans)",
        color: "var(--ink-soft)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background 0.14s, color 0.14s",
      }}
      onMouseEnter={(e) => { if (!disabled) { e.currentTarget.style.background = "var(--c3)"; e.currentTarget.style.color = "var(--ink)"; } }}
      onMouseLeave={(e) => { if (!disabled) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink-soft)"; } }}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

/* ── Primary accent button ─────────────────────────────────────────── */
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
      className="inline-flex items-center gap-2"
      style={{
        background: "var(--blue)",
        color: "#ffffff",
        border: "1px solid var(--blue)",
        borderRadius: 12,
        padding: "8px 14px",
        font: "600 13px/16px var(--font-node-sans)",
        cursor: "pointer",
        boxShadow: "var(--shadow-btn)",
        transition: "background 0.14s",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "#126767"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "var(--blue)"; }}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

/* ── Platform filter pill ──────────────────────────────────────────── */
function ProviderPill({
  name, logo, count, active, onClick,
}: {
  name: string;
  logo?: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-[7px]"
      style={{
        borderRadius: 999,
        padding: "5px 10px 5px 6px",
        font: "600 12.5px/16px var(--font-node-sans)",
        border: active ? "1px solid rgba(53,130,255,0.30)" : "1px solid var(--line)",
        background: active ? "rgba(53,130,255,0.08)" : "#ffffff",
        color: active ? "var(--blue)" : "var(--ink-soft)",
        cursor: "pointer",
        transition: "background 0.14s, border-color 0.14s, color 0.14s",
      }}
    >
      <PlatformDot name={name} logo={logo} />
      <span>{name}</span>
      <span
        style={{
          borderRadius: 999,
          padding: "1px 7px",
          font: "700 11px/14px var(--font-node-mono)",
          fontVariantNumeric: "tabular-nums",
          background: active ? "rgba(53,130,255,0.15)" : "var(--c3)",
          color: active ? "var(--blue)" : "var(--muted)",
        }}
      >
        {count}
      </span>
    </button>
  );
}

/* ── Main page ─────────────────────────────────────────────────────── */
export default function JobsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<JobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [seniority, setSeniority] = useState("");
  const [jobType, setJobType] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set<number>());
  const [openId, setOpenId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [view, setView] = useState<ViewMode>("grid");
  const [platformFilter, setPlatformFilter] = useState("");
  const [platforms, setPlatforms] = useState<AdminPlatform[]>([]);

  // All platforms (server-side list, not derived from the current page).
  useEffect(() => {
    jobService.listPlatforms()
      .then((ps) => setPlatforms(ps.filter((p) => p.job_count > 0)))
      .catch(console.error);
  }, []);

  const activeCount = items.filter((j) => j.is_active).length;
  const inactiveCount = items.length - activeCount;

  const filtered = useMemo(() => {
    let result = items;
    if (activeFilter === "active") result = result.filter((j) => j.is_active);
    if (activeFilter === "inactive") result = result.filter((j) => !j.is_active);
    return result;
  }, [items, activeFilter]);

  const load = useCallback((p: number, s: string, sen: string, jt: string, plat: string) => {
    setLoading(true);
    jobService
      .listJobs({ search: s, seniority: sen, job_type: jt, platform: plat, page: p, page_size: PAGE_SIZE })
      .then((res) => { setItems(res.data ?? []); setTotal(res.total ?? 0); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(page, search, seniority, jobType, platformFilter); }, [page, load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    load(1, search, seniority, jobType, platformFilter);
  };

  const handleWorkMode = (v: string) => {
    setJobType(v); setPage(1); load(1, search, seniority, v, platformFilter);
  };

  const handlePlatform = (slug: string) => {
    const next = platformFilter === slug ? "" : slug;
    setPlatformFilter(next); setPage(1); load(1, search, seniority, jobType, next);
  };

  const toggleSel = (id: number) =>
    setSelectedIds((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelectedIds(new Set(filtered.map((j) => j.id)));
  const clearSel = () => setSelectedIds(new Set());

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="mb-6 flex items-end gap-4">
        <div className="flex-1">
          <h1
            style={{
              font: "700 32px/1 var(--font-node-sans)",
              letterSpacing: "-0.025em",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            All{" "}
            <em
              style={{
                fontFamily: "Georgia, serif",
                fontStyle: "italic",
                fontWeight: 400,
                color: "var(--blue)",
              }}
            >
              jobs
            </em>
          </h1>
          <div
            className="mt-1.5"
            style={{ font: "400 13px/18px var(--font-node-sans)", color: "var(--muted)" }}
          >
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
      </header>

      {/* ── Provider filter strip (all platforms, server-side filter) ── */}
      {platforms.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {platforms.map((p) => (
            <ProviderPill
              key={p.slug}
              name={p.name}
              logo={p.logo_url}
              count={p.job_count}
              active={platformFilter === p.slug}
              onClick={() => handlePlatform(p.slug)}
            />
          ))}
        </div>
      )}

      {/* ── Toolbar ──────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <form onSubmit={handleSearch} className="relative">
          <Search
            className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2"
            style={{ color: "var(--muted)" }}
          />
          <input
            type="text"
            placeholder="Search title, company, skill…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              height: 38,
              width: 360,
              borderRadius: 12,
              border: "1px solid var(--line)",
              background: "#ffffff",
              boxShadow: "var(--shadow-input)",
              paddingLeft: 34,
              paddingRight: 12,
              font: "400 13px/16px var(--font-node-sans)",
              color: "var(--ink)",
              outline: "none",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "var(--blue)"; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = "var(--line)"; }}
          />
        </form>

        <Seg
          value={activeFilter}
          onChange={setActiveFilter}
          options={[
            { value: "", label: `All · ${total}` },
            { value: "active", label: `Active · ${activeCount}` },
            { value: "inactive", label: `Inactive · ${inactiveCount}` },
          ]}
        />

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

        <select
          value={seniority}
          onChange={(e) => { setSeniority(e.target.value); setPage(1); load(1, search, e.target.value, jobType, platformFilter); }}
          style={{
            height: 38,
            borderRadius: 12,
            border: "1px solid var(--line)",
            background: "#ffffff",
            padding: "0 12px",
            font: "400 13px/16px var(--font-node-sans)",
            color: "var(--ink-soft)",
            outline: "none",
          }}
        >
          <option value="">All levels</option>
          {Object.entries(SENIORITY_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>

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
        <div
          className="mb-4 flex items-center gap-3"
          style={{
            borderRadius: 16,
            border: "1px solid rgba(53,130,255,0.20)",
            background: "rgba(53,130,255,0.06)",
            padding: "10px 14px",
            font: "600 13px/16px var(--font-node-sans)",
            color: "var(--blue)",
          }}
        >
          <span><strong>{selectedIds.size}</strong> selected</span>
          <button
            type="button"
            onClick={clearSel}
            style={{ background: "transparent", border: "none", color: "rgba(53,130,255,0.6)", cursor: "pointer", font: "500 12.5px/16px var(--font-node-sans)" }}
          >
            Clear
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              className="inline-flex items-center gap-1.5"
              style={{
                borderRadius: 10,
                border: "1px solid var(--line)",
                background: "#ffffff",
                padding: "5px 10px",
                font: "600 12px/16px var(--font-node-sans)",
                color: "var(--ink-soft)",
                cursor: "pointer",
                boxShadow: "var(--shadow-btn)",
              }}
            >
              <Tag className="size-3" /> Tag…
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5"
              style={{
                borderRadius: 10,
                border: "1px solid var(--line)",
                background: "#ffffff",
                padding: "5px 10px",
                font: "600 12px/16px var(--font-node-sans)",
                color: "var(--ink-soft)",
                cursor: "pointer",
                boxShadow: "var(--shadow-btn)",
              }}
            >
              <Download className="size-3" /> Export {selectedIds.size}
            </button>
            <button
              type="button"
              onClick={() => navigate("/admin/jd-batch/new")}
              className="inline-flex items-center gap-1.5"
              style={{
                borderRadius: 10,
                background: "var(--blue)",
                color: "#ffffff",
                border: "1px solid var(--blue)",
                padding: "5px 10px",
                font: "600 12px/16px var(--font-node-sans)",
                cursor: "pointer",
                boxShadow: "var(--shadow-btn)",
              }}
            >
              <Sparkles className="size-3" /> Extract {selectedIds.size} jobs
            </button>
          </div>
        </div>
      )}

      {/* ── Content ───────────────────────────────────────────── */}
      {loading ? (
        <div
          className="flex items-center justify-center"
          style={{ padding: "64px 0", color: "var(--muted)", font: "400 13px/18px var(--font-node-sans)" }}
        >
          Loading…
        </div>
      ) : filtered.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center gap-2"
          style={{
            background: "#ffffff",
            border: "1px solid var(--line)",
            borderRadius: 24,
            boxShadow: "var(--shadow-card)",
            padding: "64px 0",
            color: "var(--muted)",
          }}
        >
          <Briefcase className="size-8" strokeWidth={1.5} />
          <p style={{ font: "400 13px/18px var(--font-node-sans)", margin: 0 }}>
            No jobs match these filters.
          </p>
        </div>
      ) : view === "grid" ? (
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
        <div
          className="overflow-hidden"
          style={{
            background: "#ffffff",
            border: "1px solid var(--line)",
            borderRadius: 24,
            boxShadow: "var(--shadow-card)",
          }}
        >
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th
                    className="px-4 py-3"
                    style={{
                      width: 40,
                      background: "var(--c2)",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.size === filtered.length}
                      onChange={(e) => (e.target.checked ? selectAll() : clearSel())}
                      className="cursor-pointer rounded"
                      style={{ accentColor: "var(--blue)" }}
                    />
                  </th>
                  {["Job", "Location", "Posted", "Salary", "Status", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-4 py-3"
                      style={{
                        background: "var(--c2)",
                        borderBottom: "1px solid var(--line)",
                        font: "600 11px/16px var(--font-node-mono)",
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        color: "var(--muted)",
                        textAlign: (i === 4 || i === 5) ? "right" : "left",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((job, idx) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    selected={selectedIds.has(job.id)}
                    onToggle={() => toggleSel(job.id)}
                    onOpen={() => setOpenId(job.id)}
                    isFirst={idx === 0}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Pagination ────────────────────────────────────────── */}
      {!loading && totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <span style={{ font: "400 12.5px/16px var(--font-node-sans)", color: "var(--muted)" }}>
            Page {page} of {totalPages} · {total.toLocaleString()} total
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "#ffffff",
                padding: 6,
                color: "var(--ink-soft)",
                cursor: "pointer",
                opacity: page === 1 ? 0.4 : 1,
                boxShadow: "var(--shadow-btn)",
              }}
            >
              <ChevronLeft className="size-4" />
            </button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const p = totalPages <= 7 ? i + 1
                : page <= 4 ? i + 1
                : page >= totalPages - 3 ? totalPages - 6 + i
                : page - 3 + i;
              const isCurrent = p === page;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  style={{
                    minWidth: 32,
                    borderRadius: 8,
                    border: isCurrent ? "1px solid var(--blue)" : "1px solid var(--line)",
                    background: isCurrent ? "var(--blue)" : "#ffffff",
                    color: isCurrent ? "#ffffff" : "var(--ink-soft)",
                    padding: "5px 8px",
                    font: "600 12.5px/16px var(--font-node-sans)",
                    cursor: "pointer",
                    boxShadow: "var(--shadow-btn)",
                  }}
                >
                  {p}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "#ffffff",
                padding: 6,
                color: "var(--ink-soft)",
                cursor: "pointer",
                opacity: page === totalPages ? 0.4 : 1,
                boxShadow: "var(--shadow-btn)",
              }}
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}

      <DetailDrawer jobId={openId} isOpen={openId !== null} onClose={() => setOpenId(null)} />
    </div>
  );
}
