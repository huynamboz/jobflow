import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { IconChevronRight, IconArrowLeft } from "@tabler/icons-react";

import { cn } from "@/lib/utils";

/**
 * JobNest breadcrumb — the muted trail above a detail title, with an optional
 * leading back-arrow. The last crumb is rendered as the current (ink) page;
 * earlier crumbs link via `href`. Add `onBack` to show the back arrow.
 */
export interface Crumb {
  label: ReactNode;
  href?: string;
}

export interface BreadcrumbProps {
  items: Crumb[];
  onBack?: () => void;
  className?: string;
}

export function Breadcrumb({ items, onBack, className }: BreadcrumbProps) {
  return (
    <nav className={cn("flex items-center gap-2.5 text-[13.5px] text-jn-muted", className)}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          aria-label="Back"
          className="text-jn-ink-soft transition-colors hover:text-jn-ink"
        >
          <IconArrowLeft size={16} />
        </button>
      )}
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-2.5">
            {c.href && !last ? (
              <Link
                to={c.href}
                className={cn("transition-colors hover:text-jn-ink-soft", i === 0 && "font-semibold text-jn-ink")}
              >
                {c.label}
              </Link>
            ) : (
              <span className={cn(last ? "text-jn-ink-mute" : "font-semibold text-jn-ink")}>{c.label}</span>
            )}
            {!last && <IconChevronRight size={13} className="text-jn-faint" />}
          </span>
        );
      })}
    </nav>
  );
}

export default Breadcrumb;
