import type { JDBatch } from "@/types/job.types";

export const T = {
  accent:    "#167a7a",
  accent600: "oklch(0.48 0.20 240)",
  accent50:  "#e8f4f4",
  accent100: "oklch(0.92 0.07 240)",
  success:   "oklch(0.62 0.17 155)",
  success50: "oklch(0.96 0.04 155)",
  danger:    "oklch(0.60 0.22 25)",
  danger50:  "oklch(0.96 0.03 25)",
  warning:   "oklch(0.76 0.16 70)",
  warning50: "oklch(0.97 0.04 75)",
  ink:       "oklch(0.18 0.02 265)",
  ink2:      "oklch(0.38 0.015 265)",
  ink3:      "oklch(0.56 0.012 265)",
  ink4:      "oklch(0.72 0.008 265)",
  surface:   "#ffffff",
  surface2:  "oklch(0.97 0.005 85)",
  surface3:  "oklch(0.945 0.006 85)",
  line:      "oklch(0.92 0.006 85)",
  lineStrong:"oklch(0.86 0.008 85)",
};

export const POLL_INTERVAL = 2000;
export const PAGE_SIZE = 50;

export const LIMIT_OPTIONS = [
  { label: "All",   value: null },
  { label: "100",   value: 100  },
  { label: "500",   value: 500  },
  { label: "1 000", value: 1000 },
] as const;

export function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

export function eta(batch: Pick<JDBatch, "status" | "done_count" | "total" | "error_count">): string {
  if (batch.status !== "running" || batch.done_count === 0) return "";
  const remaining = batch.total - batch.done_count - batch.error_count;
  if (remaining <= 0) return "";
  const secs = remaining * 4;
  return secs < 60 ? `~${secs}s left` : `~${Math.round(secs / 60)}min left`;
}
