import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@heroui/button";
import { IconFileText, IconLoader2, IconPlus } from "@tabler/icons-react";

import { cn } from "@/lib/utils";
import { jobService } from "@/services/job.service";
import type { JDBatch } from "@/types/job.types";
import { POLL_INTERVAL, fmtDate } from "./_tokens";
import { Badge, type BadgeStatus, KeyframeStyle, ProgressBar, StatCard } from "./_primitives";

function BatchCard({ batch, onClick }: { batch: JDBatch; onClick: () => void }) {
  const { t } = useTranslation("llm");
  const processed = batch.done_count + batch.error_count;
  const pct = batch.total > 0 ? (batch.done_count / batch.total) * 100 : 0;

  return (
    <div
      className="jb-card-hover bg-jb-surface border border-jb-line rounded-[20px] p-[18px] cursor-pointer transition-[transform,box-shadow] duration-150"
      onClick={onClick}
    >
      <div className="flex justify-between items-center mb-2.5">
        <Badge status={batch.status as BadgeStatus} />
        <span className="font-mono text-[11px] text-jb-ink4">{fmtDate(batch.created_at)}</span>
      </div>

      <div className="font-bold text-[15px] tracking-[-0.01em]">{t("batch.overview.card.batch", { id: batch.id })}</div>
      <div className="font-mono text-[12px] text-jb-ink3 mt-0.5">
        {batch.file_path.split("/").pop()}
      </div>

      <div className="mt-3.5">
        <ProgressBar
          value={batch.done_count} errors={batch.error_count} total={batch.total}
          running={batch.status === "running"} done={batch.status === "done"}
        />
        <div className="flex justify-between text-xs mt-2">
          <span className="text-jb-ink3">{t("batch.overview.card.records", { done: batch.done_count, total: batch.total })}</span>
          <span className="font-semibold">{pct.toFixed(0)}%</span>
        </div>
      </div>

      <div className="h-px bg-jb-line my-3.5" />

      <div className="grid grid-cols-2 gap-2.5 text-[11.5px]">
        <div>
          <div className="uppercase tracking-[0.05em] font-semibold text-[10px] text-jb-ink4">{t("batch.overview.card.fields")}</div>
          <div className="mt-0.5 text-jb-ink2">{t("batch.overview.card.fieldsCombined", { count: batch.fields_config.length })}</div>
        </div>
        <div>
          <div className="uppercase tracking-[0.05em] font-semibold text-[10px] text-jb-ink4">{t("batch.overview.card.errors")}</div>
          <div className={cn("mt-0.5 font-semibold", batch.error_count > 0 ? "text-jb-danger" : "text-jb-ink2")}>
            {batch.error_count}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function JDBatchOverview() {
  const { t } = useTranslation("llm");
  const navigate = useNavigate();
  const [batches, setBatches] = useState<JDBatch[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setBatches(await jobService.listBatches()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const hasRunning = batches.some((b) => b.status === "running");
    if (!hasRunning) return;
    const id = setInterval(load, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [batches, load]);

  const totalRecords = batches.reduce((s, b) => s + b.total, 0);
  const totalDone    = batches.reduce((s, b) => s + b.done_count, 0);
  const runningCount = batches.filter((b) => b.status === "running").length;

  return (
    <div className="flex flex-col gap-5">
      <KeyframeStyle />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div>
          <h1 className="text-[26px] sm:text-[32px] font-bold tracking-[-0.025em] m-0 text-jb-ink">
            {t("batch.overview.titlePrefix")} <span className="italic text-jb-accent font-normal">{t("batch.overview.titleAccent")}</span>
          </h1>
          <p className="mt-1 text-jb-ink3 text-sm m-0">
            {t("batch.overview.description")}
          </p>
        </div>
        <div className="sm:ml-auto">
          <Button color="primary" startContent={<IconPlus size={14} />} onPress={() => navigate("new")}>
            {t("batch.overview.newBatch")}
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label={t("batch.overview.statActiveNow")}        value={runningCount}               unit={t("batch.overview.statActiveNowUnit")}  accent={runningCount > 0} />
        <StatCard label={t("batch.overview.statTotalBatches")}     value={batches.length}             unit={t("batch.overview.statTotalBatchesUnit")} />
        <StatCard label={t("batch.overview.statRecordsExtracted")} value={totalDone.toLocaleString()} unit={`/ ${totalRecords.toLocaleString()}`} />
        <StatCard label={t("batch.overview.statLastBatch")}        value={batches[0] ? `#${batches[0].id}` : "—"} />
      </div>

      {/* Batch grid */}
      {loading ? (
        <div className="grid place-items-center h-40 text-jb-ink3">
          <IconLoader2 size={20} className="animate-[jb-spin_0.7s_linear_infinite]" />
        </div>
      ) : batches.length === 0 ? (
        <div className="grid place-items-center h-60 text-jb-ink3">
          <div className="text-center">
            <IconFileText size={32} className="mx-auto mb-3 text-jb-ink4" />
            <div className="font-semibold mb-1">{t("batch.overview.emptyTitle")}</div>
            <div className="text-[13px]">{t("batch.overview.emptyHint")}</div>
          </div>
        </div>
      ) : (
        <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(320px,1fr))" }}>
          {batches.map((b) => (
            <BatchCard key={b.id} batch={b} onClick={() => navigate(String(b.id))} />
          ))}
        </div>
      )}
    </div>
  );
}
