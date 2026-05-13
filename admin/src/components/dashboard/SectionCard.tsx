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
  /** Extra action element rendered in the header right side (e.g. filter chip). */
  action?: ReactNode;
}

/**
 * NODE-styled section shell.
 *
 *   ┌──────────────────────────────────────────────────┐
 *   │  TITLE in dark ink, eyebrow caption in mono caps │
 *   │  ── thin --line divider ────                      │
 *   │  content                                          │
 *   └──────────────────────────────────────────────────┘
 *
 * Background: var(--surface) (cool white)
 * Border: 1px var(--line)
 * Radius: var(--r-20)
 * Shadow: var(--shadow-card)
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
      className="rounded-node-20"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        boxShadow: "var(--shadow-card)",
      }}
    >
      <header className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div>
          <h2
            className="font-node-sans text-node-ink"
            style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.015em", margin: 0 }}
          >
            {title}
          </h2>
          {description && (
            <p
              className="font-node-mono text-node-muted mt-1"
              style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}
            >
              {description}
            </p>
          )}
        </div>
        {action}
      </header>

      <div className="px-5 pb-5">
        {loading && (
          <div
            className="flex items-center gap-2 text-node-muted"
            style={{ fontSize: 12 }}
            aria-live="polite"
          >
            <span className="inline-block size-2.5 animate-pulse rounded-full bg-node-c5" />
            Loading…
          </div>
        )}

        {!loading && error && (
          <div
            className="flex flex-col gap-2 rounded-node-12 p-3"
            style={{ background: "rgba(254,89,56,0.06)", border: "1px solid rgba(254,89,56,0.18)" }}
          >
            <div className="flex items-center gap-2 text-node-red" style={{ fontSize: 12.5 }}>
              <AlertCircle className="size-4" />
              <span style={{ fontWeight: 600 }}>Failed to load</span>
            </div>
            <p className="text-node-ink-soft" style={{ fontSize: 11.5 }}>
              {error.message}
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 self-start rounded-node-8 px-2.5 py-1 font-node-sans"
                style={{
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: "var(--ink)",
                  background: "var(--c1)",
                  border: "1px solid var(--line-2)",
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
            className="flex flex-col items-center gap-2 py-10 text-node-muted"
            style={{ fontSize: 12.5 }}
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

/* Reusable typography utilities for sections to consume. */
export const NODE_LABEL_STYLE: React.CSSProperties = {
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--muted)",
  fontFamily: "var(--font-node-mono)",
};

export const NODE_NUMBER_STYLE: React.CSSProperties = {
  fontFamily: "var(--font-node-mono)",
  fontWeight: 500,
  letterSpacing: "-0.03em",
  color: "var(--ink)",
};
