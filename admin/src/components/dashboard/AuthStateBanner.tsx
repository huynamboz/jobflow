import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

import { dashboardService } from "@/services/dashboard.service";

const DISMISS_KEY = "dashboard.authBanner.dismissed";

interface Props { refreshKey: number }

export default function AuthStateBanner({ refreshKey }: Props) {
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
      className="flex items-start justify-between gap-3 rounded-node-16"
      style={{
        background: "rgba(254,89,56,0.06)",
        border: "1px solid rgba(254,89,56,0.20)",
        padding: 14,
      }}
    >
      <div className="flex items-start gap-2.5 text-node-red" style={{ fontSize: 13 }}>
        <AlertTriangle className="mt-0.5 size-4 shrink-0" strokeWidth={1.75} />
        <div>
          <p style={{ fontWeight: 600, letterSpacing: "-0.005em" }}>
            LinkedIn auth state invalid
          </p>
          <p className="text-node-ink-soft mt-1" style={{ fontSize: 11.5, letterSpacing: "-0.005em" }}>
            Saved <code className="font-node-mono">linkedin_state.json</code> is missing or lacks{" "}
            <code className="font-node-mono">li_at</code>. Run{" "}
            <code className="font-node-mono">python -m ml_service.crawler.providers.linkedin_auth</code> from the
            backend venv. See <code className="font-node-mono">roadmap/commands.md</code>.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => { sessionStorage.setItem(DISMISS_KEY, "1"); setShow(false); }}
        className="rounded-node-8 p-1 transition-colors hover:bg-node-c3"
        aria-label="Dismiss"
      >
        <X className="size-4" strokeWidth={1.75} />
      </button>
    </div>
  );
}
