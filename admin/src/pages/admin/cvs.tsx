import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody } from "@heroui/card";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";
import { ChevronLeft, ChevronRight, Download, FileText, Upload } from "lucide-react";

import { cvAdminService } from "@/services/cv-admin.service";
import type { AdminCVDetail, AdminCVItem, WorkExperienceItem } from "@/types/cv-admin.types";

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
const EDUCATION_LABEL: Record<number, string> = {
  0: "None", 1: "College", 2: "Bachelor", 3: "Master", 4: "PhD",
};
const SKILL_CATEGORY_LABEL: Record<number, string> = {
  0: "Technical", 1: "Soft", 2: "Tool", 3: "Domain",
};
const SKILL_CATEGORY_COLOR: Record<number, string> = {
  0: "bg-blue-50 text-blue-700 border-blue-200",
  1: "bg-green-50 text-green-700 border-green-200",
  2: "bg-orange-50 text-orange-700 border-orange-200",
  3: "bg-purple-50 text-purple-700 border-purple-200",
};
const SOURCE_LABEL: Record<string, string> = {
  upload: "Upload",
  linkedin_dataset: "LinkedIn",
  kaggle: "Kaggle",
};

const ROLE_COLOR: Record<string, string> = {
  backend:   "oklch(0.93 0.05 240)",
  frontend:  "oklch(0.93 0.06 180)",
  fullstack: "oklch(0.93 0.06 210)",
  mobile:    "oklch(0.93 0.05 270)",
  devops:    "oklch(0.93 0.05 60)",
  data_ml:   "oklch(0.93 0.06 300)",
  data_eng:  "oklch(0.92 0.05 320)",
  qa:        "oklch(0.93 0.04 140)",
  design:    "oklch(0.93 0.06 20)",
  ba:        "oklch(0.93 0.04 80)",
  other:     "oklch(0.94 0.005 265)",
};

