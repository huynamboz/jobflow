import type { CSSProperties, MouseEventHandler, ReactNode } from "react";

/**
 * Shared admin Card — the single source of truth for the howard-style card
 * surface: white background, soft slate-200/70 border (`border-card-border`),
 * 16px radius (`rounded-2xl`), no resting shadow, optional subtle hover lift.
 * Built with Tailwind utilities for consistency; tweak the border token once
 * in globals.css (--card-border) and every card follows.
 */
export interface CardProps {
  children: ReactNode;
  /** Adds cursor + a subtle hover lift (use for clickable cards). */
  hoverable?: boolean;
  /** Inner padding in px (default 18). Pass 0 for full-bleed content. */
  padding?: number;
  className?: string;
  style?: CSSProperties;
  onClick?: MouseEventHandler<HTMLDivElement>;
}

export function Card({
  children,
  hoverable = false,
  padding = 18,
  className = "",
  style,
  onClick,
}: CardProps) {
  return (
    <div
      onClick={onClick}
      className={[
        "rounded-2xl border border-card-border bg-white",
        hoverable ? "jb-card-hover cursor-pointer transition-[transform,box-shadow]" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ padding, ...style }}
    >
      {children}
    </div>
  );
}

export default Card;
