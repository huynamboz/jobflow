import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, X } from "lucide-react";

import { dashboardService } from "@/services/dashboard.service";

const DISMISS_KEY = "dashboard.authBanner.dismissed";

interface Props { refreshKey: number }

export default function AuthStateBanner({ refreshKey }: Props) {
  const { t } = useTranslation("dashboard");
  const [show, setShow] = useState(false);

  useEffect(() => {
    let alive = true;
    const dismissed = sessionStorage.getItem(DISMISS_KEY) === "1";
    if (dismissed) return;
    dashboardService.getKpi()
      .then((kpi) => {
        if (!alive) return;
        if (!kpi.auth_state.has_li_at) setShow(true);
      })
      .catch(() => { /* silent — KpiStrip surfaces */ });
    return () => { alive = false; };
  }, [refreshKey]);

  if (!show) return null;
  return (
    <div
      className="flex items-start justify-between gap-3"
      style={{
        background: "rgba(254,89,56,0.06)",
        border: "1px solid rgba(254,89,56,0.20)",
        borderRadius: 24,
        padding: 16,
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" strokeWidth={1.75} style={{ color: "var(--red)" }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <p style={{ font: "600 13px/18px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--red)", margin: 0 }}>
            {t("authBanner.title")}
          </p>
          <p style={{ font: "400 12px/16px var(--font-node-sans)", letterSpacing: "-0.01em", color: "var(--ink-soft)", margin: 0 }}>
            {t("authBanner.bodyPrefix")} <code style={{ font: "400 11.5px/16px var(--font-node-mono)" }}>linkedin_state.json</code> {t("authBanner.bodyMissing")}{" "}
            <code style={{ font: "400 11.5px/16px var(--font-node-mono)" }}>li_at</code>{t("authBanner.bodyRun")}{" "}
            <code style={{ font: "400 11.5px/16px var(--font-node-mono)" }}>python -m ml_service.crawler.providers.linkedin_auth</code>{" "}
            {t("authBanner.bodyFromVenv")} <code style={{ font: "400 11.5px/16px var(--font-node-mono)" }}>roadmap/commands.md</code>.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => { sessionStorage.setItem(DISMISS_KEY, "1"); setShow(false); }}
        aria-label={t("authBanner.dismiss")}
        style={{
          borderRadius: 8,
          padding: 4,
          background: "transparent",
          border: "none",
          color: "var(--ink-soft)",
        }}
      >
        <X className="size-4" strokeWidth={1.75} />
      </button>
    </div>
  );
}
