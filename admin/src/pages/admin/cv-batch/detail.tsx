import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@heroui/button";
import { Modal, ModalContent, ModalHeader, ModalBody } from "@heroui/modal";
import {
  IconAlertCircle, IconChevronLeft, IconChevronRight,
  IconClock, IconCopy, IconFileText, IconLoader2, IconRefresh, IconSparkles, IconSquare,
} from "@tabler/icons-react";

import { cvAdminService } from "@/services/cv-admin.service";
import type { CVBatchDetail, CVBatchRecord, CVRecordDetail, CVRecordStatus } from "@/types/cv-admin.types";

const T = {
  accent:   "#167a7a", accent50: "#e8f4f4",
  success:  "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger:   "oklch(0.60 0.22 25)",  danger50: "oklch(0.96 0.03 25)",
  ink:      "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3:     "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface:  "#ffffff", surface2: "oklch(0.97 0.005 85)", surface3: "oklch(0.945 0.006 85)",
  line:     "rgba(226,232,240,0.7)",
};

const POLL_INTERVAL = 2500;
const PAGE_SIZE = 50;

const SENIORITY_LABEL: Record<number, string> = { 0: "Intern", 1: "Junior", 2: "Mid", 3: "Senior", 4: "Lead", 5: "Manager" };

const BADGE: Record<string, { bg: string; color: string }> = {
  pending:    { bg: T.surface3, color: T.ink3 },
  running:    { bg: "#c8e5e5", color: "#0e5353" },
  processing: { bg: "#c8e5e5", color: "#0e5353" },
  done:       { bg: T.success50, color: T.success },
  error:      { bg: T.danger50, color: T.danger },
  cancelled:  { bg: "oklch(0.94 0.03 60)", color: "oklch(0.52 0.12 60)" },
};

function StatusBadge({ status }: { status: string }) {
  const s = BADGE[status] ?? BADGE.pending;
  const pulse = status === "running" || status === "processing";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600, background: s.bg, color: s.color, whiteSpace: "nowrap" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", flexShrink: 0, animation: pulse ? "jb-pulse 1.4s ease-in-out infinite" : undefined }} />
      {status}
    </span>
  );
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

function eta(batch: CVBatchDetail["batch"]): string {
  if (batch.status !== "running" || batch.done_count === 0) return "";
  const remaining = batch.total - batch.done_count - batch.error_count;
  if (remaining <= 0) return "";
  const secs = remaining * 5;
  return secs < 60 ? `~${secs}s left` : `~${Math.round(secs / 60)}min left`;
}

const thStyle = (w?: number): React.CSSProperties => ({
  textAlign: "left", fontSize: 11, fontWeight: 600,
  color: T.ink3, textTransform: "uppercase", letterSpacing: "0.06em",
  padding: "12px 16px", borderBottom: `1px solid ${T.line}`,
  background: T.surface2, width: w,
});
const tdStyle: React.CSSProperties = { padding: "12px 16px", borderBottom: `1px solid ${T.line}`, verticalAlign: "middle" };

function PaneLabel({ icon, children, right }: { icon: React.ReactNode; children: React.ReactNode; right?: string }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: T.ink3, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
      {icon}{children}
      {right && <span style={{ marginLeft: "auto", fontWeight: 500, textTransform: "none", letterSpacing: 0, fontSize: 11, color: T.ink4 }}>{right}</span>}
    </div>
  );
}

