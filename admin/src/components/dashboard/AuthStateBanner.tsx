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
      .catch(() => {/* silent — KpiStrip will surface */});
    return () => { alive = false; };
  }, [refreshKey]);

  if (!show) return null;
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-semibold">LinkedIn auth state invalid</p>
          <p className="text-xs text-danger-600">
            The saved <code>linkedin_state.json</code> is missing or lacks <code>li_at</code>.
            Run <code>python -m ml_service.crawler.providers.linkedin_auth</code> from the
            backend venv to re-login. See <code>roadmap/commands.md</code>.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => { sessionStorage.setItem(DISMISS_KEY, "1"); setShow(false); }}
        className="rounded-md p-1 hover:bg-danger-100"
        aria-label="Dismiss"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
