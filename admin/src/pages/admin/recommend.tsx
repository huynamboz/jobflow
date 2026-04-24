import { useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Briefcase, ExternalLink, Loader2, MapPin, Search, Upload, X } from "lucide-react";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";

import { matchingService } from "@/services/matching.service";
import type { CVInfo, CVMatchData, JobMatchResult } from "@/types/matching.types";

const JOB_TYPE_LABEL: Record<string, string> = {
  "full-time": "Full-time", "part-time": "Part-time",
  remote: "Remote", hybrid: "Hybrid", "on-site": "On-site",
};

const SENIORITY_LABEL: Record<string, string> = {
  INTERN: "Intern", JUNIOR: "Junior", MID: "Mid", SENIOR: "Senior",
  LEAD: "Lead", MANAGER: "Manager",
};

const EDUCATION_LABEL: Record<string, string> = {
  NONE: "No degree", COLLEGE: "College", BACHELOR: "Bachelor",
  MASTER: "Master", PHD: "PhD",
};

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", SGD: "S$", VND: "₫", EUR: "€", GBP: "£", JPY: "¥", AUD: "A$",
};

function fmtSalary(min: number | null, max: number | null, currency = "USD"): string | null {
  if (!min && !max) return null;
  const sym = CURRENCY_SYMBOL[currency] ?? currency + " ";
  const fmt = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
    return String(n);
  };
  if (min && max) return `${sym}${fmt(min)}–${sym}${fmt(max)}`;
  if (min) return `≥ ${sym}${fmt(min)}`;
  return `≤ ${sym}${fmt(max!)}`;
}

function fmtExp(min: number | null, max: number | null): string | null {
  if (!min && !max) return null;
  if (min && max) return `${min}–${max} yrs`;
  if (min) return `${min}+ yrs`;
  return `≤${max} yrs`;
}