function RecordModal({ batchId, record, onClose }: {
  batchId: number;
  record: CVBatchRecord | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<CVRecordDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!record) return;
    setDetail(null);
    setLoading(true);
    cvAdminService.getCVBatchRecord(batchId, record.id)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [batchId, record]);

  const result = detail?.result;

  return (
    <Modal isOpen={!!record} onClose={onClose} size="5xl" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader style={{ borderBottom: `1px solid ${T.line}`, padding: "16px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 700, fontSize: 17, letterSpacing: "-0.015em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {record?.file_name || `CV #${record?.cv_id}`}
                </span>
                {record && <StatusBadge status={record.status} />}
              </div>
              {record && <div style={{ fontSize: 12.5, color: T.ink3, marginTop: 2 }}>{record.source_category} · CV #{record.cv_id}</div>}
            </div>
            {result && (
              <button type="button" title="Copy extracted JSON"
                onClick={() => navigator.clipboard?.writeText(JSON.stringify(result, null, 2))}
                style={{ width: 34, height: 34, borderRadius: 12, background: T.surface2, border: "none", display: "grid", placeItems: "center", cursor: "pointer", color: T.ink2, flexShrink: 0 }}>
                <IconCopy size={15} />
              </button>
            )}
          </div>
        </ModalHeader>

        <ModalBody style={{ padding: 0 }}>
          {loading ? (
            <div style={{ display: "grid", placeItems: "center", height: 300, color: T.ink3 }}>
              <IconLoader2 size={20} style={{ animation: "jb-spin 0.7s linear infinite" }} />
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: 400 }}>
              {/* Left — raw text */}
              <div style={{ overflow: "auto", padding: "20px 24px", borderRight: `1px solid ${T.line}` }}>
                <PaneLabel icon={<IconFileText size={12} />}>Raw text</PaneLabel>
                {detail?.raw_text ? (
                  <pre style={{
                    background: T.surface2, border: `1px solid ${T.line}`, borderRadius: 12,
                    padding: "12px 14px", fontFamily: "'JetBrains Mono',ui-monospace,monospace",
                    fontSize: 12, color: T.ink, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    lineHeight: 1.6, margin: 0,
                  }}>
                    {detail.raw_text}
                  </pre>
                ) : (
                  <div style={{ color: T.ink4, fontSize: 13, padding: "24px 0" }}>No raw text stored.</div>
                )}
              </div>

              {/* Right — extracted */}
              <div style={{ overflow: "auto", padding: "20px 24px", background: `color-mix(in oklch,${T.surface2} 70%,white)` }}>
                <PaneLabel icon={<IconSparkles size={12} />}>Extracted by LLM</PaneLabel>

                {record?.status === "error" && record.error_msg && (
                  <div style={{ padding: 16, borderRadius: 12, background: T.danger50, border: `1px solid color-mix(in oklch,${T.danger} 20%,transparent)`, marginBottom: 14 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: T.danger, fontWeight: 700, fontSize: 13 }}>
                      <IconAlertCircle size={14} /> Extraction failed
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12.5, color: T.ink2 }}>{record.error_msg}</div>
                  </div>
                )}

                {record?.status === "pending" && (
                  <div style={{ padding: "32px 0", textAlign: "center", color: T.ink3 }}>
                    <IconClock size={24} style={{ display: "block", margin: "0 auto 12px" }} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Queued</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>Waiting for a worker…</div>
                  </div>
                )}

                {record?.status === "processing" && (
                  <div style={{ padding: "32px 0", textAlign: "center", color: T.accent }}>
                    <IconLoader2 size={22} style={{ display: "block", margin: "0 auto 12px", animation: "jb-spin 0.7s linear infinite" }} />
                    <div style={{ fontWeight: 700, fontSize: 14 }}>Extracting…</div>
                  </div>
                )}

                {result && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {/* Name */}
                    {result.name && (
                      <div style={{ fontWeight: 700, fontSize: 16, color: T.ink, letterSpacing: "-0.01em" }}>
                        {result.name}
                      </div>
                    )}

                    {/* Meta stats — 2×2 grid */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      {[
                        { label: "Role", value: result.role_category ?? "—" },
                        { label: "Seniority", value: result.seniority != null ? (SENIORITY_LABEL[result.seniority] ?? String(result.seniority)) : "—" },
                        { label: "Experience", value: result.experience_years != null ? `${result.experience_years} yrs` : "—" },
                        { label: "Education", value: result.education != null ? (["None","College","Bachelor","Master","PhD"][result.education] ?? String(result.education)) : "—" },
                      ].map(({ label, value }) => (
                        <div key={label} style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 10, padding: "8px 12px" }}>
                          <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: T.ink4 }}>{label}</div>
                          <div style={{ marginTop: 3, fontWeight: 600, fontSize: 13, color: T.ink }}>{value}</div>
                        </div>
                      ))}
                    </div>

                    {/* Skills */}
                    {result.skills && result.skills.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: T.ink3, marginBottom: 8 }}>
                          Skills · {result.skills.length}
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {result.skills.map((s, i) => (
                            <span key={i} style={{
                              padding: "3px 9px", borderRadius: 8, fontSize: 11.5, fontWeight: 500,
                              background: T.surface, border: `1px solid ${T.line}`, color: T.ink2,
                              display: "inline-flex", alignItems: "center", gap: 4,
                            }}>
                              {s.name}
                              <span style={{ fontSize: 10, color: T.ink4 }}>p{s.proficiency}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Work experience */}
                    {result.work_experience && result.work_experience.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: T.ink3, marginBottom: 8 }}>
                          Work Experience · {result.work_experience.length}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {result.work_experience.map((w, i) => (
                            <div key={i} style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 10, padding: "10px 14px" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: 13, color: T.ink }}>{w.title}</div>
                                  <div style={{ fontSize: 12, color: T.ink3, marginTop: 2 }}>{w.company}</div>
                                </div>
                                {w.duration && (
                                  <div style={{ fontSize: 11, color: T.ink4, whiteSpace: "nowrap", flexShrink: 0 }}>{w.duration}</div>
                                )}
                              </div>
                              {w.description && (
                                <div style={{ fontSize: 12, color: T.ink2, marginTop: 6, lineHeight: 1.5 }}>{w.description}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {!result && !record?.error_msg && record?.status === "done" && (
                  <div style={{ color: T.ink3, fontSize: 13, fontStyle: "italic" }}>No extraction result stored.</div>
                )}
              </div>
            </div>
          )}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}

export default function CVBatchDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const batchId = Number(id);

  const [detail, setDetail] = useState<CVBatchDetail | null>(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<CVRecordStatus | "">("");
  const [cancelling, setCancelling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<CVBatchRecord | null>(null);

  const load = useCallback(async (p: number, sf: string) => {
    try { setDetail(await cvAdminService.getCVBatch(batchId, p, PAGE_SIZE, sf)); }
    catch { /* retry on next poll */ }
  }, [batchId]);

  useEffect(() => { load(page, statusFilter); }, [load, page, statusFilter]);

  useEffect(() => {
    if (detail?.batch.status !== "running") return;
    pollRef.current = setInterval(async () => {
      const d = await cvAdminService.getCVBatch(batchId, page, PAGE_SIZE, statusFilter).catch(() => null);
      if (!d) return;
      setDetail(d);
      if (d.batch.status !== "running") clearInterval(pollRef.current!);
    }, POLL_INTERVAL);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [batchId, detail?.batch.status, page, statusFilter]);

  const handleCancel = async () => {
    setCancelling(true);
    try { await cvAdminService.cancelCVBatch(batchId); await load(page, statusFilter); }
    finally { setCancelling(false); }
  };

  if (!detail) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 160, color: T.ink3 }}>
        <IconLoader2 size={20} style={{ animation: "jb-spin 0.7s linear infinite" }} />
      </div>
    );
  }

  const { batch, records, total_records } = detail;
  const processed = batch.done_count + batch.error_count;
  const pct = batch.total > 0 ? (processed / batch.total) * 100 : 0;
  const running = batch.status === "running";
  const totalPages = Math.ceil(total_records / PAGE_SIZE);
  const etaStr = eta(batch);

  const filterOptions: { label: string; value: string }[] = [
    { label: `All · ${total_records}`, value: "" },
    { label: `Processing`, value: "processing" },
    { label: `Done · ${batch.done_count}`, value: "done" },
    { label: `Error · ${batch.error_count}`, value: "error" },
    { label: "Pending", value: "pending" },
  ];

  const handleRowClick = (rec: CVBatchRecord) => setSelectedRecord(rec);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <style>{`
        @keyframes jb-pulse  { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes jb-shimmer{ 0%{transform:translateX(-100%)} 100%{transform:translateX(100%)} }
        @keyframes jb-spin   { to{transform:rotate(360deg)} }
        .cv-row:hover td { background: ${T.surface2} !important; cursor: pointer; }
      `}</style>

      <RecordModal batchId={batchId} record={selectedRecord} onClose={() => setSelectedRecord(null)} />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <button type="button" onClick={() => navigate("/admin/cv-batch")} style={{
            background: "transparent", border: "none", color: T.ink3, fontSize: 12.5,
            cursor: "pointer", display: "flex", alignItems: "center", gap: 4, padding: 0, marginBottom: 10, fontWeight: 500,
          }}>
            <IconChevronLeft size={13} /> All batches
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h2 style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.025em", margin: 0 }}>CV Batch #{batch.id}</h2>
            <StatusBadge status={batch.status} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 8, color: T.ink3, fontSize: 13 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <IconClock size={13} />{fmtDate(batch.created_at)}
            </span>
            <span style={{ color: T.ink4 }}>
              {batch.filter_source_categories.length > 0 ? batch.filter_source_categories.join(" · ") : "All CVs"}
            </span>
            {etaStr && (
              <span style={{ display: "flex", alignItems: "center", gap: 5, color: T.accent }}>
                <IconLoader2 size={13} style={{ animation: "jb-spin 1.5s linear infinite" }} />{etaStr}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, paddingTop: 28 }}>
          {running && (
            <button type="button" onClick={handleCancel} disabled={cancelling} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 14px", borderRadius: 10, border: "none",
              background: T.danger50, color: T.danger, cursor: "pointer", fontSize: 13, fontWeight: 600,
            }}>
              {cancelling ? <IconLoader2 size={13} style={{ animation: "jb-spin 0.7s linear infinite" }} /> : <IconSquare size={13} />}
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
          <button type="button" onClick={() => load(page, statusFilter)} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "8px 14px", borderRadius: 10,
            border: `1px solid ${T.line}`, background: T.surface, cursor: "pointer", fontSize: 13, color: T.ink2,
          }}>
            <IconRefresh size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
        {[
          { label: "Progress", value: `${pct.toFixed(0)}%`, accent: running },
          { label: "Completed", value: batch.done_count, unit: `/ ${batch.total} CVs` },
          { label: "Errors", value: batch.error_count, unit: batch.error_count === 0 ? "clean" : "failed" },
          { label: "Categories", value: batch.filter_source_categories.length || "all" },
        ].map(({ label, value, unit, accent }) => (
          <div key={label} style={{
            background: accent ? T.accent : T.surface, border: `1px solid ${accent ? T.accent : T.line}`,
            borderRadius: 16, padding: "14px 16px", color: accent ? "#fff" : T.ink,
          }}>
            {label === "Progress" && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ height: 6, borderRadius: 999, background: accent ? "rgba(255,255,255,0.3)" : T.surface3, overflow: "hidden" }}>
                  <span style={{
                    display: "block", height: "100%", borderRadius: 999,
                    background: batch.status === "done" ? T.success : (accent ? "#fff" : T.accent),
                    width: `${pct}%`, transition: "width 0.4s", position: "relative", overflow: "hidden",
                  }}>
                    {running && <span style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg,transparent,rgba(255,255,255,0.45),transparent)", animation: "jb-shimmer 1.6s linear infinite" }} />}
                  </span>
                </div>
              </div>
            )}
            <div style={{ fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: accent ? "rgba(255,255,255,0.75)" : T.ink3 }}>{label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.02em", marginTop: 4, display: "flex", alignItems: "baseline", gap: 6 }}>
              {value}
              {unit && <span style={{ fontSize: 13, fontWeight: 500, color: accent ? "rgba(255,255,255,0.7)" : T.ink3 }}>{unit}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Records table */}
      <div style={{ background: T.surface, border: `1px solid ${T.line}`, borderRadius: 16, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.line}`, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 15 }}>Records · {total_records}</span>
          <div style={{ marginLeft: "auto", display: "inline-flex", padding: 3, background: T.surface2, borderRadius: 10, gap: 2 }}>
            {filterOptions.map((o) => (
              <button key={o.value} type="button" onClick={() => { setStatusFilter(o.value as CVRecordStatus | ""); setPage(1); }} style={{
                border: "none", padding: "5px 11px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
                background: statusFilter === o.value ? T.surface : "transparent",
                color: statusFilter === o.value ? T.ink : T.ink2,
              }}>
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ maxHeight: 560, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, fontSize: 13 }}>
            <thead>
              <tr>
                <th style={thStyle(48)}>CV ID</th>
                <th style={thStyle()}>File</th>
                <th style={thStyle(120)}>Source cat.</th>
                <th style={thStyle(110)}>Role</th>
                <th style={thStyle(90)}>Seniority</th>
                <th style={thStyle(70)}>Skills</th>
                <th style={thStyle(120)}>Status</th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec) => (
                <tr key={rec.id} className="cv-row" onClick={() => handleRowClick(rec)} style={{ background: rec.status === "processing" ? "oklch(0.96 0.02 240)" : undefined }}>
                  <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12, color: T.ink4 }}>#{rec.cv_id}</td>
                  <td style={{ ...tdStyle, fontWeight: 500, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {rec.file_name || <span style={{ color: T.ink4, fontStyle: "italic" }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: T.ink3, fontSize: 12 }}>{rec.source_category || "—"}</td>
                  <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12 }}>
                    {rec.role_category
                      ? <span style={{ padding: "2px 8px", borderRadius: 6, background: T.surface2, color: T.ink2 }}>{rec.role_category}</span>
                      : <span style={{ color: T.ink4 }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: T.ink2 }}>
                    {rec.seniority != null ? SENIORITY_LABEL[rec.seniority] ?? rec.seniority : <span style={{ color: T.ink4 }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: T.ink2, fontVariantNumeric: "tabular-nums" }}>
                    {rec.skill_count > 0 ? rec.skill_count : <span style={{ color: T.ink4 }}>—</span>}
                  </td>
                  <td style={tdStyle}>
                    <StatusBadge status={rec.status} />
                    {rec.error_msg && <div style={{ fontSize: 11, color: T.danger, marginTop: 3, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rec.error_msg}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: `1px solid ${T.line}` }}>
            <span style={{ fontSize: 12, color: T.ink3 }}>Page {page} of {totalPages}</span>
            <div style={{ display: "flex", gap: 4 }}>
              <Button isIconOnly size="sm" variant="flat" isDisabled={page === 1} onPress={() => setPage((p) => p - 1)}>
                <IconChevronLeft size={16} />
              </Button>
              <Button isIconOnly size="sm" variant="flat" isDisabled={page >= totalPages} onPress={() => setPage((p) => p + 1)}>
                <IconChevronRight size={16} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
