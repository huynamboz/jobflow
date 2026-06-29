import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobNest Badge — the tinted pill used for statuses, departments, counts and
 * tags. Soft fill + matching foreground by `color`. Add `dot` for the small
 * leading status dot; `solid` for an inverted dark/strong pill.
 *
 *   <Badge color="green" dot>Active</Badge>
 *   <Badge color="blue">12 members</Badge>
 *   <Badge color="ink" solid>+2</Badge>
 */
export type BadgeColor =
  | "blue"
  | "green"
  | "amber"
  | "red"
  | "violet"
  | "neutral"
  | "ink";

export type BadgeSize = "sm" | "md";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  color?: BadgeColor;
  size?: BadgeSize;
  dot?: boolean;
  solid?: boolean;
  leftIcon?: ReactNode;
  children: ReactNode;
}

// [softFill, softText, dotColor, solidFill, solidText]
const COLORS: Record<BadgeColor, { soft: string; dot: string; solid: string }> = {
  blue: { soft: "bg-jn-primary-soft text-jn-primary", dot: "bg-jn-primary", solid: "bg-jn-primary text-white" },
  green: { soft: "bg-jn-green-bg text-jn-green", dot: "bg-jn-green", solid: "bg-jn-green text-white" },
  amber: { soft: "bg-jn-amber-bg text-jn-amber", dot: "bg-jn-amber", solid: "bg-jn-amber text-white" },
  red: { soft: "bg-jn-red-bg text-jn-red", dot: "bg-jn-red", solid: "bg-jn-red text-white" },
  violet: { soft: "bg-jn-violet-bg text-jn-violet", dot: "bg-jn-violet", solid: "bg-jn-violet text-white" },
  neutral: { soft: "bg-jn-sunken text-jn-ink-mute", dot: "bg-jn-muted", solid: "bg-jn-line-3 text-jn-ink" },
  ink: { soft: "bg-jn-sunken text-jn-ink", dot: "bg-jn-ink", solid: "bg-jn-ink text-white" },
};

const SIZES: Record<BadgeSize, string> = {
  sm: "text-[11px] px-2.5 py-0.5 gap-1.5",
  md: "text-[12px] px-3 py-1 gap-1.5",
};

export function Badge({
  color = "neutral",
  size = "sm",
  dot = false,
  solid = false,
  leftIcon,
  className,
  children,
  ...rest
}: BadgeProps) {
  const c = COLORS[color];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-jn-pill font-semibold leading-none whitespace-nowrap",
        solid ? c.solid : c.soft,
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", solid ? "bg-current" : c.dot)} />}
      {leftIcon}
      {children}
    </span>
  );
}

export default Badge;
