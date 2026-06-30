import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button as HButton } from "@heroui/button";
import { Tooltip } from "@heroui/tooltip";
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
} from "@heroui/modal";
import {
  IconArrowLeft,
  IconBriefcase,
  IconBuilding,
  IconCalendar,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconExternalLink,
  IconMail,
  IconMapPin,
  IconUser,
  IconUsers,
  IconX,
  IconBookmark,
  IconSparkles,
  IconCheck,
  IconLoader2,
  IconAlertTriangle,
  IconRefresh,
  IconShieldCheck,
} from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Button, useReveal } from "@/components/ui";
import { cn } from "@/lib/utils";
import { employeeService } from "@/services/employee.service";
import { jobService } from "@/services/job.service";
import { matchService } from "@/services/match.service";
import { mailService, type MailLog } from "@/services/mail.service";
import type { DuplicateApplyError, DuplicateApplyFrontman } from "@/services/match.service";
import type { Employee } from "@/types/employee.types";
import type { EmployeeJobMatch, JobLite, MatchStatus } from "@/types/match.types";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];
const PAGE_SIZE = 10;

// internal palette for the rich score breakdown (semantic, not brand)
const C = {
  success: "#1f9e6e", successBg: "#E7F6EF",
  warning: "#C77700", warningBg: "#FBF1DC",
  danger: "#E0533A", dangerBg: "#FCEDEA",
  blue: "#0064E5", blueBg: "#EEF2FB",
};

const STATUS_META: Record<MatchStatus, { key: string; bg: string; color: string }> = {
  suggested: { key: "suggested", bg: "#F2F3F5", color: "#5B6470" },
  pursuing: { key: "pursuing", bg: C.blueBg, color: C.blue },
  applied: { key: "applied", bg: "rgba(124,77,208,.12)", color: "#7C4DD0" },
  won: { key: "won", bg: C.successBg, color: C.success },
  in_progress: { key: "inProgress", bg: C.warningBg, color: C.warning },
  completed: { key: "completed", bg: C.successBg, color: C.success },
  lost: { key: "lost", bg: C.dangerBg, color: C.danger },
  dismissed: { key: "dismissed", bg: "#F2F3F5", color: "#A2A8B0" },
};

// source/platform brand dot colour
const SRC_COLOR: Record<string, string> = {
  freelancer: "#0E76A8", indeed: "#2557A7", linkedin: "#0A66C2",
  remoteok: "#E0533A", remotive: "#7C4DD0", adzuna: "#1F9E6E",
};
const srcColor = (name?: string) => SRC_COLOR[(name || "").toLowerCase().replace(/\s+/g, "")] ?? "#6B7079";

// Coloured on the rank-score scale (0–100, good dynamic range) — not the
// saturated calibrated probability.
const matchColor = (pct: number) => (pct >= 66 ? "#1F9E6E" : pct >= 40 ? "#0064E5" : "#C77700");

/** Headline number = rank score (reranker × gates): real dynamic range, gate
 *  penalties show through. Falls back to the calibrated P when no breakdown. */
function rankPct(m: EmployeeJobMatch): number {
  const r = m.score_breakdown?.rank_score;
  return Math.round((r != null ? r : (m.match_score ?? 0)) * 100);
}

function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function jobPostedLabel(j: JobLite, t: TFunction): string {
  const iso = j.date_posted || j.created_at;
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return t("posted.today");
  if (days === 1) return t("posted.dayAgo");
  if (days < 30) return t("posted.daysAgo", { count: days });
  return new Date(iso).toLocaleDateString("vi-VN", { dateStyle: "short" });
}

