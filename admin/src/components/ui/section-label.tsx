import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * JobFlow section label — the tiny uppercase caption above a group
 * ("APPLICATION DETAILS"). Faint, bold, wide letter-spacing.
 */
export function SectionLabel({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "text-[11px] font-bold uppercase tracking-[0.06em] text-jn-faint",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export default SectionLabel;
