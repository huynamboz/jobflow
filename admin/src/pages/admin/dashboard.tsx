import { useCallback, useState } from "react";
import { RefreshCcw } from "lucide-react";

import StaffingDashboard from "@/components/dashboard/StaffingDashboard";

export default function DashboardPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1
            style={{
              font: "600 24px/1.1 var(--font-node-sans)",
              letterSpacing: "-0.025em",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            Dashboard
          </h1>
          <p
            style={{
              font: "400 13px/18px var(--font-node-sans)",
              letterSpacing: "-0.01em",
              color: "var(--muted)",
              margin: "4px 0 0",
            }}
          >
            What your team needs to handle today.
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-2"
          style={{
            font: "600 12.5px/16px var(--font-node-sans)",
            color: "var(--ink)",
            background: "#ffffff",
            border: "1px solid var(--line-2)",
            borderRadius: 10,
            padding: "6px 12px",
            boxShadow: "var(--shadow-btn)",
          }}
        >
          <RefreshCcw className="size-3.5" strokeWidth={1.75} />
          Refresh
        </button>
      </header>

      <StaffingDashboard refreshKey={refreshKey} />
    </div>
  );
}
