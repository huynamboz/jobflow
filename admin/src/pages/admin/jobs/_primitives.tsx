// ── Color helpers ──────────────────────────────────────────────────
const PLATFORM_PALETTE: Record<string, string> = {
  linkedin: "#0A66C2",
  indeed: "#2164F3",
  glassdoor: "#0CAA41",
  topcv: "#00B14F",
  vietnamworks: "#F36F21",
  itviec: "#E60028",
  greenhouse: "#24A47F",
  lever: "#6D28D9",
};

const FALLBACK_COLORS = [
  "#6D28D9", "#0A66C2", "#0CAA41", "#F36F21", "#E60028", "#0E7490", "#BE185D",
];

function strHash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) >>> 0;
  return h;
}

export function platformColor(name: string): string {
  const key = name.toLowerCase().replace(/\s+/g, "");
  return PLATFORM_PALETTE[key] ?? FALLBACK_COLORS[strHash(name) % FALLBACK_COLORS.length];
}

function platformAbbr(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase() || "??";
}

// ── Company logo ───────────────────────────────────────────────────
const LOGO_COLORS = [
  "#7C3AED", "#2563EB", "#059669", "#D97706",
  "#DC2626", "#0891B2", "#DB2777", "#4F46E5",
];

export function CompanyLogo({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  const mono = name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase() || "?";
  const bg = LOGO_COLORS[strHash(name) % LOGO_COLORS.length];
  const cls =
    size === "sm"
      ? "size-8 rounded-lg text-xs"
      : size === "lg"
      ? "size-[44px] rounded-xl text-sm"
      : "size-[38px] rounded-[10px] text-sm";
  return (
    <div
      className={`${cls} shrink-0 grid place-items-center font-[800] text-white shadow-sm`}
      style={{ background: bg }}
    >
      {mono}
    </div>
  );
}

// ── Platform logo (avatar slot — favicon if available, else colored abbr) ──
export function PlatformLogo({ name, logo, size = "md" }: { name: string; logo?: string; size?: "sm" | "md" | "lg" }) {
  const abbr = platformAbbr(name);
  const bg = platformColor(name);
  const cls =
    size === "sm"
      ? "size-8 rounded-lg text-xs"
      : size === "lg"
      ? "size-[44px] rounded-xl text-sm"
      : "size-[38px] rounded-[10px] text-sm";
  return (
    <>
      {logo && (
        <img
          src={logo}
          alt=""
          className={`${cls} shrink-0 object-contain bg-white border border-default-200 p-1 shadow-sm`}
          // fall back to the colored-abbr square if the favicon fails to load
          onError={(e) => {
            const el = e.currentTarget;
            const span = el.nextElementSibling as HTMLElement | null;
            el.style.display = "none";
            if (span) span.style.display = "";
          }}
        />
      )}
      <div
        className={`${cls} shrink-0 grid place-items-center font-[800] text-white shadow-sm`}
        style={{ background: bg, display: logo ? "none" : undefined }}
      >
        {abbr}
      </div>
    </>
  );
}

// ── Platform dot (favicon if available, else colored square with abbr) ──
export function PlatformDot({ name, logo, size = "md" }: { name: string; logo?: string; size?: "sm" | "md" }) {
  const abbr = platformAbbr(name);
  const bg = platformColor(name);
  const cls = size === "sm"
    ? "size-[18px] rounded-[5px] text-[8.5px]"
    : "size-[22px] rounded-[7px] text-[9.5px]";
  return (
    <>
      {logo && (
        <img
          src={logo}
          alt=""
          className={`${cls} shrink-0 object-contain bg-white`}
          // fall back to the colored-abbr square if the favicon fails to load
          onError={(e) => {
            const el = e.currentTarget;
            const span = el.nextElementSibling as HTMLElement | null;
            el.style.display = "none";
            if (span) span.style.display = "";
          }}
        />
      )}
      <span
        className={`${cls} shrink-0 inline-grid place-items-center font-[800] text-white`}
        style={{ background: bg, display: logo ? "none" : undefined }}
      >
        {abbr}
      </span>
    </>
  );
}

// ── Platform chip (dot + name, used inside cards) ──────────────────
export function PlatformChip({ name, logo }: { name: string; logo?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-default-100 pl-[3px] pr-2 py-[3px] text-[11.5px] font-semibold text-default-700">
      <PlatformDot name={name} logo={logo} size="sm" />
      {name}
    </span>
  );
}

// ── Seniority badge ────────────────────────────────────────────────
export const SENIORITY_LABEL: Record<number, string> = {
  0: "Intern", 1: "Junior", 2: "Mid", 3: "Senior", 4: "Lead", 5: "Manager",
};

const SENIORITY_CLS: Record<number, string> = {
  0: "bg-gray-100 text-gray-600",
  1: "bg-blue-100 text-blue-700",
  2: "bg-indigo-100 text-indigo-700",
  3: "bg-purple-100 text-purple-700",
  4: "bg-pink-100 text-pink-700",
  5: "bg-rose-100 text-rose-700",
};

export function SeniorityBadge({ level }: { level: number }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${SENIORITY_CLS[level] ?? "bg-gray-100 text-gray-600"}`}>
      {SENIORITY_LABEL[level] ?? `Level ${level}`}
    </span>
  );
}

// ── Work mode badge ────────────────────────────────────────────────
const WORK_MODE_CLS: Record<string, string> = {
  remote: "bg-green-50 text-green-700",
  hybrid: "bg-blue-50 text-blue-700",
  "on-site": "bg-amber-50 text-amber-600",
};

export function WorkModeBadge({ mode }: { mode: string }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-[0.04em] ${WORK_MODE_CLS[mode] ?? "bg-default-100 text-default-600"}`}>
      {mode}
    </span>
  );
}

