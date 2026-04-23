import { useCallback, useEffect, useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";
import { ChevronLeft, ChevronRight, ClipboardList } from "lucide-react";

import { llmService } from "@/services/llm.service";
import type { LLMCallLog } from "@/types/llm.types";

const PAGE_SIZE = 50;

const FEATURE_LABEL: Record<string, string> = {
  cv_extraction: "CV Extraction",
  jd_extraction: "JD Extraction",
  labeling: "Labeling",
  "": "Unknown",
};

function StatusBadge({ status }: { status: "success" | "error" }) {
  return status === "success"
    ? <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700">Success</span>
    : <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-600">Error</span>;
}

function LogDrawer({ log, isOpen, onClose }: { log: LLMCallLog | null; isOpen: boolean; onClose: () => void }) {
  return (
    <Drawer isOpen={isOpen} onOpenChange={(open) => !open && onClose()} placement="right" size="lg">
      <DrawerContent>
        <DrawerHeader className="border-b border-default-200">
          {log && (
            <div className="flex items-center gap-2">
              <span>Log #{log.id}</span>
              <StatusBadge status={log.status} />
            </div>
          )}
        </DrawerHeader>
        <DrawerBody className="p-0 overflow-y-auto">
        {log && <div className="space-y-5 p-5">
          <div className="space-y-1.5 rounded-xl border border-default-100 bg-default-50 px-4 py-3 text-sm">
            {[
              ["Feature", FEATURE_LABEL[log.feature] ?? (log.feature || "—")],
              ["Provider", log.provider_name ?? "—"],
              ["Duration", log.duration_ms != null ? `${log.duration_ms}ms` : "—"],
              ["Time", new Date(log.created_at).toLocaleString("vi-VN")],
            ].map(([k, v]) => (
              <div key={String(k)} className="flex justify-between gap-4">
                <span className="text-default-500">{k}</span>
                <span className="font-medium text-default-800">{String(v)}</span>
              </div>
            ))}
          </div>

          {log.input_preview && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-400">Input (preview)</p>
              <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-xl border border-default-100 bg-default-50 px-4 py-3 text-xs leading-relaxed text-default-600">
                {log.input_preview}
              </pre>
            </div>
          )}

          {log.output && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-default-400">Output</p>
              <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border border-default-100 bg-default-50 px-4 py-3 text-xs leading-relaxed text-default-600">
                {log.output}
              </pre>
            </div>
          )}

          {log.status === "error" && log.error_message && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-400">Error</p>
              <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-xs leading-relaxed text-red-700">
                {log.error_message}
              </pre>
            </div>
          )}
        </div>}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

export default function LLMLogsPage() {
  const [logs, setLogs] = useState<LLMCallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [featureFilter, setFeatureFilter] = useState("");
  const [selected, setSelected] = useState<LLMCallLog | null>(null);

  const load = useCallback((p: number, s: string, f: string) => {
    setLoading(true);
    llmService.listLogs({ status: s, feature: f, page: p, page_size: PAGE_SIZE })
      .then((res) => { setLogs(res.data ?? []); setTotal(res.total ?? 0); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(page, statusFilter, featureFilter); }, [page, load]);

  const handleFilter = (s: string, f: string) => {
    setStatusFilter(s); setFeatureFilter(f); setPage(1);
    load(1, s, f);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-default-900">LLM Call Logs</h1>
        <p className="text-default-500">{total.toLocaleString()} logs</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select value={statusFilter} onChange={(e) => handleFilter(e.target.value, featureFilter)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none">
          <option value="">All Status</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
        </select>
        <select value={featureFilter} onChange={(e) => handleFilter(statusFilter, e.target.value)}
          className="h-9 rounded-lg border border-default-200 bg-white px-3 text-sm text-default-700 outline-none">
          <option value="">All Features</option>
          <option value="cv_extraction">CV Extraction</option>
          <option value="jd_extraction">JD Extraction</option>
          <option value="labeling">Labeling</option>
        </select>
      </div>

      <Card className="shadow-sm">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-default-400">
              <ClipboardList className="size-8" /><p>No logs yet.</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-default-100 bg-default-50 text-xs font-semibold uppercase tracking-wide text-default-500">
                    <tr>
                      <th className="px-4 py-3 text-left">ID</th>
                      <th className="px-4 py-3 text-left">Feature</th>
                      <th className="px-4 py-3 text-left">Provider</th>
                      <th className="px-4 py-3 text-left">Status</th>
                      <th className="px-4 py-3 text-right">Duration</th>
                      <th className="px-4 py-3 text-left">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-default-100">
                    {logs.map((log) => (
                      <tr key={log.id} onClick={() => setSelected(log)}
                        className="cursor-pointer transition-colors hover:bg-default-50">
                        <td className="px-4 py-3 font-mono text-xs text-default-400">#{log.id}</td>
                        <td className="px-4 py-3 text-default-700">
                          {FEATURE_LABEL[log.feature] ?? (log.feature || "—")}
                        </td>
                        <td className="px-4 py-3 text-default-500">{log.provider_name ?? "—"}</td>
                        <td className="px-4 py-3"><StatusBadge status={log.status} /></td>
                        <td className="px-4 py-3 text-right text-default-500">
                          {log.duration_ms != null ? `${log.duration_ms}ms` : "—"}
                        </td>
                        <td className="px-4 py-3 text-xs text-default-400">
                          {new Date(log.created_at).toLocaleString("vi-VN")}
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

      <LogDrawer log={selected} isOpen={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}
