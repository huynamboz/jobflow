import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobNest segmented control — the sunken pill toggle ("All Documents /
 * Portal Milestones"). The active item lifts to a white surface with a soft
 * outline; inactive items are muted text. Controlled via `value`/`onChange`.
 */
export interface SegmentedItem<T extends string = string> {
  key: T;
  label: ReactNode;
}

export interface SegmentedProps<T extends string = string> {
  items: SegmentedItem<T>[];
  value: T;
  onChange: (key: T) => void;
  size?: "sm" | "md";
  className?: string;
}

export function Segmented<T extends string = string>({
  items,
  value,
  onChange,
  size = "md",
  className,
}: SegmentedProps<T>) {
  return (
    <div className={cn("inline-flex rounded-jn-btn bg-jn-sunken p-[3px]", className)}>
      {items.map((it) => {
        const active = it.key === value;
        return (
          <button
            key={it.key}
            type="button"
            onClick={() => onChange(it.key)}
            className={cn(
              "rounded-[8px] font-semibold transition-all duration-200 whitespace-nowrap",
              size === "sm" ? "px-3.5 py-1.5 text-[12.5px]" : "px-4 py-[7px] text-[13px]",
              active
                ? "bg-jn-surface text-jn-ink border border-jn-line-2 shadow-jn-card"
                : "border border-transparent text-jn-ink-mute hover:text-jn-ink",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

export default Segmented;