// ── Status badge (active / inactive) ──────────────────────────────
type StatusKind = "active" | "inactive" | "running";

const STATUS_CLS: Record<StatusKind, string> = {
  active: "bg-green-50 text-green-700",
  running: "bg-violet-50 text-violet-600",
  inactive: "bg-default-100 text-default-500",
};

const STATUS_LABEL: Record<StatusKind, string> = {
  active: "active",
  running: "running",
  inactive: "inactive",
};

export function StatusBadge({ kind }: { kind: StatusKind }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-[3px] text-[11.5px] font-semibold ${STATUS_CLS[kind]}`}>
      <span className={`size-1.5 rounded-full bg-current ${kind === "running" ? "animate-pulse" : ""}`} />
      {STATUS_LABEL[kind]}
    </span>
  );
}

// ── Job type label ─────────────────────────────────────────────────
export const JOB_TYPE_LABEL: Record<string, string> = {
  "full-time": "Full-time",
  "part-time": "Part-time",
  remote: "Remote",
  hybrid: "Hybrid",
  "on-site": "On-site",
};

export const WORK_MODES = new Set(["remote", "hybrid", "on-site"]);

// ── Utility formatters ─────────────────────────────────────────────
const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", SGD: "S$", VND: "₫", EUR: "€", GBP: "£", JPY: "¥", AUD: "A$",
};

export function fmtSalary(min: number | null, max: number | null, currency = "USD"): string {
  if (!min && !max) return "—";
  const sym = CURRENCY_SYMBOL[currency] ?? currency + " ";
  const fmt = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
    return String(n);
  };
  if (min && max) return `${sym}${fmt(min)}–${sym}${fmt(max)}`;
  if (min) return `≥ ${sym}${fmt(min)}`;
  return `≤ ${sym}${fmt(max!)}`;
}

export function daysAgo(d: string | null): string {
  if (!d) return "—";
  const days = Math.max(0, Math.round((Date.now() - new Date(d).getTime()) / 86400000));
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}
