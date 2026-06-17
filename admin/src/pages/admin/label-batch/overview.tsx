import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@heroui/button";
import {
  IconLoader2, IconPlayerPlay, IconPlayerStop,
  IconTag, IconCheck, IconAlertCircle, IconChevronRight,
} from "@tabler/icons-react";

import { cn } from "@/lib/utils";
import { labelingService } from "@/services/labeling.service";
import type { LabelingBatch, LabelingBatchListResponse } from "@/types/labeling-batch.types";
import { Badge, type BadgeStatus, KeyframeStyle, ProgressBar, StatCard } from "../jd-batch/_primitives";

const POLL_MS = 3000;

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

function BatchCard({ batch, onCancel }: { batch: LabelingBatch; onCancel: (id: number) => void }) {
  const { t } = useTranslation("labeling");
  const navigate = useNavigate();
  const running = batch.status === "running";
  return (
    <div
      className="bg-jb-surface border border-jb-line rounded-[20px] p-[18px] cursor-pointer hover:border-jb-accent/40 transition-colors"
      onClick={() => navigate(`/admin/label-batch/${batch.id}`)}
    >
      <div className="flex justify-between items-center mb-2.5">
        <Badge status={batch.status as BadgeStatus} />
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] text-jb-ink4">{fmtDate(batch.created_at)}</span>
          <IconChevronRight size={13} className="text-jb-ink4" />
        </div>
      </div>

      <div className="font-bold text-[15px] tracking-[-0.01em]">{t("batch.card.batchNumber", { id: batch.id })}</div>
      <div className="font-mono text-[12px] text-jb-ink3 mt-0.5">{t("batch.card.workers", { count: batch.workers })}</div>

      <div className="mt-3.5">
        <ProgressBar
          value={batch.done_count} errors={batch.error_count} total={batch.total}
          running={running} done={batch.status === "done"}
        />
        <div className="flex justify-between text-xs mt-2">
          <span className="text-jb-ink3">{t("batch.card.labeledOf", { done: batch.done_count, total: batch.total })}</span>
          <span className="font-semibold">{batch.pct.toFixed(0)}%</span>
        </div>
      </div>

      <div className="h-px bg-jb-line my-3.5" />

      <div className="grid grid-cols-3 gap-2 text-[11.5px]">
        <div>
          <div className="uppercase tracking-[0.05em] font-semibold text-[10px] text-jb-ink4">{t("batch.card.done")}</div>
          <div className="mt-0.5 text-jb-success font-semibold">{batch.done_count}</div>
        </div>
        <div>
          <div className="uppercase tracking-[0.05em] font-semibold text-[10px] text-jb-ink4">{t("batch.card.errors")}</div>
          <div className={cn("mt-0.5 font-semibold", batch.error_count > 0 ? "text-jb-danger" : "text-jb-ink2")}>
            {batch.error_count}
          </div>
        </div>
        <div>
          <div className="uppercase tracking-[0.05em] font-semibold text-[10px] text-jb-ink4">{t("batch.card.pending")}</div>
          <div className="mt-0.5 text-jb-ink2">{Math.max(0, batch.total - batch.done_count - batch.error_count)}</div>
        </div>
      </div>

      {running && (
        <div onClick={(e) => e.stopPropagation()}>
          <Button
            size="sm" color="danger" variant="flat" className="mt-3.5 w-full"
            startContent={<IconPlayerStop size={13} />}
            onPress={() => onCancel(batch.id)}
          >
            {t("batch.card.stop")}
          </Button>
        </div>
      )}
    </div>
  );
}

