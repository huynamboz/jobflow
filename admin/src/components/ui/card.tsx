import type { CSSProperties, MouseEventHandler, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobNest Card — the single source of truth for the surface primitive:
 * white background, soft hairline border, 16px radius (20px with
 * `radius="lg"`), no resting shadow, optional hover lift.
 *
 * Back-compatible with the previous howard-card API (`hoverable`,
 * `padding`, `className`, `style`, `onClick`). `hoverable` now applies the
 * JobNest lift (translateY + soft shadow). Set `padding={0}` for full-bleed
 * content (covers, tables, list rows).
 */
export interface CardProps {
  children: ReactNode;
  /** Adds cursor + JobNest hover lift (use for clickable cards). */
  hoverable?: boolean;
  /** Inner padding in px (default 18). Pass 0 for full-bleed content. */
  padding?: number;
  /** Corner radius — 16px (default) or 20px feature card. */
  radius?: "md" | "lg";
  className?: string;
  style?: CSSProperties;
  onClick?: MouseEventHandler<HTMLDivElement>;
}

export function Card({
  children,
  hoverable = false,
  padding = 18,
  radius = "md",
  className = "",
  style,
  onClick,
}: CardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "border border-jn-line bg-jn-surface",
        radius === "lg" ? "rounded-jn-card-lg" : "rounded-jn-card",
        hoverable &&
          "cursor-pointer transition-[transform,box-shadow,border-color] duration-300 " +
            "hover:-translate-y-1 hover:shadow-jn-hover hover:border-jn-line-3",
        className,
      )}
      style={{ padding, ...style }}
    >
      {children}
    </div>
  );
}

export default Card;
