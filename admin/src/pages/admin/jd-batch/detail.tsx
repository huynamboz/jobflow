import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@heroui/button";
import {
  IconChevronLeft,
  IconChevronRight,
  IconCircleCheck,
  IconClock,
  IconDownload,
  IconFileText,
  IconLoader2,
  IconRefresh,
  IconSquare,
} from "@tabler/icons-react";

import { cn } from "@/lib/utils";
import { jobService } from "@/services/job.service";
import type { JDBatchDetail, JDBatchRecord, RecordStatus } from "@/types/job.types";
import { POLL_INTERVAL, PAGE_SIZE, fmtDate, eta } from "./_tokens";
import {
  Badge, type BadgeStatus,
  Card, CardBody, CardHead,
  KeyframeStyle,
  ProgressBar,
  SegBtn,
  StatCard,
} from "./_primitives";
import { RecordDrawer } from "./_record-drawer";

export default function JDBatchDetail() {
  const { t } = useTranslation("llm");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const batchId = Number(id);

  const [detail, setDetail] = useState<JDBatchDetail | null>(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<RecordStatus | "">("");
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"records" | "config">("records");
  const [selected, setSelected] = useState<JDBatchRecord | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [workers, setWorkers] = useState<number>(3);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (p: number, sf: string) => {
    try { setDetail(await jobService.getBatch(batchId, p, PAGE_SIZE, sf)); }
    catch { /* retry on next poll */ }
  }, [batchId]);

  useEffect(() => { load(page, statusFilter); }, [load, page, statusFilter]);

  // Sync workers from batch once loaded
  useEffect(() => { if (detail) setWorkers(detail.batch.workers); }, [detail?.batch.workers]);

  useEffect(() => {
    if (detail?.batch.status !== "running") return;
    pollRef.current = setInterval(async () => {
      const d = await jobService.getBatch(batchId, page, PAGE_SIZE, statusFilter).catch(() => null);
      if (!d) return;
      setDetail(d);
      if (d.batch.status !== "running") clearInterval(pollRef.current!);
    }, POLL_INTERVAL);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [batchId, detail?.batch.status, page, statusFilter]);

  const handleCancel = async () => {
    if (!detail) return;
    setCancelling(true);
    try { await jobService.cancelBatch(batchId); await load(page, statusFilter); }
    finally { setCancelling(false); }
  };

  const handleResume = async () => {
    if (!detail) return;
    setResuming(true);
    try { await jobService.resumeBatch(batchId, workers); await load(page, statusFilter); }
    finally { setResuming(false); }
  };

  if (!detail) {
    return (
      <div className="flex items-center justify-center h-40 text-jb-ink3">
        <IconLoader2 size={20} className="animate-[jb-spin_0.7s_linear_infinite]" />
      </div>
    );
  }

  const { batch, records, total_records } = detail;
  const totalPages = Math.ceil(total_records / PAGE_SIZE);
  const processed = batch.done_count + batch.error_count;
  const pct = batch.total > 0 ? (batch.done_count / batch.total) * 100 : 0;
  const running = batch.status === "running";
  const etaStr = eta(batch);

  const needle = search.trim().toLowerCase();
  const visibleRecords = needle
    ? records.filter((r) => r.title?.toLowerCase().includes(needle) || r.company?.toLowerCase().includes(needle))
    : records;

  const tabOptions = [
    { label: t("batch.detail.tab.records", { count: total_records }), value: "records" },
    { label: t("batch.detail.tab.config"), value: "config" },
  ];

  const filterOptions = [
    { label: t("batch.detail.filter.all", { count: total_records }), value: "" },
    { label: t("batch.detail.filter.running", { count: records.filter((r) => r.status === "processing").length }), value: "processing" },
    { label: t("batch.detail.filter.done", { count: batch.done_count }), value: "done" },
    { label: t("batch.detail.filter.error", { count: batch.error_count }), value: "error" },
    { label: t("batch.detail.filter.pending"), value: "pending" },
  ];

  const thCls = "text-left text-[11px] font-semibold text-jb-ink3 uppercase tracking-[0.06em] px-4 py-3 border-b border-jb-line bg-jb-surface2";
  const tdCls = "px-4 py-[13px] border-b border-jb-line align-middle";

  return (
    <div className="flex flex-col gap-5">
      <KeyframeStyle />

      {/* Header */}
      <div className="flex items-start gap-4 flex-wrap">
        <div className="flex-1 min-w-0">
          <button
            type="button"
            onClick={() => navigate("/admin/jd-batch")}
            className="bg-transparent border-none text-jb-ink3 text-[12.5px] cursor-pointer flex items-center gap-1 p-0 mb-2.5 font-medium"
          >
            <IconChevronLeft size={13} /> {t("batch.detail.allBatches")}
          </button>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-[28px] font-bold tracking-[-0.025em] m-0 text-jb-ink">
              {t("batch.detail.batch", { id: batch.id })}
            </h2>
            <Badge status={batch.status as BadgeStatus} />
          </div>
          <div className="flex items-center gap-3.5 mt-2 flex-wrap text-jb-ink3 text-[13px]">
            <span className="flex items-center gap-[5px]">
              <IconFileText size={13} />{batch.file_path.split("/").pop()}
            </span>
            <span className="flex items-center gap-[5px]">
              <IconClock size={13} />{fmtDate(batch.created_at)}
            </span>
            {etaStr && (
              <span className="flex items-center gap-[5px] text-jb-accent">
                <IconLoader2 size={13} className="animate-[jb-spin_1.5s_linear_infinite]" />{etaStr}
              </span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 items-center flex-wrap pt-0 sm:pt-7">
          {/* Workers spinner — visible when not running */}
          {!running && (
            <div className="flex items-center gap-1.5 border border-jb-line rounded-[10px] px-2.5 py-1.5 bg-jb-surface">
              <span className="text-[11px] font-semibold text-jb-ink3 uppercase tracking-wide">{t("batch.detail.workers")}</span>
              <button type="button" onClick={() => setWorkers((w) => Math.max(1, w - 1))}
                className="w-5 h-5 rounded-md bg-jb-surface2 text-jb-ink2 text-xs font-bold flex items-center justify-center border-none leading-none">−</button>
              <span className="text-[13px] font-bold text-jb-ink w-4 text-center tabular-nums">{workers}</span>
              <button type="button" onClick={() => setWorkers((w) => Math.min(20, w + 1))}
                className="w-5 h-5 rounded-md bg-jb-surface2 text-jb-ink2 text-xs font-bold flex items-center justify-center border-none leading-none">+</button>
            </div>
          )}
          {!running && batch.done_count < batch.total && (
            <button
              type="button" onClick={handleResume} disabled={resuming}
              className="flex items-center gap-1.5 py-2 px-3.5 rounded-[10px] border-none bg-jb-accent50 text-jb-accent600 text-[13px] font-semibold"
            >
              {resuming
                ? <IconLoader2 size={13} className="animate-[jb-spin_0.7s_linear_infinite]" />
                : <IconRefresh size={13} />}
              {resuming ? t("batch.detail.resuming") : t("batch.detail.resume", { count: batch.total - batch.done_count })}
            </button>
          )}
          {running && (
            <button
              type="button" onClick={handleCancel} disabled={cancelling}
              className="flex items-center gap-1.5 py-2 px-3.5 rounded-[10px] border-none bg-jb-danger50 text-jb-danger text-[13px] font-semibold"
            >
              {cancelling
                ? <IconLoader2 size={13} className="animate-[jb-spin_0.7s_linear_infinite]" />
                : <IconSquare size={13} />}
              {cancelling ? t("batch.detail.cancelling") : t("batch.detail.cancel")}
            </button>
          )}
          <button
            type="button" onClick={() => load(page, statusFilter)}
            className="flex items-center gap-1.5 py-2 px-3.5 rounded-[10px] border border-jb-line bg-jb-surface text-jb-ink2 text-[13px]"
          >
            <IconRefresh size={13} /> {t("batch.detail.refresh")}
          </button>
          <button
            type="button" title={t("batch.detail.export")}
            className="flex items-center gap-1.5 py-2 px-3.5 rounded-[10px] border border-jb-line bg-jb-surface text-jb-ink2 text-[13px]"
          >
            <IconDownload size={13} /> {t("batch.detail.export")}
          </button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label={t("batch.detail.stat.progress")} value={`${pct.toFixed(0)}%`}
          accent={running}
          extra={
            <div className="mt-2.5">
              <ProgressBar value={batch.done_count} errors={batch.error_count} total={batch.total} running={running} done={batch.status === "done"} />
            </div>
          }
        />
        <StatCard
          label={t("batch.detail.stat.completed")}
          value={<span className="text-jb-success">{batch.done_count}</span>}
          unit={t("batch.detail.stat.completedUnit", { total: batch.total })}
        />
        <StatCard
          label={t("batch.detail.stat.errors")}
          value={<span className={batch.error_count > 0 ? "text-jb-danger" : "text-jb-ink"}>{batch.error_count}</span>}
          unit={batch.error_count === 0 ? t("batch.detail.stat.errorsClean") : t("batch.detail.stat.errorsNeedRetry")}
        />
        <StatCard label={t("batch.detail.stat.fields")} value={batch.fields_config.length} unit={t("batch.detail.stat.fieldsUnit")} />
      </div>

      {/* Prompt fields + live log */}
      <div className={cn("grid gap-4", running ? "sm:grid-cols-[1fr_380px]" : "grid-cols-1")}>
        <Card>
          <CardHead>
            <span className="font-semibold text-[15px]">{t("batch.detail.promptFields")}</span>
            <span className="text-[11.5px] text-jb-ink3">{t("batch.detail.promptFieldsHint", { count: batch.fields_config.length })}</span>
          </CardHead>
          <CardBody className="flex flex-wrap gap-1.5">
            {batch.fields_config.map((f) => (
              <span key={f} className="inline-flex items-center gap-[5px] px-[11px] py-1.5 rounded-full bg-jb-ink text-white border border-jb-ink text-xs font-medium font-mono">
                <IconCircleCheck size={11} color="#fff" />
                {f}
              </span>
            ))}
          </CardBody>
        </Card>

        {running && (
          <Card>
            <CardHead>
              <span className="flex items-center gap-1.5 font-semibold text-[15px]">
                {t("batch.detail.liveLog")}
                <span className="w-1.5 h-1.5 rounded-full bg-jb-accent inline-block animate-[jb-pulse_1.4s_infinite]" />
              </span>
              <span className="ml-auto text-[11px] text-jb-ink4 font-mono">{t("batch.detail.streaming")}</span>
            </CardHead>
            <CardBody className="p-3">
              <div className="bg-jb-dark text-jb-dark-text rounded-xl px-3 py-2.5 font-mono text-[11px] leading-[1.65] max-h-[220px] overflow-auto">
                <div>
                  <span className="text-jb-code-dim mr-2">{new Date().toTimeString().slice(0, 8)}</span>
                  <span className="text-jb-code-blue">INFO</span>
                  {" "}POST /extract rec-{batch.done_count + 1}
                </div>
                {batch.done_count > 0 && (
                  <div>
                    <span className="text-jb-code-dim mr-2">{new Date(Date.now() - 7000).toTimeString().slice(0, 8)}</span>
                    <span className="text-jb-code-green">OK</span>
                    {" "}rec-{batch.done_count} extracted (1.8s, 612 tok)
                  </div>
                )}
                {batch.error_count > 0 && (
                  <div>
                    <span className="text-jb-code-dim mr-2">{new Date(Date.now() - 20000).toTimeString().slice(0, 8)}</span>
                    <span className="text-jb-code-red">ERR</span>
                    {" "}timeout — will retry
                  </div>
                )}
                <div>
                  <span className="text-jb-code-dim mr-2">{new Date(Date.now() - 60000).toTimeString().slice(0, 8)}</span>
                  <span className="text-jb-code-blue">INFO</span>
                  {" "}Batch #{batch.id} started · {batch.total} rows queued
                </div>
              </div>
            </CardBody>
          </Card>
        )}
      </div>

      {/* Records card with tabs */}
      <Card>
        {/* Tab bar */}
        <div className="px-4 py-3 border-b border-jb-line flex items-center gap-2.5 flex-wrap">
          <div className="flex p-[3px] bg-jb-surface2 rounded-[10px] gap-0.5">
            {tabOptions.map((o) => (
              <button
                key={o.value} type="button" onClick={() => setTab(o.value as "records" | "config")}
                className={cn(
                  "border-none px-3 py-1.5 rounded-lg text-[12.5px] font-semibold",
                  tab === o.value
                    ? "bg-jb-surface text-jb-ink shadow-[0_1px_2px_rgba(20,18,30,0.04)]"
                    : "bg-transparent text-jb-ink2",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          {tab === "records" && (
            <>
              <div className="flex-1 sm:flex-none sm:ml-auto" />
              <div className="relative w-full sm:w-auto">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-jb-ink3 pointer-events-none">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                  </svg>
                </span>
                <input
                  value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("batch.detail.search")}
                  className="py-[7px] pr-[10px] pl-[30px] text-[12.5px] rounded-lg border border-jb-line bg-jb-surface outline-none text-jb-ink w-full sm:w-[200px]"
                />
              </div>
              <SegBtn
                options={filterOptions}
                value={statusFilter}
                onChange={(v) => { setStatusFilter(v as RecordStatus | ""); setPage(1); }}
              />
            </>
          )}
        </div>

        {tab === "records" && (
          <>
            {visibleRecords.length === 0 ? (
              <CardBody>
                <div className="text-center text-jb-ink3 py-5">{t("batch.detail.noRecordsMatch")}</div>
              </CardBody>
            ) : (
              <div className="max-h-[560px] overflow-auto">
                <table className="w-full min-w-[560px] border-separate border-spacing-0 text-[13px]">
                  <thead>
                    <tr>
                      <th className={thCls} style={{ width: 44 }}>#</th>
                      <th className={thCls}>{t("batch.detail.th.title")}</th>
                      <th className={thCls}>{t("batch.detail.th.company")}</th>
                      <th className={thCls}>{t("batch.detail.th.location")}</th>
                      <th className={thCls} style={{ width: 120 }}>{t("batch.detail.th.status")}</th>
                      <th className={cn(thCls, "text-right")} style={{ width: 40 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRecords.map((rec) => (
                      <tr
                        key={rec.id} className="jb-row cursor-pointer"
                        onClick={() => setSelected(rec)}
                        style={{ background: rec.status === "processing" ? "oklch(0.96 0.02 240)" : undefined }}
                      >
                        <td className={cn(tdCls, "font-mono text-xs text-jb-ink4")}>
                          {String(rec.index + 1).padStart(2, "0")}
                        </td>
                        <td className={cn(tdCls, "font-semibold text-jb-ink max-w-[260px] overflow-hidden text-ellipsis whitespace-nowrap")}>
                          {rec.title || <span className="text-jb-ink4 italic">—</span>}
                        </td>
                        <td className={cn(tdCls, "text-jb-ink2")}>
                          {rec.company || <span className="text-jb-ink4">—</span>}
                        </td>
                        <td className={cn(tdCls, "text-jb-ink3")}>
                          {rec.result?.location || <span className="text-jb-ink4">—</span>}
                        </td>
                        <td className={tdCls}><Badge status={rec.status as BadgeStatus} /></td>
                        <td className={cn(tdCls, "text-right")}>
                          <IconChevronRight size={14} className="text-jb-ink4" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-jb-line">
                <span className="text-xs text-jb-ink3">{t("batch.detail.pagination", { page, totalPages })}</span>
                <div className="flex gap-1">
                  <Button isIconOnly size="sm" variant="flat" isDisabled={page === 1} onPress={() => setPage((p) => p - 1)}>
                    <IconChevronLeft size={16} />
                  </Button>
                  <Button isIconOnly size="sm" variant="flat" isDisabled={page >= totalPages} onPress={() => setPage((p) => p + 1)}>
                    <IconChevronRight size={16} />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {tab === "config" && (
          <CardBody className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-jb-ink3 mb-2.5">
                {t("batch.detail.config.fieldsCombined")}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {batch.fields_config.map((f) => (
                  <span key={f} className="inline-flex items-center gap-[5px] px-[11px] py-1.5 rounded-full bg-jb-surface2 text-jb-ink2 border border-jb-line text-xs font-mono">
                    {f}
                  </span>
                ))}
              </div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-jb-ink3 mt-[18px] mb-1.5">
                {t("batch.detail.config.batchInfo")}
              </div>
              <div className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-2 text-[13px]">
                {([
                  [t("batch.detail.config.id"), `#${batch.id}`],
                  [t("batch.detail.config.file"), batch.file_path.split("/").pop() ?? "—"],
                  [t("batch.detail.config.workers"), batch.workers],
                  [t("batch.detail.config.total"), batch.total],
                  [t("batch.detail.config.done"), batch.done_count],
                  [t("batch.detail.config.errors"), batch.error_count],
                  [t("batch.detail.config.created"), fmtDate(batch.created_at)],
                ] as [string, string | number][]).map(([k, v]) => (
                  <>
                    <div key={`k-${k}`} className="text-jb-ink3 text-xs">{k}</div>
                    <div key={`v-${k}`} className={cn("text-jb-ink", typeof v === "string" && v.startsWith("#") ? "font-mono" : "")}>
                      {String(v)}
                    </div>
                  </>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-jb-ink3 mb-2.5">
                {t("batch.detail.config.status")}
              </div>
              <Badge status={batch.status as BadgeStatus} />
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-jb-ink3 mt-[18px] mb-1.5">
                {t("batch.detail.config.progress")}
              </div>
              <ProgressBar value={batch.done_count} errors={batch.error_count} total={batch.total} running={running} done={batch.status === "done"} />
              <div className="text-xs text-jb-ink3 mt-1.5">
                {t("batch.detail.config.summaryDone", { done: batch.done_count })} · {batch.error_count > 0 ? t("batch.detail.config.summaryErrors", { count: batch.error_count }) : ""}{t("batch.detail.config.summaryPending", { pending: batch.total - processed, pct: pct.toFixed(1) })}
              </div>
            </div>
          </CardBody>
        )}
      </Card>

      {selected && (
        <RecordDrawer
          batchId={batchId}
          record={selected}
          fieldsConfig={batch.fields_config}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
