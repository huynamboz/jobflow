import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * JobFlow Button — the single source of truth for action buttons.
 *
 *  variant: primary  → solid blue, drop shadow (the main CTA)
 *           secondary→ white surface, soft outline (the default action)
 *           ghost    → transparent, hover sunken
 *           danger   → solid red
 *  size:    sm | md
 *
 * Icons: pass `leftIcon` / `rightIcon` (already-sized SVG nodes). `loading`
 * swaps the left slot for a spinner and disables the button.
 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  loading?: boolean;
  fullWidth?: boolean;
}

const BASE =
  "inline-flex items-center justify-center gap-2 font-semibold whitespace-nowrap " +
  "rounded-jn-btn transition-[background,transform,box-shadow,color,border-color] duration-200 " +
  "select-none disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-jn-primary/40 focus-visible:ring-offset-1";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-jn-primary text-white shadow-jn-btn hover:bg-jn-primary-hover " +
    "hover:-translate-y-px active:translate-y-0 border border-transparent",
  secondary:
    "bg-jn-surface text-jn-ink border border-jn-line-3 hover:bg-jn-sunken",
  ghost:
    "bg-transparent text-jn-ink-soft border border-transparent hover:bg-jn-sunken",
  danger:
    "bg-jn-red text-white border border-transparent hover:brightness-95 " +
    "hover:-translate-y-px active:translate-y-0",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-9 px-3.5 text-[13px]",
  md: "h-11 px-[18px] text-[13.5px]",
};

function Spinner() {
  return (
    <svg
      className="animate-spin"
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    leftIcon,
    rightIcon,
    loading = false,
    fullWidth = false,
    className,
    disabled,
    children,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(BASE, VARIANTS[variant], SIZES[size], fullWidth && "w-full", className)}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  );
});

export default Button;
