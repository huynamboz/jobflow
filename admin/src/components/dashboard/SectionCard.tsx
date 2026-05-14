import { ReactNode } from "react";
import { AlertCircle, Inbox, RefreshCcw } from "lucide-react";

interface SectionCardProps {
  title: string;
  description?: string;
  loading: boolean;
  error: Error | null;
  empty?: boolean;
  emptyMessage?: string;
  onRetry?: () => void;
  children: ReactNode;
  action?: ReactNode;
}

/**
 * NODE canonical card shell — matches preview/components-cards.html:
 *   background: var(--c1)
 *   border: 1px solid var(--line)
 *   border-radius: 16px
 *   box-shadow: var(--shadow-card)
 *   padding: 16px
 *   gap: 8px
 *
 * Typography:
 *   title  → 600 13px/18px sans, letter-spacing: -0.01em
 *   desc   → 400 12px/16px sans muted, letter-spacing: -0.01em
 *   meta   → 400 11px/16px mono muted (used inside content)
 */
export default function SectionCard({
  title,
  description,
  loading,
  error,
  empty,
  emptyMessage = "No data yet",
  onRetry,
  children,
  action,
}: SectionCardProps) {
  return (
    <section
      style={{
        background: "#ffffff",
        border: "1px solid var(--line)",
        borderRadius: 24,
        boxShadow: "var(--shadow-card)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2
            style={{
              font: "600 13px/18px var(--font-node-sans)",
              letterSpacing: "-0.01em",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            {title}
          </h2>
          {description && (
            <p
              style={{
                font: "400 12px/16px var(--font-node-sans)",
                letterSpacing: "-0.01em",
                color: "var(--muted)",
                margin: 0,
              }}
            >
              {description}
            </p>
          )}
        </div>
        {action}
      </header>

      <div style={{ marginTop: 8 }}>
        {loading && (
          <div
            className="flex items-center gap-2"
            style={{ font: "400 12px/16px var(--font-node-sans)", color: "var(--muted)" }}
            aria-live="polite"
          >
            <span className="inline-block animate-pulse" style={{ width: 8, height: 8, borderRadius: 999, background: "var(--c5)" }} />
            Loading…
          </div>
        )}

        {!loading && error && (
          <div
            style={{
              background: "rgba(254,89,56,0.06)",
              border: "1px solid rgba(254,89,56,0.18)",
              borderRadius: 12,
              padding: 12,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div className="flex items-center gap-2" style={{ font: "600 12.5px/16px var(--font-node-sans)", color: "var(--red)" }}>
              <AlertCircle className="size-4" />
              <span>Failed to load</span>
            </div>
            <p style={{ font: "400 11.5px/16px var(--font-node-sans)", color: "var(--ink-soft)", letterSpacing: "-0.01em", margin: 0 }}>
              {error.message}
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 self-start"
                style={{
                  font: "600 11.5px/16px var(--font-node-sans)",
                  color: "var(--ink)",
                  background: "var(--c1)",
                  border: "1px solid var(--line-2)",
                  borderRadius: 8,
                  padding: "4px 10px",
                  boxShadow: "var(--shadow-btn)",
                }}
              >
                <RefreshCcw className="size-3" /> Retry
              </button>
            )}
          </div>
        )}

        {!loading && !error && empty && (
          <div
            className="flex flex-col items-center gap-2"
            style={{ font: "400 12.5px/18px var(--font-node-sans)", color: "var(--muted)", padding: "40px 0" }}
          >
            <Inbox className="size-6" strokeWidth={1.5} />
            <span>{emptyMessage}</span>
          </div>
        )}

        {!loading && !error && !empty && children}
      </div>
    </section>
  );
}

/* Shared typography styles used by section internals. */
export const NODE_TITLE: React.CSSProperties = {
  font: "600 13px/18px var(--font-node-sans)",
  letterSpacing: "-0.01em",
  color: "var(--ink)",
  margin: 0,
};

export const NODE_DESC: React.CSSProperties = {
  font: "400 12px/16px var(--font-node-sans)",
  letterSpacing: "-0.01em",
  color: "var(--muted)",
  margin: 0,
};

export const NODE_META: React.CSSProperties = {
  font: "400 11px/16px var(--font-node-mono)",
  color: "var(--muted)",
  margin: 0,
};

/** Big display number used inside Wallet/KPI hero contexts.
 *  Sans-serif, 500 weight, tight negative tracking. */
export const NODE_DISPLAY_NUMBER: React.CSSProperties = {
  font: "500 28px/1 var(--font-node-sans)",
  letterSpacing: "-0.03em",
  color: "var(--ink)",
};
