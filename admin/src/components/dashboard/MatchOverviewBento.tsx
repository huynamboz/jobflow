import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  IconSparkles,
  IconStack2,
  IconSend,
  IconTrophy,
  IconArrowRight,
  IconArrowUpRight,
} from "@tabler/icons-react";

import { Avatar, AvatarStack, Badge } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { JobsOverview } from "@/types/dashboard.types";
import type { StaffingDashboard } from "@/types/staffing-dashboard.types";

const fmt = new Intl.NumberFormat();

/* ── tiny inline charts ──────────────────────────────────────────────── */

/** Smooth-ish area sparkline from a daily series. */
function Sparkline({ data, color }: { data: { count: number }[]; color: string }) {
  const d = useMemo(() => {
    const vals = data.length ? data.map((p) => p.count) : [0, 0];
    const max = Math.max(1, ...vals);
    const n = vals.length;
    const x = (i: number) => (n === 1 ? 0 : (i / (n - 1)) * 150);
    const y = (v: number) => 28 - (v / max) * 24 - 2;
    const line = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    return { line, area: `${line} L 150 30 L 0 30 Z` };
  }, [data]);
  return (
    <svg viewBox="0 0 150 30" preserveAspectRatio="none" className="mt-auto h-[26px] w-full overflow-visible">
      <path d={d.area} fill={`${color}22`} />
      <path d={d.line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Progress ring with a centred percentage. */
function Ring({ pct, color }: { pct: number; color: string }) {
  const r = 32;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.max(0, Math.min(1, pct / 100)));
  return (
    <div className="relative h-[78px] w-[78px] shrink-0">
      <svg width={78} height={78} viewBox="0 0 78 78" className="-rotate-90">
        <circle cx={39} cy={39} r={r} fill="none" stroke="#EEF0F2" strokeWidth={8} />
        <circle
          cx={39}
          cy={39}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(.2,.7,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-[18px] font-extrabold text-jn-ink">
        {Math.round(pct)}%
      </div>
    </div>
  );
}

/* ── tile chrome ─────────────────────────────────────────────────────── */

function Tile({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "jn-reveal flex flex-col rounded-[18px] border border-jn-line-2 bg-jn-surface p-[22px]",
        "transition-[box-shadow,transform] duration-300 hover:-translate-y-[3px] hover:shadow-jn-hover",
        className,
      )}
    >
      {children}
    </div>
  );
}

const CHIP_TINT: Record<string, string> = {
  green: "bg-jn-green-bg text-jn-green",
  blue: "bg-jn-primary-soft text-jn-primary",
  violet: "bg-jn-violet-bg text-jn-violet",
  amber: "bg-jn-amber-bg text-jn-amber",
};

/* provider → brand colour + short initial for the crawl-sources rows */
const PROVIDER_STYLE: Record<string, { color: string; initial: string }> = {
  linkedin: { color: "#0A66C2", initial: "in" },
  indeed: { color: "#2557A7", initial: "I" },
  freelancer: { color: "#0E76A8", initial: "Fl" },
  remoteok: { color: "#E0533A", initial: "R" },
  remotive: { color: "#7C4DD0", initial: "Rm" },
  adzuna: { color: "#1F9E6E", initial: "Az" },
};
function providerStyle(key: string) {
  return (
    PROVIDER_STYLE[key.toLowerCase().replace(/\s+/g, "")] ?? {
      color: "#6B7079",
      initial: key.slice(0, 2),
    }
  );
}

/** Provider logo from the DB (Platform.logo_url); falls back to a brand
 *  monogram tile when there's no URL or the image fails to load. */
function ProviderLogo({ url, color, initial }: { url?: string; color: string; initial: string }) {
  const [failed, setFailed] = useState(false);
  if (url && !failed) {
    return (
      <span className="grid h-[30px] w-[30px] shrink-0 place-items-center overflow-hidden rounded-[9px] border border-jn-line-2 bg-white">
        <img
          src={url}
          alt=""
          loading="lazy"
          className="h-[18px] w-[18px] object-contain"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }
  return (
    <span
      className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px] text-[13px] font-bold text-white"
      style={{ background: color }}
    >
      {initial}
    </span>
  );
}

/* ── main ────────────────────────────────────────────────────────────── */

export interface MatchOverviewBentoProps {
  jobs: JobsOverview;
  staffing: StaffingDashboard;
}

export default function MatchOverviewBento({ jobs, staffing }: MatchOverviewBentoProps) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();

  const s = jobs.stats;
  const { kpi, action_queue } = staffing;

  const activePct = s.total > 0 ? (s.active / s.total) * 100 : 0;
  const topMatches = action_queue.top_new_matches;
  const providers = [...jobs.by_provider].sort((a, b) => b.count - a.count);
  const providerMax = Math.max(1, ...providers.map((p) => p.count));

  return (
    <div className="grid auto-rows-[minmax(150px,auto)] grid-cols-1 gap-[18px] md:grid-cols-2 xl:grid-cols-4">
      {/* HERO — AI matches today */}
      <div
        className="jn-reveal relative flex flex-col overflow-hidden rounded-[20px] p-[28px] text-white md:col-span-2 xl:row-span-2"
        style={{ background: "linear-gradient(135deg,#0a4fc4 0%,#5b34c0 56%,#7c3fb5 100%)" }}
      >
        <span className="pointer-events-none absolute -right-12 -top-14 h-[230px] w-[230px] rounded-full border border-white/15" />
        <span className="pointer-events-none absolute -right-2 -top-5 h-[150px] w-[150px] rounded-full border border-white/20" />
        <div className="relative flex items-center gap-2 text-[12.5px] font-semibold text-white/85">
          <IconSparkles size={16} />
          {t("matchOverview.heroEyebrow")}
        </div>
        <div className="relative mt-auto text-[64px] font-extrabold leading-none tracking-[-0.03em]">
          {fmt.format(s.suitable_today)}
        </div>
        <div className="relative mt-2.5 max-w-[330px] text-[15px] leading-relaxed text-white/90">
          {t("matchOverview.heroBody", { jobs: fmt.format(s.new_today), applied: fmt.format(s.applied) })}
        </div>
        <div className="relative mt-[22px] flex items-center gap-3.5">
          <button
            type="button"
            onClick={() => navigate("/admin/employees")}
            className="inline-flex items-center gap-2 rounded-[11px] bg-white px-[22px] py-3 text-[14px] font-semibold text-jn-ink transition-transform duration-200 hover:-translate-y-0.5"
          >
            {t("matchOverview.reviewMatches")}
            <IconArrowRight size={15} />
          </button>
          {topMatches.length > 0 && (
            <AvatarStack people={topMatches.slice(0, 3).map((m) => ({ name: m.full_name }))} size={34} />
          )}
        </div>
      </div>

      {/* Catalog */}
      <Tile>
        <div className="flex items-center gap-2.5">
          <span className={cn("grid h-[38px] w-[38px] place-items-center rounded-[11px]", CHIP_TINT.green)}>
            <IconStack2 size={20} />
          </span>
          {s.new_today > 0 && (
            <Badge color="green" className="ml-auto">
              +{fmt.format(s.new_today)}
            </Badge>
          )}
        </div>
        <div className="mt-3.5 text-[28px] font-extrabold tracking-[-0.02em] text-jn-ink">{fmt.format(s.total)}</div>
        <div className="mt-0.5 text-[12.5px] text-jn-ink-mute">{t("matchOverview.jobsInCatalog")}</div>
        <Sparkline data={jobs.per_day} color="#0E9CA6" />
      </Tile>

      {/* Active ring */}
      <Tile className="flex-row items-center gap-3.5">
        <Ring pct={activePct} color="#0064E5" />
        <div>
          <div className="text-[14px] font-bold text-jn-ink">{t("matchOverview.activeShare")}</div>
          <div className="mt-1 text-[12.5px] leading-relaxed text-jn-ink-mute">
            {t("matchOverview.activeShareHint", { active: fmt.format(s.active), total: fmt.format(s.total) })}
          </div>
        </div>
      </Tile>

      {/* Applications sent */}
      <Tile>
        <div className="flex items-center gap-2.5">
          <span className={cn("grid h-[38px] w-[38px] place-items-center rounded-[11px]", CHIP_TINT.blue)}>
            <IconSend size={19} />
          </span>
          {kpi.in_progress > 0 && (
            <Badge color="neutral" className="ml-auto">
              {t("matchOverview.inProgress", { count: kpi.in_progress })}
            </Badge>
          )}
        </div>
        <div className="mt-3.5 text-[28px] font-extrabold tracking-[-0.02em] text-jn-ink">{fmt.format(s.applied)}</div>
        <div className="mt-0.5 text-[12.5px] text-jn-ink-mute">{t("matchOverview.applicationsSent")}</div>
      </Tile>

      {/* Accepted this week */}
      <Tile>
        <div className="flex items-center gap-2.5">
          <span className={cn("grid h-[38px] w-[38px] place-items-center rounded-[11px]", CHIP_TINT.violet)}>
            <IconTrophy size={19} />
          </span>
          {kpi.lost_this_week > 0 && (
            <Badge color="neutral" className="ml-auto">
              {t("matchOverview.lost", { count: kpi.lost_this_week })}
            </Badge>
          )}
        </div>
        <div className="mt-3.5 text-[28px] font-extrabold tracking-[-0.02em] text-jn-ink">
          {fmt.format(kpi.won_this_week)}
        </div>
        <div className="mt-0.5 text-[12.5px] text-jn-ink-mute">{t("matchOverview.acceptedThisWeek")}</div>
      </Tile>

      {/* Top matches (wide) */}
      <Tile className="md:col-span-2">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[16px] font-bold text-jn-ink">{t("matchOverview.topMatchesTitle")}</div>
            <div className="mt-0.5 text-[12.5px] text-jn-muted">{t("matchOverview.topMatchesHint")}</div>
          </div>
          <button
            type="button"
            onClick={() => navigate("/admin/employees")}
            className="text-[13px] font-semibold text-jn-primary hover:underline"
          >
            {t("matchOverview.seeAll")}
          </button>
        </div>
        <div className="mt-2 flex flex-col">
          {topMatches.length === 0 && (
            <div className="py-8 text-center text-[13px] text-jn-muted">{t("matchOverview.noMatches")}</div>
          )}
          {topMatches.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => navigate(`/admin/employees/${m.id}`)}
              className="flex items-center gap-3.5 rounded-lg border-b border-jn-line-soft px-2 py-3 text-left transition-colors last:border-b-0 hover:bg-jn-sunken"
            >
              <Avatar name={m.full_name} size={40} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-semibold text-jn-ink">{m.full_name}</div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-jn-muted">
                  <IconArrowUpRight size={11} className="text-jn-faint" />
                  {t("matchOverview.newMatchesSub")}
                </div>
              </div>
              <Badge color="blue">{t("matchOverview.newCount", { count: m.new_count })}</Badge>
            </button>
          ))}
        </div>
      </Tile>

      {/* Crawl sources (wide) */}
      <Tile className="md:col-span-2">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[16px] font-bold text-jn-ink">{t("matchOverview.crawlSourcesTitle")}</div>
            <div className="mt-0.5 text-[12.5px] text-jn-muted">{t("matchOverview.crawlSourcesHint")}</div>
          </div>
          <Badge color="green" dot>
            {t("matchOverview.activeSources", { count: providers.length })}
          </Badge>
        </div>
        <div className="mt-1.5 flex flex-col">
          {providers.map((p) => {
            const ps = providerStyle(p.key);
            return (
              <div key={p.key} className="border-b border-jn-line-soft py-3 last:border-b-0">
                <div className="flex items-center gap-2.5">
                  <ProviderLogo url={p.logo_url} color={ps.color} initial={ps.initial} />
                  <span className="text-[13.5px] font-semibold text-jn-ink">{p.key}</span>
                  <span className="ml-auto text-[13.5px] font-extrabold tabular-nums text-jn-ink">
                    {fmt.format(p.count)}
                  </span>
                </div>
                <div className="ml-10 mt-2.5 h-1.5 overflow-hidden rounded bg-jn-bg">
                  <div
                    className="h-full rounded"
                    style={{ width: `${(p.count / providerMax) * 100}%`, background: ps.color }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-auto flex items-center gap-2 pt-4 text-[12.5px] text-jn-ink-mute">
          <IconStack2 size={15} className="text-[#0E9CA6]" />
          {t("matchOverview.jobsIndexed", { count: fmt.format(s.total) })}
        </div>
      </Tile>
    </div>
  );
}