// ── CV Info Panel ───────────────────────────────────────────────────────────
function CVInfoPanel({ cv }: { cv: CVInfo }) {
  return (
    <div className="p-5 space-y-3 border rounded-2xl border-violet-100 bg-violet-50/60">
      <p className="text-[11px] font-bold uppercase tracking-[0.07em] text-violet-500">
        Extracted from your CV
      </p>

      <div className="flex flex-wrap gap-2 text-[12.5px]">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-violet-200 px-3 py-1 font-semibold text-violet-700">
          {SENIORITY_LABEL[cv.seniority] ?? cv.seniority}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-default-200 px-3 py-1 text-default-600">
          {cv.experience_years > 0 ? `${cv.experience_years} yrs exp` : "No exp detected"}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-default-200 px-3 py-1 text-default-600">
          {EDUCATION_LABEL[cv.education] ?? cv.education}
        </span>
      </div>

      {cv.skills.length > 0 ? (
        <div>
          <p className="mb-1.5 text-[10.5px] font-semibold text-violet-500">
            {cv.skills.length} skills detected
          </p>
          <div className="flex flex-wrap gap-1">
            {cv.skills.map((s) => (
              <span
                key={s}
                className="rounded-md border border-violet-200 bg-white px-2 py-0.5 text-[11px] font-medium text-violet-700"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-[12px] text-amber-600">
          No skills detected — try adding a skills section to your CV.
        </p>
      )}
    </div>
  );
}

// ── Match Level Badge ───────────────────────────────────────────────────────
const MATCH_LEVEL_CONFIG = {
  strong: { label: "Very suitable", cls: "border-emerald-300 bg-emerald-50 text-emerald-700" },
  good:   { label: "Suitable",      cls: "border-blue-200   bg-blue-50   text-blue-700"    },
  weak:   { label: "Weak match",    cls: "border-default-200 bg-default-50 text-default-500" },
};

function MatchLevelBadge({ level }: { level: string }) {
  const cfg = MATCH_LEVEL_CONFIG[level as keyof typeof MATCH_LEVEL_CONFIG];
  if (!cfg) return null;
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

// ── Dimension Scores ────────────────────────────────────────────────────────
const DIM_LABEL: Record<string, string> = {
  skill_fit: "Skills", experience_fit: "Experience",
  seniority_fit: "Seniority", domain_fit: "Domain",
};
const DIM_LEVEL_CFG = {
  good: { icon: "✓", cls: "text-emerald-600" },
  ok:   { icon: "~", cls: "text-amber-500"   },
  weak: { icon: "✗", cls: "text-red-500"     },
};

function DimScores({ dims }: { dims: JobMatchResult["dim_scores"] }) {
  const entries = Object.entries(dims).filter(([, v]) => !!v);
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.07em] text-default-400">
        Fit breakdown
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
        {entries.map(([dim, level]) => {
          const cfg = DIM_LEVEL_CFG[level as keyof typeof DIM_LEVEL_CFG];
          return (
            <div key={dim} className="flex items-center justify-between">
              <span className="text-[12px] text-default-500">{DIM_LABEL[dim] ?? dim}</span>
              <span className={`text-[12px] font-semibold ${cfg?.cls}`}>
                {cfg?.icon} {level}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DimScoresBadges({ dims }: { dims: JobMatchResult["dim_scores"] }) {
  const entries = Object.entries(dims ?? {}).filter(([, v]) => !!v);
  if (entries.length === 0) return null;
  const BG: Record<string, string> = {
    good: "border-emerald-200 bg-emerald-50 text-emerald-700",
    ok:   "border-amber-200  bg-amber-50  text-amber-600",
    weak: "border-red-200    bg-red-50    text-red-600",
  };
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([dim, level]) => {
        const cfg = DIM_LEVEL_CFG[level as keyof typeof DIM_LEVEL_CFG];
        return (
          <span key={dim} className={`rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${BG[level] ?? ""}`}>
            {cfg?.icon} {DIM_LABEL[dim] ?? dim}
          </span>
        );
      })}
    </div>
  );
}

// ── Score Bar ───────────────────────────────────────────────────────────────
function ScoreBar({ score, eligible }: { score: number; eligible: boolean }) {
  const pct = Math.round(score * 100);
  const color = eligible
    ? "bg-emerald-500"
    : score >= 0.5
    ? "bg-amber-400"
    : "bg-default-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-default-100">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`tabular-nums text-xs font-semibold ${eligible ? "text-emerald-600" : "text-default-500"}`}>
        {pct}%
      </span>
      {eligible && (
        <span className="rounded border border-emerald-200 bg-emerald-50 px-1 text-[10px] font-medium text-emerald-600">
          Match
        </span>
      )}
    </div>
  );
}

// ── Job Detail Drawer ───────────────────────────────────────────────────────
function JobDetailDrawer({ job, onClose }: { job: JobMatchResult | null; onClose: () => void }) {
  const salary = job ? fmtSalary(job.salary_min, job.salary_max, job.salary_currency) : null;
  const exp = job ? fmtExp(job.experience_min, job.experience_max) : null;
  const isWorkMode = job ? ["remote", "hybrid", "on-site"].includes(job.job_type) : false;

  return (
    <Drawer isOpen={!!job} onOpenChange={(open) => !open && onClose()} placement="right" size="lg">
      <DrawerContent>
        <DrawerHeader className="border-b border-default-100 px-6 py-4">
          {job && (
            <div className="min-w-0 flex-1">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-[17px] font-bold leading-snug text-default-900">
                    {job.title || `Job #${job.job_id}`}
                  </h2>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-default-500">
                    {job.company_name && <span className="font-semibold text-default-700">{job.company_name}</span>}
                    {job.location && (
                      <span className="inline-flex items-center gap-0.5">
                        <MapPin className="size-3" />{job.location}
                      </span>
                    )}
                  </div>
                </div>
                {job.source_url && (
                  <a href={job.source_url} target="_blank" rel="noreferrer"
                    className="shrink-0 rounded-lg border border-default-200 p-1.5 text-default-400 transition-colors hover:border-blue-300 hover:text-blue-600">
                    <ExternalLink className="size-3.5" />
                  </a>
                )}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <ScoreBar score={job.score} eligible={job.eligible} />
                <MatchLevelBadge level={job.match_level} />
              </div>
            </div>
          )}
        </DrawerHeader>

        <DrawerBody className="overflow-y-auto p-0">
          {job && (
            <div className="space-y-5 p-6">
              {/* Meta chips */}
              <div className="flex flex-wrap gap-2">
                {(isWorkMode ? job.job_type : null) && (
                  <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[12px] font-medium text-blue-700">
                    {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
                  </span>
                )}
                {!isWorkMode && job.job_type && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-default-200 bg-default-50 px-3 py-1 text-[12px] text-default-600">
                    <Briefcase className="size-3" />
                    {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
                  </span>
                )}
                {exp && (
                  <span className="rounded-full border border-default-200 bg-default-50 px-3 py-1 text-[12px] text-default-600">
                    {exp} experience
                  </span>
                )}
                {salary && (
                  <span className="rounded-full border border-default-200 bg-default-50 px-3 py-1 text-[12px] font-semibold tabular-nums text-default-700">
                    {salary}
                  </span>
                )}
                {!job.seniority_match && (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[12px] text-amber-600">
                    Seniority mismatch
                  </span>
                )}
              </div>

              {/* Dimension scores */}
              {Object.keys(job.dim_scores ?? {}).length > 0 && (
                <DimScores dims={job.dim_scores} />
              )}

              {/* Matched skills */}
              {job.matched_skills.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.07em] text-emerald-600">
                    Matched skills ({job.matched_skills.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.matched_skills.map((s) => (
                      <span key={s} className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[12px] font-medium text-emerald-700">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Missing skills */}
              {job.missing_skills.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.07em] text-red-500">
                    Missing skills ({job.missing_skills.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.missing_skills.map((s) => (
                      <span key={s} className="rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 text-[12px] font-medium text-red-600">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Source link */}
              {job.source_url && (
                <div>
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.07em] text-default-400">Source</p>
                  <a href={job.source_url} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-[13px] font-medium text-violet-600 hover:underline">
                    View original job posting <ExternalLink className="size-3.5" />
                  </a>
                </div>
              )}
            </div>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

// ── Job Card ────────────────────────────────────────────────────────────────
function JobCard({ job, onClick }: { job: JobMatchResult; onClick: () => void }) {
  const salary = fmtSalary(job.salary_min, job.salary_max, job.salary_currency);
  const exp = fmtExp(job.experience_min, job.experience_max);
  const isWorkMode = ["remote", "hybrid", "on-site"].includes(job.job_type);

  return (
    <div
      className="flex flex-col gap-3 p-5 transition-colors bg-white border rounded-2xl border-default-200 hover:border-violet-300 cursor-pointer"
      onClick={onClick}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold truncate text-default-900">
            {job.title || `Job #${job.job_id}`}
          </h3>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-default-500">
            {job.company_name && <span className="font-medium text-default-700">{job.company_name}</span>}
            {job.location && (
              <span className="inline-flex items-center gap-0.5">
                <MapPin className="size-3" />{job.location}
              </span>
            )}
          </div>
        </div>
        {job.source_url && (
          <a
            href={job.source_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 rounded-lg border border-default-200 p-1.5 text-default-400 transition-colors hover:border-blue-300 hover:text-blue-600"
          >
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>

      {/* Score + Match level */}
      <div className="flex items-center gap-2">
        <ScoreBar score={job.score} eligible={job.eligible} />
        <MatchLevelBadge level={job.match_level} />
      </div>

      {/* Meta chips */}
      <div className="flex flex-wrap gap-1.5">
        {isWorkMode && (
          <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700">
            {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
          </span>
        )}
        {!isWorkMode && job.job_type && (
          <span className="inline-flex items-center gap-1 rounded-full border border-default-200 bg-default-50 px-2 py-0.5 text-[11px] text-default-600">
            <Briefcase className="size-2.5" />
            {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
          </span>
        )}
        {exp && (
          <span className="rounded-full border border-default-200 bg-default-50 px-2 py-0.5 text-[11px] text-default-600">
            {exp}
          </span>
        )}
        {salary && (
          <span className="rounded-full border border-default-200 bg-default-50 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-default-700">
            {salary}
          </span>
        )}
        {!job.seniority_match && (
          <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-600">
            Seniority mismatch
          </span>
        )}
      </div>

      {/* Fit breakdown badges */}
      <DimScoresBadges dims={job.dim_scores} />

      {/* Skills */}
      {job.matched_skills.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-600">
            Matched ({job.matched_skills.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {job.matched_skills.map((s) => (
              <span key={s} className="rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
      {job.missing_skills.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-red-500">
            Missing ({job.missing_skills.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {job.missing_skills.map((s) => (
              <span key={s} className="rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 text-[11px] text-red-600">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────
export default function RecommendPage() {
  const location = useLocation();
  const prefilled = (location.state as { cvText?: string } | null)?.cvText ?? "";
  const [text, setText] = useState(prefilled);
  const [file, setFile] = useState<File | null>(null);
  const [topK, setTopK] = useState(10);
  const [result, setResult] = useState<CVMatchData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobMatchResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() && !file) return;
    setLoading(true);
    setError(null);
    try {
      const data = file
        ? await matchingService.matchFile(file, topK)
        : await matchingService.matchText(text, topK);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to get recommendations.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    if (f) setText("");
  };

  const clearFile = () => {
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const jobs = result?.jobs ?? [];
  const strongCount = jobs.filter((r) => r.eligible).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-default-900">Job Recommendations</h1>
        <p className="text-default-500">Paste CV text or upload a file to find matching jobs</p>
      </div>

      <form onSubmit={handleSubmit} className="p-5 space-y-4 bg-white border rounded-2xl border-default-200">
        {/* Drop zone */}
        <div
          className="flex flex-col items-center justify-center px-4 py-6 text-center transition-colors border-2 border-dashed cursor-pointer rounded-xl border-default-200 bg-default-50 hover:border-violet-300 hover:bg-violet-50/30"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files[0];
            if (f) { setFile(f); setText(""); }
          }}
        >
          <Upload className="mb-1 size-5 text-default-400" />
          <p className="text-sm text-default-600">
            {file ? (
              <span className="flex items-center gap-1.5">
                <span className="font-medium text-violet-600">{file.name}</span>
                <button type="button" onClick={(e) => { e.stopPropagation(); clearFile(); }}>
                  <X className="size-3.5 text-default-400 hover:text-red-500" />
                </button>
              </span>
            ) : "Drop PDF/DOCX/TXT or click to browse"}
          </p>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={handleFileChange} />
        </div>

        <div className="flex items-center gap-3 text-xs text-default-400">
          <div className="flex-1 h-px bg-default-200" />
          <span>or paste CV text</span>
          <div className="flex-1 h-px bg-default-200" />
        </div>

        <textarea
          rows={8}
          placeholder="Paste your CV / resume text here..."
          value={text}
          onChange={(e) => { setText(e.target.value); if (e.target.value) clearFile(); }}
          className="w-full px-4 py-3 text-sm transition-colors border resize-none rounded-xl border-default-200 bg-default-50 text-default-800 placeholder:text-default-400 focus:border-violet-300 focus:bg-white focus:outline-none"
          disabled={!!file}
        />

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-default-600">Top</label>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="h-8 px-2 text-sm bg-white border rounded-lg outline-none border-default-200 text-default-700 focus:border-violet-300"
            >
              {[5, 10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <span className="text-sm text-default-600">results</span>
          </div>

          <button
            type="submit"
            disabled={loading || (!text.trim() && !file)}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white transition-colors rounded-xl bg-violet-600 hover:bg-violet-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
            {loading ? "Matching… (may take ~30s on first run)" : "Find Jobs"}
          </button>
        </div>
      </form>

      {error && (
        <div className="px-4 py-3 text-sm text-red-700 border border-red-200 rounded-xl bg-red-50">{error}</div>
      )}

      {result && (
        <div className="space-y-5">
          {/* CV parse panel */}
          <CVInfoPanel cv={result.cv_info} />

          {/* Results header */}
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-default-700">
              {jobs.length} job{jobs.length !== 1 ? "s" : ""} found
              {strongCount > 0 && (
                <span className="ml-2 text-emerald-600">
                  · {strongCount} strong match{strongCount !== 1 ? "es" : ""}
                </span>
              )}
            </p>
          </div>

          {/* Job cards */}
          {jobs.length === 0 ? (
            <div className="py-16 text-center bg-white border rounded-2xl border-default-200 text-default-400">
              <Search className="mx-auto mb-2 size-8" />
              <p>No matching jobs found. Try a more detailed CV.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {jobs.map((job) => (
                <JobCard key={job.job_id} job={job} onClick={() => setSelectedJob(job)} />
              ))}
            </div>
          )}
        </div>
      )}

      <JobDetailDrawer job={selectedJob} onClose={() => setSelectedJob(null)} />
    </div>
  );
}
