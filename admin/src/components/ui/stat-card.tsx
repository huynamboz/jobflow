import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { BadgeColor } from "./badge";

/**
 * JobNest stat block — the dashboard "Docs Owed / Pending / Accepted" row:
 * a single bordered card with N stat columns separated by hairline dividers.
 * Each stat has a tinted icon chip, a label and a large value (+ optional
 * suffix like "/13"). Pass `footer` for the trailing "Go to …" link.
 */
export interface StatItem {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  /** Dim suffix after the value, e.g. "/13". */
  suffix?: ReactNode;
  /** Tint for the icon chip. */
  color?: BadgeColor;
}

const CHIP: Record<BadgeColor, string> = {
  blue: "bg-jn-primary-soft text-jn-primary",
  green: "bg-jn-green-bg text-jn-green",
  amber: "bg-jn-amber-bg text-jn-amber",
  red: "bg-jn-red-bg text-jn-red",
  violet: "bg-jn-violet-bg text-jn-violet",
  neutral: "bg-jn-sunken text-jn-ink-mute",
  ink: "bg-jn-sunken text-jn-ink",
};

function Stat({ icon, label, value, suffix, color = "blue", divided }: StatItem & { divided?: boolean }) {
  return (
    <div className={cn(divided && "border-l border-jn-line pl-[22px]")}>
      <div className="flex items-center gap-2.5 text-[13px] text-jn-ink-mute">
        <span className={cn("grid h-7 w-7 place-items-center rounded-lg", CHIP[color])}>{icon}</span>
        {label}
      </div>
      <div className="mt-2.5 text-[30px] font-extrabold leading-none text-jn-ink">
        {value}
        {suffix != null && <span className="ml-1 text-[15px] font-semibold text-jn-muted">{suffix}</span>}
      </div>
    </div>
  );
}

export interface StatGroupProps {
  items: StatItem[];
  footer?: ReactNode;
  className?: string;
}

export function StatGroup({ items, footer, className }: StatGroupProps) {
  return (
    <div className={cn("rounded-jn-card border border-jn-line bg-jn-surface p-[22px]", className)}>
      <div
        className="grid gap-[22px]"
        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
      >
        {items.map((it, i) => (
          <Stat key={i} {...it} divided={i > 0} />
        ))}
      </div>
      {footer && <div className="mt-[18px] text-[13px] font-semibold text-jn-ink">{footer}</div>}
    </div>
  );
}

export default StatGroup;