function sinceLabel(iso: string, t: TFunction): string {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return t("posted.today");
  if (m < 60) return t("job.minsAgo", { count: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t("job.hrsAgo", { count: h });
  const d = Math.floor(h / 24);
  if (d === 1) return t("posted.dayAgo");
  if (d < 30) return t("posted.daysAgo", { count: d });
  return new Date(iso).toLocaleDateString("vi-VN");
}

const SALARY_PERIOD_SUFFIX: Record<string, string> = {
  hourly: "/hr", daily: "/day", weekly: "/wk", monthly: "/mo", annual: "/yr",
};
function fmtSalary(j: JobLite): string {
  const c = j.salary_currency || "$";
  const k = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`);
  const suffix = j.salary_period ? (SALARY_PERIOD_SUFFIX[j.salary_period] ?? "") : "";
  if (j.salary_min && j.salary_max) return `${c}${k(j.salary_min)}–${c}${k(j.salary_max)}${suffix}`;
  if (j.salary_min) return `${c}${k(j.salary_min)}+${suffix}`;
  return "";
}

function seniorityGapLabel(gap: number | null, t: TFunction): string {
  if (gap === null || gap === undefined) return t("why.seniorityGap.unavailable");
  if (gap === 0) return t("why.seniorityGap.matches");
  if (gap > 0) return t("why.seniorityGap.jobHigher", { n: gap });
  return t("why.seniorityGap.employeeHigher", { n: -gap });
}

function StatusChip({ status }: { status: MatchStatus }) {
  const { t } = useTranslation("employees");
  const m = STATUS_META[status];
  return (
    <span className="rounded-jn-pill px-2.5 py-[3px] text-[12px] font-semibold" style={{ background: m.bg, color: m.color }}>
      {t(`matchStatus.${m.key}`)}
    </span>
  );
}

/* ── match ring ─────────────────────────────────────────────────────── */
function Ring({ pct, size = 80, stroke = 7, color }: { pct: number; size?: number; stroke?: number; color: string }) {
  const r = (size - stroke) / 2 - 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.max(0, Math.min(1, pct / 100)));
  const c = size / 2;
  const { t } = useTranslation("employees");
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={c} cy={c} r={r} fill="none" stroke="#EEF0F2" strokeWidth={stroke} />
        <circle
          cx={c} cy={c} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset .7s cubic-bezier(.2,.7,.2,1), stroke .3s" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[20px] font-extrabold leading-none" style={{ color }}>{pct}</span>
        <span className="text-[8.5px] font-bold tracking-[0.08em] text-jn-faint">{t("why.scoreShort").toUpperCase()}</span>
      </div>
    </div>
  );
}

/* ── left: job list card ────────────────────────────────────────────── */
function JobListItem({ match, selected, onSelect }: { match: EmployeeJobMatch; selected: boolean; onSelect: () => void }) {
  const { t } = useTranslation("employees");
  const j = match.job;
  const pct = rankPct(match);
  const mc = matchColor(pct);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "block w-full cursor-pointer rounded-[14px] border-[1.5px] p-[15px] text-left transition-[background,border-color,box-shadow] duration-200",
        selected
          ? "border-[#0064E5] bg-[#F5F9FF] shadow-[0_8px_22px_rgba(0,100,229,.12)]"
          : "border-jn-line-2 bg-jn-surface hover:border-[#C9D8F5] hover:shadow-[0_6px_18px_rgba(20,20,40,.06)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-[14.5px] font-bold leading-[1.3] text-jn-ink">{j.title}</span>
        <span className="flex shrink-0 items-center gap-1.5">
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: mc }} />
          <span className="text-[13.5px] font-extrabold" style={{ color: mc }}>{pct}</span>
        </span>
      </div>
      <div className="mt-[5px] text-[12px] text-jn-muted">
        {j.company_name || "—"}{j.location ? ` · ${j.location}` : ""}
      </div>
      <div className="mt-[11px] flex items-center justify-between">
        <div className="flex items-center gap-[7px]">
          {j.platform_name && (
            <span className="flex items-center gap-[5px] rounded-jn-pill bg-[#F2F3F5] px-[9px] py-1 text-[11px] font-semibold text-jn-ink-soft">
              <span className="h-[7px] w-[7px] rounded-[3px]" style={{ background: srcColor(j.platform_name) }} />
              {j.platform_name}
            </span>
          )}
          {j.job_type && <span className="text-[11px] text-jn-faint">{j.job_type}</span>}
        </div>
        {jobPostedLabel(j, t) && <span className="text-[11px] text-jn-faint">{jobPostedLabel(j, t)}</span>}
      </div>
    </button>
  );
}

/* ── score-breakdown helpers (rich detail kept) ─────────────────────── */
const DIM_LABEL_KEYS: Record<string, string> = {
  skill_fit: "why.dim.skillFit", experience_fit: "why.dim.experienceFit",
  seniority_fit: "why.dim.seniorityFit", domain_fit: "why.dim.domainFit",
};
const DIM_ORDER = ["skill_fit", "experience_fit", "seniority_fit", "domain_fit"];
function dimNum(raw: number | string): number {
  if (typeof raw === "number") return raw;
  return ({ good: 1, ok: 0.6, weak: 0.3 } as Record<string, number>)[raw] ?? 0;
}
function dimTone(v: number): string {
  return v >= 0.7 ? C.success : v >= 0.4 ? C.warning : C.danger;
}
function ScoreBar({ label, value, hint, tone = C.blue }: { label: string; value: number; hint?: string; tone?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[12.5px] font-semibold text-jn-ink-soft">{label}</span>
        <span className="text-[12.5px] font-bold" style={{ color: tone }}>{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-jn-pill bg-jn-sunken">
        <div className="h-full rounded-jn-pill" style={{ width: `${pct}%`, background: tone }} />
      </div>
      {hint && <div className="mt-1 text-[11.5px] text-jn-faint">{hint}</div>}
    </div>
  );
}

function ScoreBreakdown({ match }: { match: EmployeeJobMatch }) {
  const { t } = useTranslation("employees");
  const matched = match.matched_skills?.length ?? 0;
  const missing = match.missing_skills?.length ?? 0;
  const reqTotal = matched + missing;
  const skillCoverage = reqTotal ? matched / reqTotal : 1;
  const gap = match.seniority_gap;
  const seniorityFit = gap == null ? 0.5 : Math.max(0, 1 - Math.abs(gap) * 0.3);
  const overall = match.match_score || 0;
  const covered = match.covered_skills ?? {};
  const trulyMissing = (match.missing_skills ?? []).filter((s) => !(s in covered));

  const rankS = match.score_breakdown?.rank_score ?? overall;
  // Ẩn thanh điểm tổng (Điểm phù hợp / Xác suất hiệu chuẩn) + khối
  // "Điểm được tính thế nào". Đổi thành true để hiện lại.
  const SHOW_SCORE_FORMULA = false;
  return (
    <div className="mt-3">
      {/* headline = rank score (reranker × gates); P kept as the eligibility gate */}
      {SHOW_SCORE_FORMULA && <ScoreBar label={t("why.matchScore")} value={rankS} tone="#0064E5" />}
      {SHOW_SCORE_FORMULA && <ScoreBar label={t("why.calibratedProbability")} value={overall} tone="#9097a0" />}
      {Object.keys(match.dim_scores ?? {}).length > 0 ? (
        <>
          <div className="mb-2 mt-3.5 flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-[0.05em] text-jn-faint">{t("why.rerankerDiagnostics")}</span>
            <span className="h-px flex-1 bg-jn-line-soft" />
          </div>
          <div className="mb-1.5 text-[11.5px] leading-relaxed text-jn-faint">{t("why.diagnosticsHint")}</div>
          {DIM_ORDER.filter((k) => match.dim_scores?.[k] != null).map((k) => {
            const v = dimNum(match.dim_scores![k]);
            return <ScoreBar key={k} label={DIM_LABEL_KEYS[k] ? t(DIM_LABEL_KEYS[k]) : k} value={v} tone={dimTone(v)} />;
          })}
        </>
      ) : (
        <>
          <ScoreBar label={t("why.skillCoverage")} value={skillCoverage} tone={C.success}
            hint={t("why.skillCoverageHint", { matched, total: reqTotal || matched })} />
          <ScoreBar label={t("why.seniorityFit")} value={seniorityFit} tone={C.warning} hint={seniorityGapLabel(gap, t)} />
          <div className="mb-2 text-[11.5px] text-jn-faint">{t("why.refreshHint")}</div>
        </>
      )}

      {/* provenance — ẩn ("Điểm được tính thế nào") */}
      {SHOW_SCORE_FORMULA && (() => {
        const bd = match.score_breakdown;
        if (!bd || !bd.stage1 || !Object.keys(bd.stage1).length) return null;
        const w = bd.weights ?? {};
        const s1 = bd.stage1 ?? {};
        const COMP_LABELS: Record<string, string> = { gnn: "GNN", skill: "Skill", seniority: "Seniority", domain: "Domain" };
        const gateLabels: Record<string, string> = {
          domain: t("why.compute.gateLabel.domain"), experience: t("why.compute.gateLabel.experience"), seniority: t("why.compute.gateLabel.seniority"),
        };
        const firedGates = Object.entries(bd.gates ?? {}).filter(([, v]) => v != null) as [string, number][];
        return (
          <div className="mb-3 mt-1 rounded-[10px] border border-dashed border-jn-line-3 bg-jn-surface px-3 py-2.5">
            <div className="mb-1.5 text-[11.5px] font-bold uppercase tracking-[0.04em] text-jn-muted">{t("why.compute.title")}</div>
            <div className="font-mono text-[12px] leading-[1.7] text-jn-ink-soft">
              <div>
                <span className="text-jn-muted">{t("why.compute.stage1")}&nbsp;&nbsp;</span>
                {(["gnn", "skill", "seniority", "domain"] as const).filter((k) => s1[k] != null && w[k] != null).map((k, i) => (
                  <span key={k}>{i > 0 && " + "}{w[k]}×{COMP_LABELS[k]}({s1[k]})</span>
                ))}
                {s1.stage1 != null && <span className="font-bold"> = {s1.stage1}</span>}
              </div>
              {bd.reranker != null && (
                <div><span className="text-jn-muted">{t("why.compute.stage2")}&nbsp;</span>{bd.reranker} <span className="text-jn-faint">{t("why.compute.stage2Note")}</span></div>
              )}
              <div>
                <span className="text-jn-muted">{t("why.compute.gates")}&nbsp;&nbsp;&nbsp;</span>
                {firedGates.length ? firedGates.map(([k, v]) => `${gateLabels[k] ?? k} ×${v}`).join(" · ") : t("why.compute.noGates")}
              </div>
              {bd.calibrated != null && bd.rank_score != null && (
                <div>
                  <span className="text-jn-muted">{t("why.compute.calibration")}&nbsp;&nbsp;</span>
                  rank {bd.rank_score} → <span className="font-bold">P = {bd.calibrated}</span>
                  <span className="text-jn-faint"> {t("why.compute.display")}</span>
                </div>
              )}
            </div>
            <div className="mt-1.5 text-[11px] leading-[1.5] text-jn-faint">{t("why.compute.footnote")}</div>
          </div>
        );
      })()}

      {/* missing skills */}
      <div className="mt-1">
        <div className="mb-1 text-[12px] text-jn-muted">{t("why.missingSkills")}</div>
        <div className="flex flex-wrap gap-1.5">
          {trulyMissing.map((s) => (
            <span key={s} className="rounded-jn-pill px-2.5 py-0.5 text-[11.5px] font-medium" style={{ background: C.dangerBg, color: C.danger }}>{s}</span>
          ))}
          {!trulyMissing.length && <span className="text-[12px]" style={{ color: C.success }}>{t("why.meetsAll")}</span>}
        </div>
      </div>
    </div>
  );
}

/* ── right: job detail panel ────────────────────────────────────────── */
function JobDetailPanel({
  match, onApply, onDismiss,
}: {
  match: EmployeeJobMatch;
  onApply: (m: EmployeeJobMatch) => void;
  onDismiss: (m: EmployeeJobMatch) => void;
}) {
  const { t } = useTranslation("employees");
  const j = match.job;
  const salary = fmtSalary(j);
  const pct = rankPct(match);
  const mc = matchColor(pct);
  const [desc, setDesc] = useState<string | null>(null);
  const [descLoading, setDescLoading] = useState(true);
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [thread, setThread] = useState<MailLog[]>([]);
  // On-demand verify — local override so we don't refetch the whole match.
  const [verifying, setVerifying] = useState(false);
  const [verifyInfo, setVerifyInfo] = useState<{ is_active: boolean; last_verified_at: string | null } | null>(null);
  const isActive = verifyInfo ? verifyInfo.is_active : j.is_active;
  const lastVerified = verifyInfo ? verifyInfo.last_verified_at : j.last_verified_at;

  const doVerify = async () => {
    setVerifying(true);
    try {
      const r = await jobService.verifyJob(j.id);
      setVerifyInfo({ is_active: r.is_active, last_verified_at: r.last_verified_at });
      addToast({ title: r.is_active ? t("job.verifyActive") : t("job.verifyClosed"), color: r.is_active ? "success" : "default" });
    } catch {
      addToast({ title: t("job.verifyFailed"), color: "danger" });
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => { setVerifyInfo(null); }, [j.id]);
  useEffect(() => { mailService.thread(match.id).then(setThread).catch(() => setThread([])); }, [match.id]);
  useEffect(() => {
    let alive = true;
    setDescLoading(true); setDesc(null);
    jobService.getJob(j.id).then((d) => { if (alive) setDesc(d.description || ""); })
      .catch(() => { if (alive) setDesc(""); }).finally(() => { if (alive) setDescLoading(false); });
    return () => { alive = false; };
  }, [j.id]);

  const tracked = match.status === "applied" || match.status === "won" || match.status === "lost";

  // matched + near-miss skills for the green panel
  const covered = match.covered_skills ?? {};
  const matchedList = match.matched_skills ?? [];
  const nearMisses = (match.missing_skills ?? []).filter((s) => s in covered);
  const whyText = `${t("why.skillCoverageHint", { matched: matchedList.length, total: matchedList.length + (match.missing_skills?.length ?? 0) })}. ${seniorityGapLabel(match.seniority_gap, t)}.`;

  return (
    <div className="p-[30px]">
      {/* header */}
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <h1 className="m-0 text-[25px] font-extrabold leading-[1.2] tracking-[-0.02em] text-jn-ink">{j.title}</h1>
          <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-2">
            {j.company_name && <Meta icon={<IconBuilding size={15} />}>{j.company_name}</Meta>}
            {j.location && <Meta icon={<IconMapPin size={15} />}>{j.location}</Meta>}
            {j.seniority != null && <Meta icon={<IconBriefcase size={15} />}>{SENIORITY_LABELS[j.seniority] ?? j.seniority}</Meta>}
            {j.applicant_count && <Meta icon={<IconUsers size={15} />}>{t("job.applicants", { count: j.applicant_count })}</Meta>}
            {j.date_posted && <Meta icon={<IconCalendar size={15} />}>{new Date(j.date_posted).toLocaleDateString("vi-VN")}</Meta>}
          </div>
        </div>
        <Ring pct={pct} color={mc} />
      </div>

      {/* chips */}
      <div className="mt-[18px] flex flex-wrap items-center gap-2.5">
        {salary && <span className="rounded-jn-pill px-[13px] py-1.5 text-[12.5px] font-bold" style={{ background: C.successBg, color: C.success }}>{salary}</span>}
        {j.job_type && <span className="rounded-jn-pill bg-[#F2F3F5] px-[13px] py-1.5 text-[12.5px] font-semibold text-jn-ink-soft">{j.job_type}</span>}
        <span className="flex items-center gap-1.5 rounded-jn-pill px-[13px] py-1.5 text-[12.5px] font-semibold"
          style={{ background: isActive ? C.successBg : "#F2F3F5", color: isActive ? C.success : "#A2A8B0" }}>
          {isActive && <span className="h-1.5 w-1.5 rounded-full" style={{ background: C.success }} />}
          {isActive ? t("job.active") : t("job.closed")}
        </span>

        {/* last verify + on-demand verify */}
        <span className="flex items-center gap-1.5 text-[12px] text-jn-muted">
          <IconShieldCheck size={14} className="text-jn-faint" />
          {lastVerified ? t("job.lastVerified", { time: sinceLabel(lastVerified, t) }) : t("job.neverVerified")}
        </span>
        <button
          type="button"
          onClick={doVerify}
          disabled={verifying}
          className="flex items-center gap-1.5 rounded-jn-pill border border-jn-line-3 bg-jn-surface px-3 py-1 text-[12px] font-semibold text-jn-ink-soft transition-colors hover:bg-jn-sunken disabled:opacity-60"
        >
          {verifying ? <IconLoader2 size={13} className="animate-spin" /> : <IconRefresh size={13} />}
          {verifying ? t("job.verifying") : t("job.verifyNow")}
        </button>
      </div>

      {/* actions */}
      <div className="mt-[22px] flex flex-wrap items-center gap-3">
        {tracked ? (
          <>
            <StatusChip status={match.status} />
            <span className="text-[12.5px] text-jn-ink-mute">{t("job.inJobTracking")}</span>
          </>
        ) : (
          <>
            <Button variant="primary" size="md" leftIcon={<IconExternalLink size={16} />} onClick={() => onApply(match)}>
              {t("job.apply")}
            </Button>
            <button
              type="button"
              onClick={() => onDismiss(match)}
              className="flex items-center gap-2 rounded-[11px] border border-jn-line-3 bg-jn-surface px-5 py-3 text-[14px] font-semibold text-jn-ink-mute transition-colors hover:bg-[#FCEDEA] hover:text-[#E0533A]"
            >
              <IconX size={16} />
              {t("job.dismiss")}
            </button>
            <button
              type="button"
              className="flex items-center rounded-[11px] border border-jn-line-3 bg-jn-surface p-3 text-jn-ink-mute transition-colors hover:bg-jn-sunken"
              aria-label="Bookmark"
            >
              <IconBookmark size={16} />
            </button>
          </>
        )}
        {j.source_url && (
          <a href={j.source_url} target="_blank" rel="noreferrer"
            className="ml-1 flex items-center gap-1.5 text-[13px] font-semibold text-jn-primary hover:underline">
            {t("job.viewOriginal")} <IconExternalLink size={14} />
          </a>
        )}
      </div>

      {/* WHY IT MATCHES */}
      <div className="mt-6 rounded-[14px] border border-[#D5EFE2] p-[18px]" style={{ background: "linear-gradient(180deg,#F3FBF7,#FAFEFC)" }}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="grid h-7 w-7 place-items-center rounded-[9px] text-white" style={{ background: C.success }}>
              <IconSparkles size={15} />
            </span>
            <span className="text-[12.5px] font-bold tracking-[0.03em] text-jn-ink">{t("why.title").toUpperCase()}</span>
          </div>
          <span className="flex items-baseline gap-1.5">
            <span className="text-[10.5px] font-bold uppercase tracking-[0.04em]" style={{ color: "#1F8A5B" }}>{t("why.matchScore")}</span>
            <span className="text-[15px] font-extrabold" style={{ color: C.success }}>{pct}</span>
          </span>
        </div>
        <div className="mt-3 text-[13px] leading-[1.6] text-jn-ink-soft">{whyText}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {matchedList.map((s) => (
            <span key={s} className="flex items-center gap-1.5 rounded-jn-pill border border-[#CFEBDD] bg-white px-[11px] py-[5px] text-[12px] font-semibold" style={{ color: "#1F8A5B" }}>
              <IconCheck size={13} style={{ color: C.success }} />{s}
            </span>
          ))}
          {nearMisses.map((s) => (
            <Tooltip key={s} placement="top" delay={0} closeDelay={50}
              content={<div className="max-w-[240px] p-0.5 text-[12px] leading-[1.5]">
                <Trans i18nKey="why.nearMissTooltip" t={t} values={{ skill: s, covered: covered[s] }} components={[<b key="0" />, <b key="1" />]} />
              </div>}>
              <span className="flex cursor-help items-center gap-1 rounded-jn-pill border border-[#F3E4C2] bg-white px-[11px] py-[5px] text-[12px] font-semibold" style={{ color: C.warning }}>
                {s} <span className="opacity-70">≈ {covered[s]}</span>
              </span>
            </Tooltip>
          ))}
          {!matchedList.length && !nearMisses.length && <span className="text-[12px] text-jn-faint">{t("why.none")}</span>}
        </div>

        {/* score details toggle */}
        <button
          type="button"
          onClick={() => setBreakdownOpen((o) => !o)}
          className="mt-3 flex items-center gap-1.5 text-[12px] font-semibold text-jn-primary"
        >
          {breakdownOpen ? t("why.hideBreakdown") : t("why.scoreBreakdown")}
          <IconChevronDown size={14} className={cn("transition-transform", breakdownOpen && "rotate-180")} />
        </button>
        {breakdownOpen && <ScoreBreakdown match={match} />}
      </div>

      {/* job description */}
      <div className="mt-6">
        <div className="mb-3 text-[12.5px] font-bold uppercase tracking-[0.04em] text-jn-muted">{t("job.description")}</div>
        {descLoading ? (
          <div className="text-[13px] text-jn-faint">{t("job.loadingDescription")}</div>
        ) : desc ? (
          <div className="whitespace-pre-line text-[14px] leading-[1.7] text-jn-ink-soft">{desc}</div>
        ) : (
          <div className="text-[13px] text-jn-faint">{t("job.noDescription")}</div>
        )}
      </div>

      {/* mail thread */}
      {thread.length > 0 && (
        <div className="mt-6">
          <div className="mb-3 text-[12.5px] font-bold uppercase tracking-[0.04em] text-jn-muted">{t("job.emailThread")}</div>
          <div className="flex flex-col gap-2">
            {thread.map((e) => (
              <div key={e.id} className="rounded-[10px] px-3 py-2.5"
                style={{ border: `1px solid ${e.is_bounce ? C.danger : "#EFEFF1"}`, background: e.direction === "in" ? C.blueBg : "#fff" }}>
                <div className="mb-1 text-[11.5px] text-jn-faint">
                  {e.direction === "out" ? t("job.sentTo", { addr: e.to_addr }) : t("job.replyFrom", { addr: e.from_addr })}
                  {e.is_bounce && <span className="font-bold" style={{ color: C.danger }}> · {t("job.deliveryFailed")}</span>}
                  {e.cv_attached && <span style={{ color: C.success }}> · {t("job.cvAttached")}</span>}
                  <span className="ml-2">{new Date(e.created_at).toLocaleString("vi-VN")}</span>
                </div>
                <div className="text-[13px] font-semibold text-jn-ink-soft">{e.subject}</div>
                <div className="mt-1 whitespace-pre-line text-[12.5px] leading-[1.5] text-jn-ink-soft">{e.body_text}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Meta({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <span className="flex items-center gap-1.5 text-[13px]" style={{ color: "#5B6470" }}>
      <span className="flex text-jn-muted">{icon}</span>
      {children}
    </span>
  );
}

/* ── waiting state: CV is being parsed + ranked in the background ────── */
function StepIcon({ state }: { state: "done" | "active" | "pending" }) {
  if (state === "done")
    return <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full bg-jn-green-bg" style={{ color: C.success }}><IconCheck size={13} /></span>;
  if (state === "active")
    return <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full bg-jn-primary-soft text-jn-primary"><IconLoader2 size={13} className="animate-spin" /></span>;
  return <span className="h-[22px] w-[22px] shrink-0 rounded-full border-[1.5px] border-jn-line-3" />;
}

function RankingState({ employee, phase }: { employee: Employee; phase: "parsing" | "ranking" }) {
  const { t } = useTranslation("employees");
  const first = (employee.full_name || "").trim().split(/\s+/)[0] || employee.full_name;
  const skills = employee.skills ?? [];
  type S = "done" | "active" | "pending";
  // In the ranking phase, parse + skill extraction are done and ranking is active.
  const steps: { key: string; label: string; state: S }[] =
    phase === "ranking"
      ? [
          { key: "uploaded", label: t("ranking.stepUploaded"), state: "done" },
          { key: "parsing", label: t("ranking.stepParsing"), state: "done" },
          { key: "skills", label: t("ranking.stepSkills"), state: "done" },
          { key: "ranking", label: t("ranking.stepRanking"), state: "active" },
        ]
      : [
          { key: "uploaded", label: t("ranking.stepUploaded"), state: "done" },
          { key: "parsing", label: t("ranking.stepParsing"), state: "active" },
          { key: "skills", label: t("ranking.stepSkills"), state: skills.length ? "done" : "pending" },
          { key: "ranking", label: t("ranking.stepRanking"), state: "pending" },
        ];
  return (
    <div className="overflow-hidden rounded-jn-card border border-jn-line bg-jn-surface">
      <style>{`
        @keyframes jnIndeterminate { 0%{left:-40%} 100%{left:100%} }
        @keyframes jnPulseRing { 0%,100%{transform:scale(1);opacity:.45} 50%{transform:scale(1.14);opacity:.85} }
      `}</style>
      {/* gradient hero */}
      <div
        className="relative flex flex-col items-center overflow-hidden px-8 py-12 text-center text-white"
        style={{ background: "linear-gradient(135deg,#0a4fc4 0%,#5b34c0 56%,#7c3fb5 100%)" }}
      >
        <span className="pointer-events-none absolute h-[210px] w-[210px] rounded-full border border-white/25" style={{ animation: "jnPulseRing 5s ease-in-out infinite" }} />
        <span className="pointer-events-none absolute h-[140px] w-[140px] rounded-full border border-white/30" style={{ animation: "jnPulseRing 5s ease-in-out infinite .6s" }} />
        <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-white/15">
          <IconSparkles size={30} className="animate-pulse" />
        </span>
        <div className="relative mt-5 text-[22px] font-extrabold tracking-[-0.02em]">{t("ranking.title", { name: first })}</div>
        <div className="relative mt-2 max-w-[460px] text-[14px] leading-relaxed text-white/85">{t(phase === "ranking" ? "ranking.subtitleRanking" : "ranking.subtitle")}</div>
        <div className="relative mt-6 h-1.5 w-full max-w-[420px] overflow-hidden rounded-full bg-white/20">
          <span className="absolute top-0 h-full w-[40%] rounded-full bg-white" style={{ animation: "jnIndeterminate 1.4s ease-in-out infinite" }} />
        </div>
      </div>
      {/* steps */}
      <div className="flex flex-col gap-3.5 px-8 py-7">
        {steps.map((s) => (
          <div key={s.key} className="flex items-center gap-3">
            <StepIcon state={s.state} />
            <span className={cn("text-[14px]", s.state === "pending" ? "text-jn-muted" : s.state === "active" ? "font-semibold text-jn-ink" : "text-jn-ink-soft")}>{s.label}</span>
          </div>
        ))}
        {skills.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {skills.slice(0, 10).map((s) => (
              <span key={s} className="rounded-jn-pill bg-jn-sunken px-2.5 py-1 text-[11.5px] font-medium text-jn-ink-soft">{s}</span>
            ))}
          </div>
        )}
        <div className="mt-1 flex items-center gap-2 text-[12.5px] text-jn-muted">
          <IconLoader2 size={14} className="animate-spin" />
          {t("ranking.autoRefresh")}
        </div>
      </div>
    </div>
  );
}

function ParseFailedState({ onSettings }: { onSettings: () => void }) {
  const { t } = useTranslation("employees");
  return (
    <div className="flex flex-col items-center gap-3 rounded-jn-card border border-jn-line bg-jn-surface px-8 py-14 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl" style={{ background: C.dangerBg, color: C.danger }}>
        <IconAlertTriangle size={26} />
      </span>
      <div className="text-[16px] font-bold text-jn-ink">{t("ranking.failedTitle")}</div>
      <div className="max-w-[400px] text-[13px] text-jn-muted">{t("ranking.failedHint")}</div>
      <Button variant="secondary" className="mt-1" leftIcon={<IconUser size={15} className="text-jn-ink-mute" />} onClick={onSettings}>
        {t("ranking.openSettings")}
      </Button>
    </div>
  );
}

/* ============================ page ============================ */
export default function EmployeeDetailPage() {
  const { t } = useTranslation("employees");
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const wantMatch = Number(searchParams.get("match")) || null;
  const empId = Number(id);
  const navigate = useNavigate();

  const [employee, setEmployee] = useState<Employee | null>(null);
  const [matches, setMatches] = useState<EmployeeJobMatch[]>([]);
  // Re-scan reveals when the page content mounts after the async load.
  const reveal = useReveal([employee, matches]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<"score" | "newest">("score");
  const [platformFilter, setPlatformFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dup, setDup] = useState<{ match: EmployeeJobMatch; frontman: DuplicateApplyFrontman } | null>(null);
  const [applyTarget, setApplyTarget] = useState<EmployeeJobMatch | null>(null);

  const listParams = useCallback(
    (pg: number) => ({
      employee: empId,
      ...(platformFilter ? { platform: platformFilter } : {}),
      hide_applied: true,
      ordering: sortBy === "newest" ? "-job__created_at" : "-match_score",
      page: pg, page_size: PAGE_SIZE,
    }),
    [empId, sortBy, platformFilter],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [emp, m] = await Promise.all([employeeService.get(empId), matchService.list(listParams(1))]);
      setEmployee(emp);
      setMatches(m.results);
      setTotal(m.count ?? m.results.length);
      setPage(1);
    } catch {
      addToast({ title: t("detail.loadFailed"), color: "danger" });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empId, listParams]);

  useEffect(() => { void reload(); }, [reload]);

  // Background work has two phases the UI should wait through:
  //  1. parsing — CV not parsed yet (parsed_at null).
  //  2. ranking — parsed, but the GNN re-match hasn't persisted matches yet.
  //     The backend sets parsed_at BEFORE running the (slow) ranking, so a
  //     parsed employee with zero matches is almost always still ranking.
  // Genuinely-empty employees are rare, so we treat "parsed + 0 matches" as
  // ranking for a bounded window, then fall back to the real empty state.
  const parsing = !!employee && !employee.parsed_at && !employee.is_parse_failed;
  const parsedNoMatches = !!employee && !!employee.parsed_at && !employee.is_parse_failed && matches.length === 0;
  const [rankingExpired, setRankingExpired] = useState(false);
  const ranking = parsedNoMatches && !rankingExpired;
  const working = parsing || ranking;

  // Bound the ranking window so a truly-empty employee doesn't spin forever.
  useEffect(() => {
    if (!parsedNoMatches) { setRankingExpired(false); return; }
    const tmo = setTimeout(() => setRankingExpired(true), 40_000);
    return () => clearTimeout(tmo);
  }, [parsedNoMatches]);

  // Poll while either phase is active so the page flips to the browser
  // automatically once matches land.
  useEffect(() => {
    if (!working) return;
    const idv = setInterval(() => { void reload(); }, 3000);
    return () => clearInterval(idv);
  }, [working, reload]);

  const goToPage = useCallback(async (p: number) => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const m = await matchService.list(listParams(p));
      setMatches(m.results);
      setTotal(m.count ?? 0);
      setPage(p);
    } catch {
      addToast({ title: t("detail.loadMoreFailed"), color: "danger" });
    } finally {
      setLoadingMore(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMore, listParams]);

  useEffect(() => {
    if (!matches.length) return;
    if (wantMatch && matches.some((m) => m.id === wantMatch)) {
      if (selectedId !== wantMatch) setSelectedId(wantMatch);
      return;
    }
    if (!matches.some((m) => m.id === selectedId)) setSelectedId(matches[0].id);
  }, [matches, selectedId, wantMatch]);

  const selected = matches.find((m) => m.id === selectedId) || null;

  const applyToJob = async (match: EmployeeJobMatch, confirmDuplicate = false) => {
    try {
      await matchService.update(match.id, { status: "applied", confirm_duplicate: confirmDuplicate });
      setDup(null); setApplyTarget(null);
      addToast({ title: t("toast.applied"), color: "success" });
      if (match.job.source_url) window.open(match.job.source_url, "_blank", "noopener,noreferrer");
      await reload();
    } catch (e: unknown) {
      const resp = (e as { response?: { status?: number; data?: { error?: DuplicateApplyError } } }).response;
      if (resp?.status === 409 && resp.data?.error?.code === "DUPLICATE_APPLY") {
        setApplyTarget(null);
        setDup({ match, frontman: resp.data.error.frontman });
        return;
      }
      addToast({ title: t("toast.applyFailed"), color: "danger" });
    }
  };

  const goWriteEmail = (match: EmployeeJobMatch) => {
    setApplyTarget(null);
    navigate(`/admin/apply-email?employee=${empId}&job=${match.job.id}&match=${match.id}`);
  };

  const dismissMatch = async (match: EmployeeJobMatch) => {
    try {
      await matchService.update(match.id, { status: "dismissed" });
      addToast({ title: t("toast.dismissed"), description: t("toast.dismissedDesc"), color: "default" });
      await reload();
    } catch {
      addToast({ title: t("toast.updateFailed"), color: "danger" });
    }
  };

  if (loading && !employee) return <div className="p-10 text-jn-ink-mute">{t("detail.loading")}</div>;
  if (!employee) return <div className="p-10 text-jn-ink-mute">{t("detail.notFound")}</div>;

  const skillsLine = (employee.skills ?? []).slice(0, 4).join(", ");
  const platforms = employee.matches_count_by_platform?.filter((p) => p.slug) ?? [];

  return (
    <div ref={reveal} className="flex min-h-0 flex-col">
      {/* candidate context */}
      <div className="jn-reveal mb-[18px] flex items-center gap-3.5">
        <button type="button" onClick={() => navigate("/admin/employees")}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-jn-btn text-jn-ink-mute transition-colors hover:bg-jn-sunken" aria-label="Back">
          <IconArrowLeft size={18} />
        </button>
        <span className="grid h-[50px] w-[50px] shrink-0 place-items-center rounded-[13px] text-[16px] font-bold" style={{ background: C.blueBg, color: C.blue }}>
          {initials(employee.full_name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[18px] font-bold tracking-[-0.01em] text-jn-ink">{employee.full_name}</div>
          <div className="mt-[3px] truncate text-[13px] text-jn-muted">
            {employee.position || "—"} · {SENIORITY_LABELS[employee.seniority] ?? employee.seniority}
            {employee.experience_years != null && ` · ${t("detail.expYears", { years: employee.experience_years })}`}
            {skillsLine && ` · ${skillsLine}`}
          </div>
        </div>
        <Button variant="secondary" leftIcon={<IconUser size={16} className="text-jn-ink-mute" />} onClick={() => navigate(`/admin/employees/${empId}/info`)}>
          {t("detail.viewDetail")}
        </Button>
      </div>

      {working ? (
        <RankingState employee={employee} phase={parsing ? "parsing" : "ranking"} />
      ) : employee.is_parse_failed && matches.length === 0 ? (
        <ParseFailedState onSettings={() => navigate(`/admin/employees/${empId}/info`)} />
      ) : (
        <>
      {/* filter row */}
      <div className="jn-reveal mb-4 flex flex-wrap items-center gap-3">
        {platforms.length > 1 && (
          <>
            <span className="text-[13px] font-medium text-jn-muted">{t("detail.platformLabel")}</span>
            <div className="flex flex-wrap gap-2">
              <PlatformPill active={platformFilter === ""} onClick={() => setPlatformFilter("")}>{t("detail.platformAll")}</PlatformPill>
              {platforms.map((p) => (
                <PlatformPill key={p.slug} active={platformFilter === p.slug} onClick={() => setPlatformFilter((prev) => (prev === p.slug ? "" : p.slug))}>
                  {p.logo && <img src={p.logo} alt="" width={15} height={15} className="rounded-[3px] object-contain" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />}
                  {p.name} <span className="font-bold opacity-70">{p.count}</span>
                </PlatformPill>
              ))}
            </div>
          </>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[13px] text-jn-muted">{t("detail.sortLabel")}</span>
          <div className="flex rounded-jn-pill bg-jn-sunken p-[3px]">
            {([["score", t("detail.sortScore")], ["newest", t("detail.sortNewest")]] as const).map(([key, label]) => (
              <button key={key} type="button" onClick={() => setSortBy(key)}
                className={cn(
                  "rounded-[18px] px-3.5 py-1.5 text-[13px] font-semibold transition-all",
                  sortBy === key ? "border border-jn-line-2 bg-white text-jn-primary" : "border border-transparent text-jn-muted hover:text-jn-ink-soft",
                )}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* two columns */}
      {matches.length === 0 ? (
        <div className="grid h-[240px] place-items-center rounded-jn-card border border-jn-line bg-jn-surface text-center text-jn-ink-mute">
          <div>
            <IconBriefcase size={30} className="mx-auto mb-2.5 text-jn-faint" />
            <div className="font-semibold text-jn-ink">{t("detail.emptyAllTitle")}</div>
            <div className="text-[13px] text-jn-muted">{t("detail.emptyAllHint")}</div>
          </div>
        </div>
      ) : (
        <div className="jn-reveal grid items-start gap-[18px]" style={{ gridTemplateColumns: "380px 1fr", height: "calc(100vh - 250px)" }}>
          {/* left list */}
          <div className="flex h-full min-h-0 flex-col gap-[11px] overflow-y-auto pr-1.5">
            {matches.map((m) => (
              <JobListItem key={m.id} match={m} selected={m.id === selectedId} onSelect={() => setSelectedId(m.id)} />
            ))}
            {total > PAGE_SIZE && (() => {
              const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
              const WINDOW = 5;
              let start = Math.max(1, page - Math.floor(WINDOW / 2));
              const end = Math.min(totalPages, start + WINDOW - 1);
              start = Math.max(1, end - WINDOW + 1);
              const nums: number[] = [];
              for (let i = start; i <= end; i++) nums.push(i);
              const numBtn = (p: number) => {
                const active = p === page;
                return (
                  <button key={p} type="button" disabled={loadingMore || active} onClick={() => void goToPage(p)}
                    className={cn("h-7 min-w-7 rounded-lg px-1.5 text-[12.5px] font-semibold tabular-nums",
                      active ? "border border-jn-primary bg-jn-primary text-white" : "border border-jn-line-2 bg-jn-surface text-jn-ink-soft hover:bg-jn-sunken")}>
                    {p}
                  </button>
                );
              };
              const arrow = (dir: -1 | 1, disabled: boolean) => (
                <button type="button" disabled={disabled || loadingMore} onClick={() => void goToPage(page + dir)} aria-label={dir < 0 ? "Prev" : "Next"}
                  className="grid h-7 w-7 place-items-center rounded-lg border border-jn-line-2 bg-jn-surface text-jn-ink-soft disabled:opacity-40">
                  {dir < 0 ? <IconChevronLeft size={15} /> : <IconChevronRight size={15} />}
                </button>
              );
              const ell = (key: string) => <span key={key} className="min-w-[18px] text-center text-[12.5px] text-jn-faint">…</span>;
              return (
                <div className="flex shrink-0 flex-wrap items-center justify-center gap-1 px-1 py-2.5">
                  {arrow(-1, page <= 1)}
                  {start > 1 && numBtn(1)}
                  {start > 2 && ell("l")}
                  {nums.map(numBtn)}
                  {end < totalPages - 1 && ell("r")}
                  {end < totalPages && numBtn(totalPages)}
                  {arrow(1, page >= totalPages)}
                </div>
              );
            })()}
          </div>

          {/* right detail */}
          <div className="h-full overflow-y-auto rounded-jn-card border border-jn-line bg-jn-surface">
            {selected ? (
              <JobDetailPanel match={selected} onApply={setApplyTarget} onDismiss={dismissMatch} />
            ) : (
              <div className="grid h-[200px] place-items-center text-jn-faint">{t("detail.selectJob")}</div>
            )}
          </div>
        </div>
      )}

        </>
      )}

      {/* duplicate-apply modal */}
      <Modal isOpen={dup !== null} onOpenChange={(open) => !open && setDup(null)} size="md">
        <ModalContent>
          <ModalHeader>{t("duplicate.title")}</ModalHeader>
          <ModalBody className="text-sm">
            {dup && (
              <p><Trans i18nKey="duplicate.body" t={t} values={{ name: dup.frontman.employee_name, status: dup.frontman.status }} components={[<span key="0" className="font-semibold" />]} /></p>
            )}
          </ModalBody>
          <ModalFooter>
            <HButton variant="light" onPress={() => setDup(null)}>{t("common:actions.cancel")}</HButton>
            <HButton color="warning" onPress={() => dup && void applyToJob(dup.match, true)}>{t("duplicate.applyAnyway")}</HButton>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* apply options modal */}
      <Modal isOpen={applyTarget !== null} onOpenChange={(open) => !open && setApplyTarget(null)} size="md">
        <ModalContent>
          <ModalHeader>{t("applyModal.title")}</ModalHeader>
          <ModalBody className="text-sm">
            <p className="text-default-500">
              <Trans i18nKey="applyModal.question" t={t} values={{ title: applyTarget?.job.title }} components={[<span key="0" className="font-semibold text-foreground" />]} />
            </p>
            <div className="flex flex-col gap-2 pb-1">
              <HButton variant="flat" color="primary" className="h-auto justify-start py-3" startContent={<IconExternalLink size={18} />}
                onPress={() => applyTarget && void applyToJob(applyTarget)}>
                <span className="text-left">
                  <span className="block font-semibold">{t("applyModal.openPostingTitle")}</span>
                  <span className="block text-xs opacity-70">{t("applyModal.openPostingDesc")}</span>
                </span>
              </HButton>
              <HButton variant="flat" className="h-auto justify-start py-3" startContent={<IconMail size={18} />}
                onPress={() => applyTarget && goWriteEmail(applyTarget)}>
                <span className="text-left">
                  <span className="block font-semibold">{t("applyModal.writeEmailTitle")}</span>
                  <span className="block text-xs opacity-70">{t("applyModal.writeEmailDesc")}</span>
                </span>
              </HButton>
            </div>
          </ModalBody>
          <ModalFooter>
            <HButton variant="light" onPress={() => setApplyTarget(null)}>{t("common:actions.cancel")}</HButton>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}

function PlatformPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-jn-pill border px-[13px] py-[7px] text-[13px] font-semibold transition-colors",
        active ? "border-jn-primary bg-jn-primary text-white" : "border-jn-line-2 bg-jn-surface text-jn-ink-soft hover:bg-jn-sunken",
      )}
    >
      {children}
    </button>
  );
}
