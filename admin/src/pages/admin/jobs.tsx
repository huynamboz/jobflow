import { useCallback, useEffect, useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";
import { Briefcase, ChevronLeft, ChevronRight, Download } from "lucide-react";

import { jobService } from "@/services/job.service";
import type { JobDetail, JobListItem } from "@/types/job.types";

const SENIORITY_LABEL: Record<number, string> = {
  0: "Intern", 1: "Junior", 2: "Mid", 3: "Senior", 4: "Lead", 5: "Manager",
};
const SENIORITY_COLOR: Record<number, string> = {
  0: "bg-gray-100 text-gray-600",
  1: "bg-blue-100 text-blue-700",
  2: "bg-indigo-100 text-indigo-700",
  3: "bg-purple-100 text-purple-700",
  4: "bg-pink-100 text-pink-700",
  5: "bg-rose-100 text-rose-700",
};
const JOB_TYPE_LABEL: Record<string, string> = {
  "full-time": "Full-time", "part-time": "Part-time",
  remote: "Remote", hybrid: "Hybrid", "on-site": "On-site",
};

function fmtSalary(min: number | null, max: number | null) {
  if (!min && !max) return "—";
  const fmt = (n: number) => n >= 1_000_000 ? `${(n / 1_000_000).toFixed(0)}M` : `${(n / 1000).toFixed(0)}K`;
  if (min && max) return `${fmt(min)}–${fmt(max)}`;
  if (min) return `≥ ${fmt(min)}`;
  return `≤ ${fmt(max!)}`;
}

function DetailDrawer({ jobId, isOpen, onClose }: { jobId: number | null; isOpen: boolean; onClose: () => void }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    setJob(null);
    setLoading(true);
    jobService.getJob(jobId)
      .then(setJob)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [jobId]);

  return (
    <Drawer isOpen={isOpen} onOpenChange={(open) => !open && onClose()} placement="right" size="lg">
      <DrawerContent>
        <DrawerHeader className="border-b border-default-200">
          {loading ? "Loading…" : (job?.title ?? "Job Detail")}
        </DrawerHeader>
        <DrawerBody className="p-0 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
        ) : !job ? (
          <div className="py-16 text-center text-default-400">Job not found.</div>
        ) : (
          <div className="space-y-5 p-5">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${SENIORITY_COLOR[job.seniority] ?? "bg-gray-100"}`}>
                  {SENIORITY_LABEL[job.seniority] ?? job.seniority}
                </span>
                <span className="rounded-lg border border-default-200 bg-default-50 px-2.5 py-1 text-xs text-default-600">
                  {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
                </span>
                {!job.is_active && (
                  <span className="rounded-lg bg-red-100 px-2.5 py-1 text-xs font-medium text-red-600">Inactive</span>
                )}
              </div>
              <div className="space-y-0.5 text-sm text-default-500">
                {job.company && <p>🏢 {job.company.name}</p>}
                {job.platform && <p>📋 {job.platform.name}</p>}
                {job.location && <p>📍 {job.location}</p>}
                <p>💰 {fmtSalary(job.salary_min, job.salary_max)}</p>
              </div>
            </div>

            {job.skills && job.skills.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-400">Skills ({job.skills.length})</p>
                <div className="flex flex-wrap gap-1.5">
                  {job.skills.map((s) => (
                    <span key={s.skill_name} className="rounded-lg border border-default-200 bg-default-50 px-2 py-0.5 text-xs text-default-600">
                      {s.skill_name}{s.importance >= 4 && <span className="ml-1 text-orange-500">★</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {job.description && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-400">Description</p>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-default-600">{job.description}</p>
              </div>
            )}

            {job.source_url && (
              <a href={job.source_url} target="_blank" rel="noreferrer"
                className="block text-center text-xs text-blue-600 hover:underline">
                View original posting ↗
              </a>
            )}
          </div>
        )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

const PAGE_SIZE = 20;

export default function JobsPage() {
  const [items, setItems] = useState<JobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [seniority, setSeniority] = useState("");
  const [jobType, setJobType] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback((p: number, s: string, sen: string, jt: string) => {
    setLoading(true);
    jobService.listJobs({ search: s, seniority: sen, job_type: jt, page: p, page_size: PAGE_SIZE })
      .then((res) => { setItems(res.data ?? []); setTotal(res.total ?? 0); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(page, search, seniority, jobType); }, [page, load]);

  const handleFilter = (newSen: string, newJt: string) => {
    setSeniority(newSen); setJobType(newJt); setPage(1);
    load(1, search, newSen, newJt);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault(); setPage(1); load(1, search, seniority, jobType);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-default-900">Job Postings</h1>
          <p className="text-default-500">{total.toLocaleString()} jobs in system</p>
        </div>
        <button
          onClick={async () => {
            setExporting(true);
            try { await jobService.exportJDs(); }
            finally { setExporting(false); }
          }}
          disabled={exporting}
          className="flex items-center gap-2 rounded-xl border border-default-200 bg-white px-4 py-2 text-sm font-medium text-default-700 hover:bg-default-50 disabled:opacity-50"
        >
          <Download className="size-4" />
          {exporting ? "Exporting…" : "Export JDs JSON"}
        </button>
      </div>

      <form onSubmit={handleSearch} className="flex flex-wrap gap-3">
        <input
          type="text" placeholder="Search by title…" value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-800 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
        />
        <select value={seniority} onChange={(e) => handleFilter(e.target.value, jobType)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none">
          <option value="">All Seniority</option>
          {Object.entries(SENIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={jobType} onChange={(e) => handleFilter(seniority, e.target.value)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none">
          <option value="">All Types</option>
          {Object.entries(JOB_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button type="submit" className="h-9 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700">
          Search
        </button>
      </form>

      <Card className="shadow-sm">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-default-400">
              <Briefcase className="size-8" /><p>No jobs found.</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-default-100 bg-default-50 text-xs font-semibold uppercase tracking-wide text-default-500">
                    <tr>
                      <th className="px-4 py-3 text-left">Title</th>
                      <th className="px-4 py-3 text-left">Company</th>
                      <th className="px-4 py-3 text-left">Platform</th>
                      <th className="px-4 py-3 text-left">Seniority</th>
                      <th className="px-4 py-3 text-left">Type</th>
                      <th className="px-4 py-3 text-right">Salary</th>
                      <th className="px-4 py-3 text-left">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-default-100">
                    {items.map((job) => (
                      <tr key={job.id} onClick={() => setSelectedId(job.id)}
                        className="cursor-pointer transition-colors hover:bg-default-50">
                        <td className="max-w-[240px] px-4 py-3">
                          <div className="flex items-center gap-2">
                            {!job.is_active && <span className="shrink-0 rounded bg-red-100 px-1 py-0.5 text-[10px] text-red-500">OFF</span>}
                            <span className="truncate font-medium text-default-800">{job.title}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-default-600">{job.company_name ?? "—"}</td>
                        <td className="px-4 py-3 text-default-500">{job.platform_name ?? "—"}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-lg px-2 py-0.5 text-xs font-medium ${SENIORITY_COLOR[job.seniority] ?? "bg-gray-100"}`}>
                            {SENIORITY_LABEL[job.seniority] ?? job.seniority}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-default-500">{JOB_TYPE_LABEL[job.job_type] ?? job.job_type}</td>
                        <td className="px-4 py-3 text-right text-xs text-default-500">{fmtSalary(job.salary_min, job.salary_max)}</td>
                        <td className="px-4 py-3 text-xs text-default-400">
                          {new Date(job.created_at).toLocaleDateString("vi-VN")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t border-default-100 px-4 py-3">
                  <span className="text-xs text-default-500">Page {page} of {totalPages} · {total.toLocaleString()} total</span>
                  <div className="flex gap-1">
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
                      className="rounded-lg border border-default-200 p-1.5 text-default-500 hover:bg-default-50 disabled:opacity-40">
                      <ChevronLeft className="size-4" />
                    </button>
                    <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                      className="rounded-lg border border-default-200 p-1.5 text-default-500 hover:bg-default-50 disabled:opacity-40">
                      <ChevronRight className="size-4" />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardBody>
      </Card>

      <DetailDrawer jobId={selectedId} isOpen={selectedId !== null} onClose={() => setSelectedId(null)} />
    </div>
  );
}
