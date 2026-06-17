import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PlayCircle, RefreshCcw, Save, Square } from "lucide-react";
import type { TFunction } from "i18next";

import { scheduleService } from "@/services/schedule.service";
import type {
  ScheduleCommand,
  ScheduleConfig,
  ScheduleHistory,
} from "@/types/schedule.types";

interface Props {
  command: ScheduleCommand;
  title: string;
  description: string;
  /** Crawl/verify commands expose batch-size + browser flags; simpler commands
   *  (e.g. morning_refresh) only need the enable toggle + hours. */
  showCrawlOptions?: boolean;
}

/* ─── Re-usable NODE bits ────────────────────────────────────────── */

const CARD: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid var(--line)",
  borderRadius: 24,
  boxShadow: "var(--shadow-card)",
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const LABEL: React.CSSProperties = {
  font: "600 11px/16px var(--font-node-mono)",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--muted)",
};

const VALUE: React.CSSProperties = {
  font: "500 22px/1 var(--font-node-sans)",
  letterSpacing: "-0.03em",
  color: "var(--ink)",
};

function GhostBtn({
  icon, children, onClick, disabled, tone = "default",
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "success" | "danger" | "primary";
}) {
  const colors = {
    default: { fg: "var(--ink-soft)", bg: "transparent",                border: "var(--line-2)" },
    success: { fg: "#ffffff",          bg: "var(--green)",              border: "var(--green)" },
    danger:  { fg: "#ffffff",          bg: "var(--red)",                border: "var(--red)" },
    primary: { fg: "#ffffff",          bg: "var(--blue)",               border: "var(--blue)" },
  }[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-2"
      style={{
        background: colors.bg,
        color: colors.fg,
        border: `1px solid ${colors.border}`,
        borderRadius: 10,
        padding: "8px 14px",
        font: "600 12.5px/16px var(--font-node-sans)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        boxShadow: tone === "default" ? "var(--shadow-btn)" : undefined,
      }}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

function timeAgo(t: TFunction, iso: string | null | undefined): string {
  if (!iso) return "—";
  const sec = (Date.now() - new Date(iso).getTime()) / 1000;
  if (sec < 60) return t("timeAgo.seconds", { count: Math.round(sec) });
  if (sec < 3600) return t("timeAgo.minutes", { count: Math.round(sec / 60) });
  if (sec < 86400) return t("timeAgo.hours", { count: Math.round(sec / 3600) });
  return t("timeAgo.days", { count: Math.round(sec / 86400) });
}

/* ─── Page ───────────────────────────────────────────────────────── */

export default function SchedulePage({ command, title, description, showCrawlOptions = true }: Props) {
  const { t } = useTranslation("schedule");
  const [config, setConfig] = useState<ScheduleConfig | null>(null);
  const [history, setHistory] = useState<ScheduleHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editable form state mirrors `config` until save.
  const [form, setForm] = useState({
    enabled: false,
    batch_size: 100,
    hours_utc: "2,14",            // text input — parsed to int[]
    use_no_auth_check: false,
    headless: true,
  });

  // Live log state
  const [logText, setLogText] = useState("");
  const offsetRef = useRef(0);
  const pollRef = useRef<number | null>(null);

  // ── Fetch config + history ──
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, h] = await Promise.all([
        scheduleService.getConfig(command),
        scheduleService.getHistory(command, 20),
      ]);
      setConfig(c);
      setHistory(h);
      setForm({
        enabled: c.enabled,
        batch_size: c.batch_size,
        hours_utc: c.hours_utc.join(","),
        use_no_auth_check: c.use_no_auth_check,
        headless: c.headless,
      });
    } catch (e: any) {
      setError(e?.message || t("errors.load"));
    } finally {
      setLoading(false);
    }
  }, [command]);

  useEffect(() => { refresh(); }, [refresh]);

  // ── Live-log polling when active ──
  useEffect(() => {
    if (!config?.active_run.is_alive) {
      if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    // Reset offset when a new run starts (started_at change)
    const tick = async () => {
      try {
        const data = await scheduleService.tailLog(command, offsetRef.current);
        offsetRef.current = data.offset;
        if (data.text) setLogText((prev) => prev + data.text);
        if (!data.is_alive) {
          // Run finished; refresh config + history
          await refresh();
        }
      } catch { /* ignore one-off poll errors */ }
    };
    tick();   // immediate
    pollRef.current = window.setInterval(tick, 2000);
    return () => {
      if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [command, config?.active_run.is_alive, config?.active_run.started_at, refresh]);

  // Reset log text when new run begins
  useEffect(() => {
    offsetRef.current = 0;
    setLogText("");
  }, [config?.active_run.started_at]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const hours = form.hours_utc
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !Number.isNaN(n) && n >= 0 && n <= 23);
      const updated = await scheduleService.updateConfig(command, {
        enabled: form.enabled,
        batch_size: form.batch_size,
        hours_utc: hours,
        use_no_auth_check: form.use_no_auth_check,
        headless: form.headless,
      });
      setConfig(updated);
    } catch (e: any) {
      setError(e?.response?.data?.error?.message || e?.message || t("errors.save"));
    } finally {
      setSaving(false);
    }
  };

  const handleStart = async () => {
    setError(null);
    setStarting(true);
    try {
      const updated = await scheduleService.start(command);
      setConfig(updated);
      offsetRef.current = 0;
      setLogText("");
    } catch (e: any) {
      setError(e?.response?.data?.error?.message || e?.message || t("errors.start"));
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    setError(null);
    setStopping(true);
    try {
      const updated = await scheduleService.stop(command);
      setConfig(updated);
    } catch (e: any) {
      setError(e?.response?.data?.error?.message || e?.message || t("errors.stop"));
    } finally {
      setStopping(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── Header ── */}
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 style={{ font: "700 26px/1.1 var(--font-node-sans)", letterSpacing: "-0.025em", color: "var(--ink)", margin: 0 }}>
            {title}
          </h1>
          <p style={{ font: "400 13px/18px var(--font-node-sans)", color: "var(--muted)", margin: "6px 0 0" }}>
            {description}
          </p>
        </div>
        <GhostBtn icon={<RefreshCcw className="size-3.5" />} onClick={refresh}>{t("common:actions.refresh")}</GhostBtn>
      </header>

      {/* ── Pending workload ── */}
      <div className="grid gap-4 sm:grid-cols-2">
        <section style={CARD}>
          <p style={LABEL}>{t("pending.verifyTitle")}</p>
          <p style={{ ...VALUE, fontSize: 28 }}>
            {config?.pending?.verify?.toLocaleString() ?? "—"}
          </p>
          <p style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}>
            {t("pending.verifyHint")}
          </p>
        </section>
        <section style={CARD}>
          <p style={LABEL}>{t("pending.extractTitle")}</p>
          <p style={{ ...VALUE, fontSize: 28 }}>
            {config?.pending?.extract?.toLocaleString() ?? "—"}
          </p>
          <p style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}>
            {t("pending.extractHint")}
          </p>
        </section>
      </div>

      {error && (
        <div
          style={{
            background: "rgba(254,89,56,0.06)",
            border: "1px solid rgba(254,89,56,0.20)",
            borderRadius: 16,
            padding: 12,
            font: "500 12.5px/16px var(--font-node-sans)",
            color: "var(--red)",
          }}
        >
          {error}
        </div>
      )}

      {/* ── Config + Run controls ── */}
      <div className="grid gap-4 xl:grid-cols-2">
        <section style={CARD}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 style={{ font: "600 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)", margin: 0 }}>
                {t("config.title")}
              </h2>
              <p style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)", margin: "2px 0 0" }}>
                {t("config.subtitle")}
              </p>
            </div>
          </div>

          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 12 }}>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                style={{ accentColor: "var(--blue)", width: 16, height: 16 }}
              />
              <span style={{ font: "500 13px/18px var(--font-node-sans)", color: "var(--ink)" }}>{t("config.enabled")}</span>
              <span style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)" }}>
                {t("config.enabledHint")}
              </span>
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              {showCrawlOptions && (
                <div>
                  <p style={LABEL}>{t("config.batchSize")}</p>
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={form.batch_size}
                    onChange={(e) => setForm({ ...form, batch_size: parseInt(e.target.value || "0", 10) })}
                    style={{
                      width: "100%", height: 36, marginTop: 4,
                      borderRadius: 12, border: "1px solid var(--line)", background: "#ffffff",
                      padding: "0 10px", font: "500 13px/16px var(--font-node-mono)", color: "var(--ink)",
                      outline: "none",
                    }}
                  />
                </div>
              )}
              <div>
                <p style={LABEL}>{t("config.hoursLabel")}</p>
                <input
                  type="text"
                  value={form.hours_utc}
                  onChange={(e) => setForm({ ...form, hours_utc: e.target.value })}
                  placeholder="2,14"
                  style={{
                    width: "100%", height: 36, marginTop: 4,
                    borderRadius: 12, border: "1px solid var(--line)", background: "#ffffff",
                    padding: "0 10px", font: "500 13px/16px var(--font-node-mono)", color: "var(--ink)",
                    outline: "none",
                  }}
                />
              </div>
            </div>

            {showCrawlOptions && (
              <>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.use_no_auth_check}
                    onChange={(e) => setForm({ ...form, use_no_auth_check: e.target.checked })}
                    style={{ accentColor: "var(--blue)", width: 16, height: 16 }}
                  />
                  <span style={{ font: "500 13px/18px var(--font-node-sans)", color: "var(--ink)" }}>
                    {t("config.noAuthCheck")}
                  </span>
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.headless}
                    onChange={(e) => setForm({ ...form, headless: e.target.checked })}
                    style={{ accentColor: "var(--blue)", width: 16, height: 16 }}
                  />
                  <span style={{ font: "500 13px/18px var(--font-node-sans)", color: "var(--ink)" }}>{t("config.headless")}</span>
                  <span style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)" }}>
                    {t("config.headlessHint")}
                  </span>
                </label>
              </>
            )}

            <div className="flex items-center gap-2 pt-1">
              <GhostBtn
                icon={<Save className="size-3.5" />}
                onClick={handleSave}
                disabled={saving}
                tone="primary"
              >
                {saving ? t("common:status.saving") : t("config.saveConfig")}
              </GhostBtn>
              {config?.last_fired_at && (
                <span style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}>
                  {t("config.lastFired", { time: timeAgo(t, config.last_fired_at) })}
                </span>
              )}
            </div>
          </div>
        </section>

        <section style={CARD}>
          <h2 style={{ font: "600 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)", margin: 0 }}>
            {t("run.title")}
          </h2>
          <p style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)", margin: "2px 0 0" }}>
            {t("run.subtitle")}
          </p>

          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p style={LABEL}>{t("run.status")}</p>
                <p style={{ ...VALUE, fontSize: 18 }}>
                  {config?.active_run.is_alive ? (
                    <span style={{ color: "var(--green)" }}>{t("run.running")}</span>
                  ) : (
                    <span style={{ color: "var(--muted)" }}>{t("run.idle")}</span>
                  )}
                </p>
              </div>
              <div>
                <p style={LABEL}>{t("run.pid")}</p>
                <p style={{ ...VALUE, fontSize: 18, fontFamily: "var(--font-node-mono)" }}>
                  {config?.active_run.pid ?? "—"}
                </p>
              </div>
            </div>

            {config?.active_run.started_at && (
              <p style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)" }}>
                {t("run.startedAt", {
                  time: timeAgo(t, config.active_run.started_at),
                  logName: config.active_run.log_path?.split("/").pop(),
                })}
              </p>
            )}

            <div className="flex items-center gap-2 pt-2">
              <GhostBtn
                icon={<PlayCircle className="size-3.5" />}
                onClick={handleStart}
                disabled={!!config?.active_run.is_alive || starting || stopping}
                tone="success"
              >
                {starting ? t("run.starting") : t("run.runNow")}
              </GhostBtn>
              <GhostBtn
                icon={<Square className="size-3.5" />}
                onClick={handleStop}
                disabled={!config?.active_run.is_alive || stopping || starting}
                tone="danger"
              >
                {stopping ? t("run.stopping") : t("run.stop")}
              </GhostBtn>
            </div>
          </div>
        </section>
      </div>

      {/* ── Live log ── */}
      <section style={{ ...CARD, padding: 0, gap: 0 }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ font: "600 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)", margin: 0 }}>
              {t("log.title")}
            </h2>
            <p style={{ font: "400 11px/16px var(--font-node-mono)", color: "var(--muted)", margin: "2px 0 0" }}>
              {config?.active_run.is_alive ? t("log.polling") : t("log.idle")}
            </p>
          </div>
          {config?.active_run.is_alive && (
            <span aria-hidden style={{ width: 8, height: 8, borderRadius: 999, background: "var(--green)" }} />
          )}
        </div>
        <pre
          style={{
            margin: 0,
            padding: "12px 16px",
            font: "400 12px/1.55 var(--font-node-mono)",
            color: "var(--ink)",
            background: "var(--c2)",
            maxHeight: 360,
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            borderBottomLeftRadius: 24,
            borderBottomRightRadius: 24,
          }}
        >
          {logText || (loading ? t("log.loading") : t("log.noOutput"))}
        </pre>
      </section>

      {/* ── History ── */}
      <section style={CARD}>
        <h2 style={{ font: "600 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink)", margin: 0 }}>
          {t("history.title", { count: history?.runs.length ?? 0 })}
        </h2>
        <div className="overflow-x-auto" style={{ marginTop: 8 }}>
          <table className="w-full text-left">
            <thead>
              <tr style={{ font: "600 10.5px/14px var(--font-node-mono)", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--muted)" }}>
                <th className="py-2 pr-3 font-normal">{t("history.when")}</th>
                <th className="py-2 pr-3 font-normal">{t("history.wall")}</th>
                <th className="py-2 pr-3 font-normal">{t("history.examined")}</th>
                <th className="py-2 pr-3 font-normal">{t("history.outcomes")}</th>
              </tr>
            </thead>
            <tbody>
              {(history?.runs ?? []).map((r) => (
                <tr key={r.id} style={{ borderTop: "1px solid var(--line)" }}>
                  <td className="py-2.5 pr-3 whitespace-nowrap" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--ink-soft)" }} title={r.started_at}>
                    {timeAgo(t, r.started_at)}
                  </td>
                  <td className="py-2.5 pr-3" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--muted)" }}>
                    {r.wall_clock_s.toFixed(1)}s
                  </td>
                  <td className="py-2.5 pr-3" style={{ font: "400 12px/16px var(--font-node-mono)", color: "var(--ink)" }}>
                    {r.total_examined}
                  </td>
                  <td className="py-2.5 pr-3">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(r.counts_by_outcome || {}).map(([k, n]) => n ? (
                        <span
                          key={k}
                          style={{
                            background: "var(--c3)", color: "var(--ink-soft)",
                            font: "500 10.5px/14px var(--font-node-mono)",
                            padding: "1px 6px", borderRadius: 5,
                          }}
                        >
                          {k} {n}
                        </span>
                      ) : null)}
                    </div>
                  </td>
                </tr>
              ))}
              {(!history || history.runs.length === 0) && (
                <tr><td colSpan={4} style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)", padding: "12px 0" }}>
                  {t("history.empty")}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