function OverallBar({ total, n0, n1, n2 }: { total: number; n0: number; n1: number; n2: number }) {
  const { t } = useTranslation("labeling");
  if (total === 0) return <div className="text-jb-ink4 text-xs">{t("batch.noLabelsYet")}</div>;
  const pct = (n: number) => total > 0 ? ((n / total) * 100).toFixed(0) : "0";
  return (
    <div className="space-y-1.5 text-[12px]">
      {[
        { label: t("batch.dist.notSuitable"), n: n0, cls: "bg-jb-danger" },
        { label: t("batch.dist.suitable"),    n: n1, cls: "bg-jb-accent" },
        { label: t("batch.dist.strongFit"),   n: n2, cls: "bg-jb-success" },
      ].map(({ label, n, cls }) => (
        <div key={label} className="flex items-center gap-2">
          <span className="text-jb-ink3 w-[110px] shrink-0">{label}</span>
          <div className="flex-1 h-2 bg-jb-surface3 rounded-full overflow-hidden">
            <div className={cn("h-full rounded-full transition-[width]", cls)} style={{ width: `${pct(n)}%` }} />
          </div>
          <span className="text-jb-ink2 font-semibold w-8 text-right tabular-nums">{pct(n)}%</span>
          <span className="text-jb-ink4 w-8 tabular-nums">{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function LabelBatchOverview() {
  const { t } = useTranslation("labeling");
  const [data, setData] = useState<LabelingBatchListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [workers, setWorkers] = useState(3);
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await labelingService.listBatches()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const hasRunning = data?.batches.some((b) => b.status === "running");
    if (!hasRunning) return;
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [data, load]);

  const handleStart = async () => {
    setErr(null);
    setStarting(true);
    try {
      await labelingService.startBatch(workers);
      await load();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? t("batch.startFailed");
      setErr(msg);
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async (id: number) => {
    try { await labelingService.cancelBatch(id); await load(); } catch { /* ignore */ }
  };

  const q = data?.queue;
  const lbl = data?.labels;
  const batches = data?.batches ?? [];
  const hasRunning = batches.some((b) => b.status === "running");

  return (
    <div className="flex flex-col gap-5">
      <KeyframeStyle />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div>
          <h1 className="text-[26px] sm:text-[32px] font-bold tracking-[-0.025em] m-0 text-jb-ink">
            {t("batch.titleEmphasis")} <span className="italic text-jb-accent font-normal">{t("batch.title")}</span>
          </h1>
          <p className="mt-1 text-jb-ink3 text-sm m-0">
            {t("batch.subtitle")}
          </p>
        </div>

        <div className="sm:ml-auto flex items-center gap-2 flex-wrap">
          {/* Workers spinner */}
          {!hasRunning && (
            <div className="flex items-center gap-1.5 border border-jb-line rounded-[10px] px-2.5 py-1.5 bg-jb-surface">
              <span className="text-[11px] font-semibold text-jb-ink3 uppercase tracking-wide">{t("batch.workers")}</span>
              <button
                type="button" onClick={() => setWorkers((w) => Math.max(1, w - 1))}
                className="w-5 h-5 rounded flex items-center justify-center text-jb-ink2 hover:bg-jb-surface2 text-sm font-bold"
              >−</button>
              <span className="text-[13px] font-bold text-jb-ink w-4 text-center tabular-nums">{workers}</span>
              <button
                type="button" onClick={() => setWorkers((w) => Math.min(20, w + 1))}
                className="w-5 h-5 rounded flex items-center justify-center text-jb-ink2 hover:bg-jb-surface2 text-sm font-bold"
              >+</button>
            </div>
          )}
          <Button
            color="primary" isLoading={starting} isDisabled={hasRunning || starting}
            startContent={!starting && <IconPlayerPlay size={14} />}
            onPress={handleStart}
          >
            {hasRunning ? t("batch.running") : t("batch.startBatch")}
          </Button>
        </div>
      </div>

      {err && (
        <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-jb-danger50 text-jb-danger text-sm">
          <IconAlertCircle size={16} className="shrink-0" />
          {err}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label={t("batch.stat.pending")}    value={q?.pending ?? "—"}  unit={t("batch.stat.unitPairs")}   accent={!!q?.pending} />
        <StatCard label={t("batch.stat.labeled")}    value={q?.labeled ?? "—"}  unit={t("batch.stat.unitPairs")} />
        <StatCard label={t("batch.stat.totalPairs")} value={q?.total ?? "—"}   unit={t("batch.stat.unitInQueue")} />
        <StatCard label={t("batch.stat.labels")}     value={lbl?.total ?? "—"}  unit={t("batch.stat.unitCreated")} />
      </div>

      {/* Label distribution */}
      {lbl && lbl.total > 0 && (
        <div className="bg-jb-surface border border-jb-line rounded-[20px] p-5">
          <div className="font-semibold text-[13px] text-jb-ink mb-3 flex items-center gap-2">
            <IconTag size={14} className="text-jb-accent" />
            {t("batch.labelDistribution")}
          </div>
          <OverallBar total={lbl.total} n0={lbl.overall_0} n1={lbl.overall_1} n2={lbl.overall_2} />
        </div>
      )}

      {/* Batch list */}
      {loading ? (
        <div className="grid place-items-center h-40 text-jb-ink3">
          <IconLoader2 size={20} className="animate-[jb-spin_0.7s_linear_infinite]" />
        </div>
      ) : batches.length === 0 ? (
        <div className="grid place-items-center h-48 text-jb-ink3">
          <div className="text-center">
            <IconCheck size={32} className="mx-auto mb-3 text-jb-ink4" />
            <div className="font-semibold mb-1">{t("batch.noBatchesTitle")}</div>
            <div className="text-[13px]">{t("batch.noBatchesHint")}</div>
          </div>
        </div>
      ) : (
        <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}>
          {batches.map((b) => (
            <BatchCard key={b.id} batch={b} onCancel={handleCancel} />
          ))}
        </div>
      )}
    </div>
  );
}
