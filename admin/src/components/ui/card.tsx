import type { CSSProperties, MouseEventHandler, ReactNode } from "react";

/**
 * Shared admin Card — the single source of truth for the howard-style card
 * surface: white background, soft slate-200/70 border, 16px radius, no resting
 * shadow (optional subtle hover lift via `hoverable`). Tweak the look once in
 * globals.css (--card-border / --card-radius) and every card follows.
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
      className={`${hoverable ? "jb-card-hover " : ""}${className}`}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--card-border)",
        borderRadius: "var(--card-radius)",
        padding,
        ...(hoverable ? { cursor: "pointer", transition: "transform 0.14s, box-shadow 0.14s" } : {}),
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export default Card;
