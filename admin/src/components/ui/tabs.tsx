import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobNest underline Tabs — the row of text tabs with a blue active underline
 * sitting on a hairline baseline (see the candidate-detail mockup). Controlled:
 * pass `value` + `onChange`. Optional per-tab `count` renders a small pill.
 */
export interface TabItem<T extends string = string> {
  key: T;
  label: ReactNode;
  count?: number;
}

export interface TabsProps<T extends string = string> {
  items: TabItem<T>[];
  value: T;
  onChange: (key: T) => void;
  className?: string;
}

export function Tabs<T extends string = string>({ items, value, onChange, className }: TabsProps<T>) {
  return (
    <div className={cn("flex gap-7 overflow-x-auto border-b border-jn-line", className)}>
      {items.map((it) => {
        const active = it.key === value;
        return (
          <button
            key={it.key}
            type="button"
            onClick={() => onChange(it.key)}
            className={cn(
              "flex items-center gap-2 whitespace-nowrap border-b-2 py-3.5 text-[14px] -mb-px transition-colors",
              active
                ? "border-jn-primary font-bold text-jn-primary"
                : "border-transparent font-medium text-jn-muted hover:text-jn-ink-soft",
            )}
          >
            {it.label}
            {it.count != null && (
              <span
                className={cn(
                  "grid h-[19px] min-w-[19px] place-items-center rounded-full px-1 text-[11px] font-bold",
                  active ? "bg-jn-primary text-white" : "bg-jn-ink text-white",
                )}
              >
                {it.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
