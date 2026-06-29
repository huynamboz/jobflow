import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobFlow page header — the big page title row: an extrabold title with an
 * optional inline count/status pill, a muted subtitle, and a right-aligned
 * actions slot (Export / Add member …). Mirrors the Employees mockup header.
 */
export interface PageHeaderProps {
  title: ReactNode;
  /** Inline pill next to the title (e.g. <Badge>12 members</Badge>). */
  pill?: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned action buttons. */
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, pill, subtitle, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-5", className)}>
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <h1 className="m-0 text-[27px] font-extrabold tracking-[-0.02em] text-jn-ink">{title}</h1>
          {pill}
        </div>
        {subtitle && <div className="mt-1.5 text-[14px] text-jn-ink-mute">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </div>
  );
}

export default PageHeader;