function WorkExperienceSection({ items }: { items: WorkExperienceItem[] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-default-400">
        Work Experience ({items.length})
      </p>
      <div className="space-y-3">
        {items.map((w, i) => (
          <div key={i} className="rounded-xl border border-default-100 bg-default-50 px-4 py-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-default-800">{w.title}</p>
                <p className="text-xs text-default-500">{w.company}</p>
              </div>
              {w.duration && (
                <span className="shrink-0 text-xs text-default-400">{w.duration}</span>
              )}
            </div>
            {w.description && (
              <p className="mt-1.5 text-xs leading-relaxed text-default-600">{w.description}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailDrawer({ cvId, isOpen, onClose }: { cvId: number | null; isOpen: boolean; onClose: () => void }) {
  const [cv, setCv] = useState<AdminCVDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!cvId) return;
    setCv(null);
    setLoading(true);
    cvAdminService.getCV(cvId)
      .then(setCv)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [cvId]);

  return (
    <Drawer isOpen={isOpen} onOpenChange={(open) => !open && onClose()} placement="right" size="lg">
      <DrawerContent>
        <DrawerHeader className="border-b border-default-200">
          <div>
            <p className="text-sm font-semibold text-default-900">
              {loading ? "Loading…" : (cv?.candidate_name || `CV #${cv?.id ?? ""}` || "CV Detail")}
            </p>
            {cv && <p className="text-xs font-normal text-default-400">CV #{cv.id}</p>}
          </div>
        </DrawerHeader>
        <DrawerBody className="p-0 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
        ) : !cv ? (
          <div className="py-16 text-center text-default-400">CV not found.</div>
        ) : (
          <div className="space-y-5 p-5">
            <p className="truncate text-xs text-default-400" title={cv.file_name}>{cv.file_name}</p>

            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${SENIORITY_COLOR[cv.seniority] ?? "bg-gray-100"}`}>
                {SENIORITY_LABEL[cv.seniority] ?? cv.seniority}
              </span>
              {cv.role_category && (
                <span style={{ background: ROLE_COLOR[cv.role_category] ?? ROLE_COLOR.other }}
                  className="rounded-lg px-2.5 py-1 text-xs font-medium text-default-700">
                  {cv.role_category}
                </span>
              )}
              <span className="rounded-lg border border-default-200 bg-default-50 px-2.5 py-1 text-xs text-default-600">
                {SOURCE_LABEL[cv.source] ?? cv.source}
              </span>
              {cv.source_category && (
                <span className="rounded-lg border border-default-200 bg-default-50 px-2.5 py-1 text-xs text-default-500">
                  {cv.source_category}
                </span>
              )}
            </div>

            <div className="space-y-1.5 rounded-xl border border-default-100 bg-default-50 px-4 py-3 text-sm">
              {[
                ["Role", cv.role_category || "—"],
                ["Experience", `${cv.experience_years}y`],
                ["Education", EDUCATION_LABEL[cv.education] ?? cv.education],
                ["Skills", cv.skills?.length ?? 0],
                ["Created", new Date(cv.created_at).toLocaleDateString("vi-VN")],
              ].map(([k, v]) => (
                <div key={String(k)} className="flex justify-between">
                  <span className="text-default-500">{k}</span>
                  <span className="font-medium text-default-800">{String(v)}</span>
                </div>
              ))}
            </div>

            {cv.work_experience && cv.work_experience.length > 0 && (
              <WorkExperienceSection items={cv.work_experience} />
            )}

            {cv.skills && cv.skills.length > 0 && (
              <div>
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-default-400">
                  Skills ({cv.skills.length})
                </p>
                {([0, 1, 2, 3] as const).map((cat) => {
                  const catSkills = cv.skills!.filter((s) => s.category === cat);
                  if (catSkills.length === 0) return null;
                  return (
                    <div key={cat} className="mb-3">
                      <p className="mb-1.5 text-xs font-medium text-default-400">
                        {SKILL_CATEGORY_LABEL[cat]}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {catSkills
                          .sort((a, b) => b.proficiency - a.proficiency)
                          .map((s) => (
                          <span
                            key={s.skill_name}
                            title={`Proficiency: ${s.proficiency}/5`}
                            className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-xs font-medium ${SKILL_CATEGORY_COLOR[cat]}`}
                          >
                            {s.skill_name}
                            {s.proficiency >= 4 && (
                              <span className="opacity-60">★</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {cv.parsed_text && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-400">CV Text</p>
                <p className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border border-default-100 bg-default-50 px-4 py-3 text-xs leading-relaxed text-default-600">
                  {cv.parsed_text}
                </p>
              </div>
            )}
          </div>
        )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}


const PAGE_SIZE = 20;

export default function CVsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<AdminCVItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [seniority, setSeniority] = useState("");
  const [source, setSource] = useState("");
  const [roleCategory, setRoleCategory] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback((p: number, sen: string, src: string, role: string) => {
    setLoading(true);
    cvAdminService.listCVs({ seniority: sen, source: src, role_category: role, page: p, page_size: PAGE_SIZE })
      .then((res) => { setItems(res.data ?? []); setTotal(res.total ?? 0); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(page, seniority, source, roleCategory); }, [page, load]);

  const handleFilter = (sen: string, src: string, role: string) => {
    setSeniority(sen); setSource(src); setRoleCategory(role); setPage(1);
    load(1, sen, src, role);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-default-900">CVs</h1>
          <p className="text-default-500">{total.toLocaleString()} CVs in system</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              setExporting(true);
              try { await cvAdminService.exportCVs({ role_category: roleCategory, source }); }
              finally { setExporting(false); }
            }}
            disabled={exporting}
            className="flex items-center gap-2 rounded-xl border border-default-200 bg-white px-4 py-2 text-sm font-medium text-default-700 hover:bg-default-50 disabled:opacity-50"
          >
            <Download className="size-4" />
            {exporting ? "Exporting…" : "Export JSON"}
          </button>
          <button
            onClick={() => navigate("/admin/cvs/upload")}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Upload className="size-4" /> Upload CV
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <select value={roleCategory} onChange={(e) => handleFilter(seniority, source, e.target.value)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none focus:border-blue-400">
          <option value="">All Roles</option>
          {Object.keys(ROLE_COLOR).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={seniority} onChange={(e) => handleFilter(e.target.value, source, roleCategory)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none focus:border-blue-400">
          <option value="">All Seniority</option>
          {Object.entries(SENIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={source} onChange={(e) => handleFilter(seniority, e.target.value, roleCategory)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none focus:border-blue-400">
          <option value="">All Sources</option>
          {Object.entries(SOURCE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <Card className="shadow-sm">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-default-400">
              <FileText className="size-8" /><p>No CVs found.</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-default-100 bg-default-50 text-xs font-semibold uppercase tracking-wide text-default-500">
                    <tr>
                      <th className="px-4 py-3 text-left">ID</th>
                      <th className="px-4 py-3 text-left">File</th>
                      <th className="px-4 py-3 text-left">Role</th>
                      <th className="px-4 py-3 text-left">Seniority</th>
                      <th className="px-4 py-3 text-right">Exp</th>
                      <th className="px-4 py-3 text-left">Education</th>
                      <th className="px-4 py-3 text-right">Skills</th>
                      <th className="px-4 py-3 text-left">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-default-100">
                    {items.map((cv) => (
                      <tr key={cv.id} onClick={() => setSelectedId(cv.id)}
                        className="cursor-pointer transition-colors hover:bg-default-50">
                        <td className="px-4 py-3 font-mono text-xs text-default-400">#{cv.id}</td>
                        <td className="max-w-[180px] truncate px-4 py-3 text-xs font-medium text-default-700" title={cv.file_name}>
                          {cv.file_name || <span className="italic text-default-400">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          {cv.role_category && cv.role_category !== "other" ? (
                            <span style={{ background: ROLE_COLOR[cv.role_category] ?? ROLE_COLOR.other }}
                              className="rounded-md px-2 py-0.5 text-xs font-medium text-default-700">
                              {cv.role_category}
                            </span>
                          ) : (
                            <span className="text-xs text-default-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-lg px-2 py-0.5 text-xs font-medium ${SENIORITY_COLOR[cv.seniority] ?? "bg-gray-100"}`}>
                            {SENIORITY_LABEL[cv.seniority] ?? cv.seniority}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-xs text-default-600">{cv.experience_years}y</td>
                        <td className="px-4 py-3 text-xs text-default-500">{EDUCATION_LABEL[cv.education] ?? cv.education}</td>
                        <td className="px-4 py-3 text-right font-medium text-default-700">{cv.skill_count}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-md border border-default-200 bg-default-50 px-2 py-0.5 text-xs text-default-500">
                            {SOURCE_LABEL[cv.source] ?? cv.source}
                          </span>
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

      <DetailDrawer cvId={selectedId} isOpen={selectedId !== null} onClose={() => setSelectedId(null)} />
    </div>
  );
}
