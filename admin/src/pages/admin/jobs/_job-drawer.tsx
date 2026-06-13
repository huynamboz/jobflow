import { useEffect, useState } from "react";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";
import { CheckCircle2, ExternalLink, MapPin, XCircle } from "lucide-react";

import { jobService } from "@/services/job.service";
import type { JobDetail } from "@/types/job.types";
import {
  JOB_TYPE_LABEL, PlatformChip, PlatformLogo, SENIORITY_LABEL,
  StatusBadge, WORK_MODES, WorkModeBadge, daysAgo, fmtSalary,
} from "./_primitives";

function KVStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-default-50 px-3 py-2.5">
      <div className="mb-1 text-[10.5px] font-bold uppercase tracking-[0.05em] text-default-400">
        {label}
      </div>
      <div className="text-[13.5px] font-bold tabular-nums text-default-900">{value}</div>
    </div>
  );
}

function PaneLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-default-400">
      {children}
    </div>
  );
}

export function DetailDrawer({
  jobId, isOpen, onClose,
}: {
  jobId: number | null;
  isOpen: boolean;
  onClose: () => void;
}) {
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

  const isWorkMode = job ? WORK_MODES.has(job.job_type) : false;
  const statusKind = job ? (job.is_active ? "active" : "inactive") : "inactive";

  return (
    <Drawer isOpen={isOpen} onOpenChange={(open) => !open && onClose()} placement="right" size="2xl">
      <DrawerContent>
        {/* Header */}
        <DrawerHeader className="border-b border-default-100 px-6 py-4">
          {loading ? (
            <span className="text-default-400">Loading…</span>
          ) : job ? (
            <div className="flex items-center gap-3">
              <PlatformLogo name={job.platform?.name || "?"} logo={job.platform?.logo_url} size="lg" />
              <div className="min-w-0 flex-1">
                <div className="text-[18px] font-bold leading-snug tracking-[-0.015em] text-default-900">
                  {job.title}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[12.5px] text-default-500">
                  {job.company && (
                    <span className="font-semibold text-default-700">{job.company.name}</span>
                  )}
                  {job.location && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="size-3" />
                      {job.location}
                    </span>
                  )}
                </div>
              </div>
              <div className="shrink-0">
                <StatusBadge kind={statusKind} />
              </div>
            </div>
          ) : (
            <span className="text-default-500">Job detail</span>
          )}
        </DrawerHeader>

        {/* Body */}
        <DrawerBody className="overflow-y-auto p-0">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-default-400">Loading…</div>
          ) : !job ? (
            <div className="py-20 text-center text-default-400">Job not found.</div>
          ) : (
            <div className="space-y-5 p-6">
              {/* Stat grid */}
              <div className="grid grid-cols-4 gap-2.5">
                <KVStat label="Salary" value={fmtSalary(job.salary_min, job.salary_max, job.salary_currency)} />
                <KVStat label="Type" value={JOB_TYPE_LABEL[job.job_type] ?? job.job_type} />
                <KVStat label="Level" value={SENIORITY_LABEL[job.seniority] ?? `L${job.seniority}`} />
                <KVStat label="Posted" value={daysAgo(job.date_posted)} />
              </div>

              {/* Skills */}
              {job.skills && job.skills.length > 0 && (
                <div>
                  <PaneLabel>Skills ({job.skills.length})</PaneLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {job.skills.map((s) => (
                      <span
                        key={s.skill_name}
                        className="rounded-full border border-default-200 bg-default-50 px-2.5 py-0.5 text-[11.5px] font-semibold text-default-700"
                      >
                        {s.skill_name}
                        {s.importance >= 4 && <span className="ml-1 text-amber-500">★</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Source */}
              {(job.platform || job.source_url) && (
                <div>
                  <PaneLabel>Source</PaneLabel>
                  <div className="flex items-center gap-3">
                    {job.platform && <PlatformChip name={job.platform.name} />}
                    {job.source_url && (
                      <a
                        href={job.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[12px] font-medium text-violet-600 hover:underline"
                      >
                        View original <ExternalLink className="size-3" />
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Description */}
              {job.description && (
                <div>
                  <PaneLabel>Description</PaneLabel>
                  <p className="whitespace-pre-wrap text-[13px] leading-[1.55] text-default-700">
                    {job.description}
                  </p>
                </div>
              )}

              {/* Responsibilities */}
              {job.responsibilities && (
                <div>
                  <PaneLabel>Responsibilities</PaneLabel>
                  <p className="whitespace-pre-wrap text-[13px] leading-[1.55] text-default-700">
                    {job.responsibilities}
                  </p>
                </div>
              )}

              {/* Requirements */}
              {job.requirements && (
                <div>
                  <PaneLabel>Requirements</PaneLabel>
                  <p className="whitespace-pre-wrap text-[13px] leading-[1.55] text-default-700">
                    {job.requirements}
                  </p>
                </div>
              )}

              {/* Status banner */}
              {job.is_active ? (
                <div className="flex items-start gap-2.5 rounded-xl border border-green-100 bg-green-50 px-3.5 py-3 text-[13px] text-green-700">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <span className="font-semibold">Active</span>
                    {" — this job is currently visible to candidates."}
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2.5 rounded-xl border border-default-200 bg-default-50 px-3.5 py-3 text-[13px] text-default-500">
                  <XCircle className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <span className="font-semibold">Inactive</span>
                    {" — this job is not visible to candidates."}
                  </div>
                </div>
              )}
            </div>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
