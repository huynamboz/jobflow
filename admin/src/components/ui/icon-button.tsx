import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobNest IconButton — square, icon-only control used in headers, toolbars
 * and card corners (bell, search, more, etc.).
 *
 *  variant: ghost   → transparent, hover sunken (header tools)
 *           soft    → tinted sunken fill (the 46px round mail/call tiles)
 *           outline → white surface with a soft outline
 *  shape:   square  → rounded-jn-btn (10px)
 *           circle  → fully round
 *
 * Optional `dot` renders a small status dot in the top-right corner.
 */
export type IconButtonVariant = "ghost" | "soft" | "outline";
export type IconButtonSize = "sm" | "md" | "lg";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: IconButtonVariant;
  size?: IconButtonSize;
  shape?: "square" | "circle";
  /** Colored status dot in the corner (e.g. unread). Pass any CSS color. */
  dot?: string;
  children: ReactNode;
}

const VARIANTS: Record<IconButtonVariant, string> = {
  ghost: "bg-transparent text-jn-ink-soft hover:bg-jn-sunken hover:text-jn-ink",
  soft: "bg-jn-sunken text-jn-ink-soft hover:brightness-[0.97]",
  outline: "bg-jn-surface text-jn-ink-soft border border-jn-line-3 hover:bg-jn-sunken",
};

const SIZES: Record<IconButtonSize, string> = {
  sm: "h-8 w-8",
  md: "h-[38px] w-[38px]",
  lg: "h-[46px] w-[46px]",
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { variant = "ghost", size = "md", shape = "square", dot, className, children, type = "button", ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(
          "relative inline-flex items-center justify-center shrink-0 cursor-pointer",
          "transition-[background,color,filter] duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-jn-primary/40",
          "disabled:cursor-not-allowed disabled:opacity-60",
          shape === "circle" ? "rounded-full" : "rounded-jn-btn",
          VARIANTS[variant],
          SIZES[size],
          className,
        )}
        {...rest}
      >
        {children}
        {dot && (
          <span
            aria-hidden
            className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full"
            style={{ background: dot }}
          />
        )}
      </button>
    );
  },
);

export default IconButton;
