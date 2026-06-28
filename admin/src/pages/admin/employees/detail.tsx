import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Tooltip } from "@heroui/tooltip";
import { Select, SelectItem } from "@heroui/select";
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
} from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Card } from "@/components/ui/card";
import { employeeService } from "@/services/employee.service";
import { jobService } from "@/services/job.service";
import { matchService } from "@/services/match.service";
import { mailService, type CredentialStatus, type MailLog } from "@/services/mail.service";
import type { DuplicateApplyError, DuplicateApplyFrontman } from "@/services/match.service";
import type { Employee } from "@/types/employee.types";
import type { EmployeeJobMatch, JobLite, MatchStatus } from "@/types/match.types";

const T = {
  accent: "#167a7a", accent50: "#e8f4f4", accent100: "#c8e5e5",
  success: "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger: "oklch(0.60 0.22 25)", danger50: "oklch(0.96 0.03 25)",
  warning: "oklch(0.62 0.13 70)", warning50: "oklch(0.97 0.04 75)",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface: "#ffffff", surface2: "oklch(0.97 0.005 85)", surface3: "oklch(0.945 0.006 85)",
  line: "rgba(226,232,240,0.7)",
};

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

const SHOW_MATCH_PCT = true;

const PAGE_SIZE = 10; // job list loads the top 10, then 10 more on demand

// i18n label key per status under matchStatus.*; colors stay here.
const STATUS_META: Record<MatchStatus, { key: string; bg: string; color: string }> = {
  suggested: { key: "suggested", bg: T.surface3, color: T.ink2 },
  pursuing: { key: "pursuing", bg: T.accent100, color: "#0e5353" },
  applied: { key: "applied", bg: "oklch(0.94 0.05 280)", color: "oklch(0.45 0.16 280)" },
  won: { key: "won", bg: T.accent100, color: "#0e5353" },
  in_progress: { key: "inProgress", bg: T.warning50, color: "oklch(0.55 0.12 70)" },
  completed: { key: "completed", bg: T.success50, color: T.success },
  lost: { key: "lost", bg: T.danger50, color: T.danger },
  dismissed: { key: "dismissed", bg: T.surface3, color: T.ink4 },
};


function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function jobPostedLabel(j: JobLite, t: TFunction): string {
  const iso = j.date_posted || j.created_at;
  if (!iso) return "";
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days <= 0) return t("posted.today");
  if (days === 1) return t("posted.dayAgo");
  if (days < 30) return t("posted.daysAgo", { count: days });
  return d.toLocaleDateString("vi-VN", { dateStyle: "short" });
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
    <span style={{ padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600, background: m.bg, color: m.color }}>
      {t(`matchStatus.${m.key}`)}
    </span>
  );
}

function MetaRow({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13, color: T.ink2 }}>
      <span style={{ color: T.ink4, display: "flex" }}>{icon}</span>
      {children}
    </span>
  );
}

/* ---------------- left: job list card ---------------- */
function JobListItem({ match, selected, onSelect }: { match: EmployeeJobMatch; selected: boolean; onSelect: () => void }) {
  const { t } = useTranslation("employees");
  const j = match.job;
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        display: "block", width: "100%", textAlign: "left", cursor: "pointer",
        padding: 14, borderRadius: 14, border: `1px solid ${selected ? T.accent : T.line}`,
        background: selected ? T.accent50 : T.surface, transition: "all 0.12s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: T.ink, lineHeight: 1.3 }}>{j.title}</span>
        {SHOW_MATCH_PCT && (
          <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 700, color: T.accent }}>
            {Math.round((match.match_score || 0) * 100)}%
          </span>
        )}
      </div>
      <div style={{ fontSize: 12.5, color: T.ink3, marginTop: 3 }}>
        {j.company_name || "—"}{j.location ? ` · ${j.location}` : ""}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        {match.status !== "suggested" && <StatusChip status={match.status} />}
        {j.platform_name && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 8px 2px 6px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: T.surface3, color: T.ink3 }}>
            {j.platform_logo && (
              <img
                src={j.platform_logo}
                alt=""
                width={14}
                height={14}
                style={{ borderRadius: 3, objectFit: "contain" }}
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
              />
            )}
            {j.platform_name}
          </span>
        )}
        {j.job_type && <span style={{ fontSize: 11.5, color: T.ink4 }}>{j.job_type}</span>}
        {jobPostedLabel(j, t) && (
          <span style={{ marginLeft: "auto", fontSize: 11.5, color: T.ink4 }}>{jobPostedLabel(j, t)}</span>
        )}
      </div>
    </button>
  );
}

const DIM_LABEL_KEYS: Record<string, string> = {
  skill_fit: "why.dim.skillFit",
  experience_fit: "why.dim.experienceFit",
  seniority_fit: "why.dim.seniorityFit",
  domain_fit: "why.dim.domainFit",
};
const DIM_ORDER = ["skill_fit", "experience_fit", "seniority_fit", "domain_fit"];

// dim_scores are numeric [0,1]; tolerate legacy good/ok/weak strings.
function dimNum(raw: number | string): number {
  if (typeof raw === "number") return raw;
  return ({ good: 1, ok: 0.6, weak: 0.3 } as Record<string, number>)[raw] ?? 0;
}
function dimTone(v: number): string {
  return v >= 0.7 ? T.success : v >= 0.4 ? T.warning : T.danger;
}

function ScoreBar({ label, value, hint, tone = T.accent }: { label: string; value: number; hint?: string; tone?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600, color: T.ink2 }}>{label}</span>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: tone }}>{pct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: T.surface3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: tone, borderRadius: 999 }} />
      </div>
      {hint && <div style={{ fontSize: 11.5, color: T.ink4, marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

/* ---------------- right: job detail panel ---------------- */
function JobDetailPanel({
  match,
  onApply,
  onDismiss,
}: {
  match: EmployeeJobMatch;
  onApply: (m: EmployeeJobMatch) => void;
  onDismiss: (m: EmployeeJobMatch) => void;
}) {
  const { t } = useTranslation("employees");
  const j = match.job;
  const salary = fmtSalary(j);
  const [desc, setDesc] = useState<string | null>(null);
  const [descLoading, setDescLoading] = useState(true);
  const [whyOpen, setWhyOpen] = useState(false);
  const [thread, setThread] = useState<MailLog[]>([]);
  useEffect(() => {
    mailService.thread(match.id).then(setThread).catch(() => setThread([]));
  }, [match.id]);
  useEffect(() => {
    let alive = true;
    setDescLoading(true);
    setDesc(null);
    jobService
      .getJob(j.id)
      .then((d) => { if (alive) setDesc(d.description || ""); })
      .catch(() => { if (alive) setDesc(""); })
      .finally(() => { if (alive) setDescLoading(false); });
    return () => { alive = false; };
  }, [j.id]);
  return (
    <div style={{ padding: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em", margin: 0, color: T.ink, lineHeight: 1.2 }}>{j.title}</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 8 }}>
            <MetaRow icon={<IconBuilding size={14} />}>{j.company_name}</MetaRow>
            <MetaRow icon={<IconMapPin size={14} />}>{j.location}</MetaRow>
            {j.seniority != null && <MetaRow icon={<IconBriefcase size={14} />}>{SENIORITY_LABELS[j.seniority] ?? j.seniority}</MetaRow>}
            {j.applicant_count && <MetaRow icon={<IconUsers size={14} />}>{t("job.applicants", { count: j.applicant_count })}</MetaRow>}
            {j.date_posted && <MetaRow icon={<IconCalendar size={14} />}>{new Date(j.date_posted).toLocaleDateString("vi-VN")}</MetaRow>}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
            {salary && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 600, background: T.success50, color: T.success }}>{salary}</span>}
            {j.job_type && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 500, background: T.surface3, color: T.ink2 }}>{j.job_type}</span>}
            <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 500, background: j.is_active ? T.success50 : T.surface3, color: j.is_active ? T.success : T.ink4 }}>
              {j.is_active ? t("job.active") : t("job.closed")}
            </span>
          </div>
        </div>
        {SHOW_MATCH_PCT && (
          <div style={{ flexShrink: 0, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 800, color: T.accent, lineHeight: 1 }}>{Math.round((match.match_score || 0) * 100)}<span style={{ fontSize: 15 }}>%</span></div>
            <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: T.ink4, marginTop: 2 }}>{t("job.match")}</div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {match.status === "applied" || match.status === "won" || match.status === "lost" ? (
          <>
            <StatusChip status={match.status} />
            <span style={{ fontSize: 12.5, color: T.ink3 }}>{t("job.inJobTracking")}</span>
            {j.source_url && (
              <a href={j.source_url} target="_blank" rel="noreferrer"
                style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, fontWeight: 600, color: T.accent, textDecoration: "none" }}>
                {t("job.openPosting")} <IconExternalLink size={13} />
              </a>
            )}
          </>
        ) : (
          <>
            <Button color="primary" startContent={<IconExternalLink size={15} />} onPress={() => onApply(match)}>
              {t("job.apply")}
            </Button>
            <Button variant="light" color="danger" startContent={<IconX size={15} />} onPress={() => onDismiss(match)}>
              {t("job.dismiss")}
            </Button>
          </>
        )}
      </div>

      {j.source_url && (
        <a href={j.source_url} target="_blank" rel="noreferrer"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 14, fontSize: 13, fontWeight: 600, color: T.accent, textDecoration: "none" }}>
          {t("job.viewOriginal")} <IconExternalLink size={14} />
        </a>
      )}

      {/* Why it matches — accordion */}
      {(() => {
        const matched = match.matched_skills?.length ?? 0;
        const missing = match.missing_skills?.length ?? 0;
        const reqTotal = matched + missing;
        const skillCoverage = reqTotal ? matched / reqTotal : 1;
        const gap = match.seniority_gap;
        const seniorityFit = gap == null ? 0.5 : Math.max(0, 1 - Math.abs(gap) * 0.3);
        const overall = match.match_score || 0;
        return (
          <div style={{ marginTop: 20, borderRadius: 14, background: T.surface2, overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => setWhyOpen((o) => !o)}
              style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: 16, background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
            >
              <span style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3 }}>{t("why.title")}</span>
              <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: T.accent }}>{t("why.matchPct", { pct: Math.round(overall * 100) })}</span>
                <IconChevronDown size={16} style={{ color: T.ink4, transition: "transform 0.15s", transform: whyOpen ? "rotate(180deg)" : "none" }} />
              </span>
            </button>
            {whyOpen && (
              <div style={{ padding: "0 16px 16px" }}>
                <ScoreBar label={t("why.overallMatch")} value={overall} />

                {Object.keys(match.dim_scores ?? {}).length > 0 ? (
                  <div style={{ marginBottom: 4 }}>
                    {DIM_ORDER.filter((k) => match.dim_scores?.[k] != null).map((k) => {
                      const v = dimNum(match.dim_scores![k]);
                      return <ScoreBar key={k} label={DIM_LABEL_KEYS[k] ? t(DIM_LABEL_KEYS[k]) : k} value={v} tone={dimTone(v)} />;
                    })}
                  </div>
                ) : (
                  <>
                    <ScoreBar label={t("why.skillCoverage")} value={skillCoverage} tone={T.success}
                      hint={t("why.skillCoverageHint", { matched, total: reqTotal || matched })} />
                    <ScoreBar label={t("why.seniorityFit")} value={seniorityFit} tone={T.warning}
                      hint={seniorityGapLabel(gap, t)} />
                    <div style={{ fontSize: 11.5, color: T.ink4, marginBottom: 8 }}>
                      {t("why.refreshHint")}
                    </div>
                  </>
                )}

                {/* 025: How this score is computed — provenance đầy đủ của Overall */}
                {(() => {
                  const bd = match.score_breakdown;
                  if (!bd || !bd.stage1 || !Object.keys(bd.stage1).length) return null;
                  const w = bd.weights ?? {};
                  const s1 = bd.stage1 ?? {};
                  const COMP_LABELS: Record<string, string> = { gnn: "GNN", skill: "Skill", seniority: "Seniority", domain: "Domain" };
                  const gateLabels: Record<string, string> = {
                    domain: t("why.compute.gateLabel.domain"),
                    experience: t("why.compute.gateLabel.experience"),
                    seniority: t("why.compute.gateLabel.seniority"),
                  };
                  const firedGates = Object.entries(bd.gates ?? {}).filter(([, v]) => v != null) as [string, number][];
                  return (
                    <div style={{ marginTop: 4, marginBottom: 12, padding: "10px 12px", borderRadius: 10, background: T.surface, border: `1px dashed ${T.border ?? "#e2e8f0"}` }}>
                      <div style={{ fontSize: 11.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: T.ink3, marginBottom: 6 }}>
                        {t("why.compute.title")}
                      </div>
                      <div style={{ fontSize: 12, color: T.ink2, lineHeight: 1.7, fontFamily: "ui-monospace, monospace" }}>
                        <div>
                          <span style={{ color: T.ink3 }}>{t("why.compute.stage1")}&nbsp;&nbsp;</span>
                          {(["gnn", "skill", "seniority", "domain"] as const)
                            .filter((k) => s1[k] != null && w[k] != null)
                            .map((k, i) => (
                              <span key={k}>{i > 0 && " + "}{w[k]}×{COMP_LABELS[k]}({s1[k]})</span>
                            ))}
                          {s1.stage1 != null && <span style={{ fontWeight: 700 }}> = {s1.stage1}</span>}
                        </div>
                        {bd.reranker != null && (
                          <div><span style={{ color: T.ink3 }}>{t("why.compute.stage2")}&nbsp;</span>{bd.reranker} <span style={{ color: T.ink4 }}>{t("why.compute.stage2Note")}</span></div>
                        )}
                        <div>
                          <span style={{ color: T.ink3 }}>{t("why.compute.gates")}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
                          {firedGates.length
                            ? firedGates.map(([k, v]) => `${gateLabels[k] ?? k} ×${v}`).join(" · ")
                            : t("why.compute.noGates")}
                        </div>
                        {bd.calibrated != null && bd.rank_score != null && (
                          <div>
                            <span style={{ color: T.ink3 }}>{t("why.compute.calibration")}&nbsp;&nbsp;</span>
                            rank {bd.rank_score} → <span style={{ fontWeight: 700 }}>P = {bd.calibrated}</span>
                            <span style={{ color: T.ink4 }}> {t("why.compute.display")}</span>
                          </div>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: T.ink4, marginTop: 6, lineHeight: 1.5 }}>
                        {t("why.compute.footnote")}
                      </div>
                    </div>
                  );
                })()}

                {/* 025: 1 list chung — matched (xanh) + covered-by-related (vàng, "react ≈ vuejs");
                    Missing chỉ còn gap thật. Giải thích trực tiếp cách skill_fit tính
                    (matched = full credit, covered = half credit, missing = 0). */}
                {(() => {
                  const covered = match.covered_skills ?? {};
                  const allMissing = match.missing_skills ?? [];
                  const trulyMissing = allMissing.filter((s) => !(s in covered));
                  const nearMisses = allMissing.filter((s) => s in covered);
                  const matchedList = match.matched_skills ?? [];
                  return (
                    <div style={{ marginTop: 6 }}>
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 12, color: T.ink3, marginBottom: 4 }}>{t("why.matchedSkills")}</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {matchedList.map((s) => (
                            <span key={s} style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.success50, color: T.success }}>{s}</span>
                          ))}
                          {nearMisses.map((s) => (
                            <Tooltip
                              key={s}
                              placement="top"
                              delay={0}
                              closeDelay={50}
                              content={
                                <div style={{ maxWidth: 240, fontSize: 12, lineHeight: 1.5, padding: 2 }}>
                                  <Trans i18nKey="why.nearMissTooltip" t={t} values={{ skill: s, covered: covered[s] }} components={[<b key="0" />, <b key="1" />]} />
                                </div>
                              }
                            >
                              <span style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.warning50 ?? "#fff7ed", color: "oklch(0.55 0.12 70)", cursor: "help" }}>
                                {s} <span style={{ opacity: 0.7 }}>≈ {covered[s]}</span>
                              </span>
                            </Tooltip>
                          ))}
                          {!matchedList.length && !nearMisses.length && <span style={{ fontSize: 12, color: T.ink4 }}>{t("why.none")}</span>}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 12, color: T.ink3, marginBottom: 4 }}>{t("why.missingSkills")}</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {trulyMissing.map((s) => (
                            <span key={s} style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.danger50, color: T.danger }}>{s}</span>
                          ))}
                          {!trulyMissing.length && <span style={{ fontSize: 12, color: T.success }}>{t("why.meetsAll")}</span>}
                        </div>
                      </div>
                    </div>                  );
                })()}
              </div>
            )}
          </div>
        );
      })()}

      {/* Job description */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 8 }}>{t("job.description")}</div>
        {descLoading ? (
          <div style={{ fontSize: 13, color: T.ink4 }}>{t("job.loadingDescription")}</div>
        ) : desc ? (
          <div style={{ fontSize: 13, lineHeight: 1.65, color: T.ink2, whiteSpace: "pre-line" }}>{desc}</div>
        ) : (
          <div style={{ fontSize: 13, color: T.ink4 }}>{t("job.noDescription")}</div>
        )}
      </div>

      {/* 026: mail thread for this application */}
      {thread.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 8 }}>{t("job.emailThread")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {thread.map((e) => (
              <div key={e.id} style={{ borderRadius: 10, border: `1px solid ${e.is_bounce ? T.danger : T.line}`,
                                       background: e.direction === "in" ? T.accent50 : T.surface, padding: "10px 12px" }}>
                <div style={{ fontSize: 11.5, color: T.ink4, marginBottom: 4 }}>
                  {e.direction === "out" ? t("job.sentTo", { addr: e.to_addr }) : t("job.replyFrom", { addr: e.from_addr })}
                  {e.is_bounce && <span style={{ color: T.danger, fontWeight: 700 }}> · {t("job.deliveryFailed")}</span>}
                  {e.cv_attached && <span style={{ color: T.success }}> · {t("job.cvAttached")}</span>}
                  <span style={{ marginLeft: 8 }}>{new Date(e.created_at).toLocaleString("vi-VN")}</span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.ink2 }}>{e.subject}</div>
                <div style={{ fontSize: 12.5, color: T.ink2, marginTop: 3, whiteSpace: "pre-line", lineHeight: 1.5 }}>{e.body_text}</div>
              </div>
            ))}
          </div>
        </div>
      )}
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
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [tab] = useState<MatchStatus | "all">("all"); // status filter removed from UI; list shows all
  const [sortBy, setSortBy] = useState<"score" | "newest">("score");
  const [platformFilter, setPlatformFilter] = useState<string>(""); // platform slug; "" = all
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dup, setDup] = useState<{ match: EmployeeJobMatch; frontman: DuplicateApplyFrontman } | null>(null);
  const [applyTarget, setApplyTarget] = useState<EmployeeJobMatch | null>(null);

  // Server-side status filter per tab; matches arrive ranked by score, paginated.
  const listParams = useCallback(
    (pg: number) => ({
      employee: empId,
      ...(platformFilter ? { platform: platformFilter } : {}),
      hide_applied: true, // already-applied jobs live on the job-tracking pipeline
      ordering: sortBy === "newest" ? "-job__created_at" : "-match_score",
      page: pg, page_size: PAGE_SIZE,
    }),
    [empId, sortBy, platformFilter],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [emp, m] = await Promise.all([
        employeeService.get(empId),
        matchService.list(listParams(1)),
      ]);
      setEmployee(emp);
      setMatches(m.results);
      setTotal(m.count ?? m.results.length);
      setPage(1);
    } catch {
      addToast({ title: t("detail.loadFailed"), color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [empId, listParams]);

  useEffect(() => { void reload(); }, [reload]);

  // Pagination: each page REPLACES the list (not append).
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
  }, [loadingMore, listParams]);

  // 026: deep-link from a notification (?match=) selects that match if present;
  // else default to the top match.
  useEffect(() => {
    if (!matches.length) return;
    if (wantMatch && matches.some((m) => m.id === wantMatch)) {
      if (selectedId !== wantMatch) setSelectedId(wantMatch);
      return;
    }
    if (!matches.some((m) => m.id === selectedId)) setSelectedId(matches[0].id);
  }, [matches, selectedId, wantMatch]);

  const selected = matches.find((m) => m.id === selectedId) || null;

  // Apply: mark the match applied (saved to job tracking) and open the posting.
  const applyToJob = async (match: EmployeeJobMatch, confirmDuplicate = false) => {
    try {
      await matchService.update(match.id, { status: "applied", confirm_duplicate: confirmDuplicate });
      setDup(null);
      setApplyTarget(null);
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

  // Write email: open the composer with employee + job + match context.
  const goWriteEmail = (match: EmployeeJobMatch) => {
    setApplyTarget(null);
    navigate(`/admin/apply-email?employee=${empId}&job=${match.job.id}&match=${match.id}`);
  };

  // Dismiss: hide from the list, keep out of re-ranking, store as a label.
  const dismissMatch = async (match: EmployeeJobMatch) => {
    try {
      await matchService.update(match.id, { status: "dismissed" });
      addToast({ title: t("toast.dismissed"), description: t("toast.dismissedDesc"), color: "default" });
      await reload();
    } catch {
      addToast({ title: t("toast.updateFailed"), color: "danger" });
    }
  };

  if (loading && !employee) return <div style={{ padding: 40, color: T.ink3 }}>{t("detail.loading")}</div>;
  if (!employee) return <div style={{ padding: 40, color: T.ink3 }}>{t("detail.notFound")}</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Button variant="light" isIconOnly onPress={() => navigate("/admin/employees")}>
          <IconArrowLeft size={18} />
        </Button>
        <span style={{ width: 48, height: 48, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: T.accent50, color: T.accent, fontWeight: 700, fontSize: 17 }}>
          {initials(employee.full_name)}
        </span>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: T.ink, letterSpacing: "-0.02em" }}>{employee.full_name}</h1>
          <div style={{ fontSize: 13, color: T.ink3 }}>
            {employee.position || "—"} · {SENIORITY_LABELS[employee.seniority] ?? employee.seniority}
            {employee.experience_years != null && ` · ${t("detail.expYears", { years: employee.experience_years })}`}
          </div>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="bordered" size="sm" startContent={<IconUser size={14} />} onPress={() => navigate(`/admin/employees/${empId}/info`)}>
            {t("detail.viewDetail")}
          </Button>
        </div>
      </div>

      {/* one row: platform filter (left) + sort (right) */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {(employee.matches_count_by_platform?.filter((p) => p.slug).length ?? 0) > 1 && (
          <>
            <span style={{ fontSize: 11.5, color: T.ink4 }}>{t("detail.platformLabel")}</span>
            <button type="button" onClick={() => setPlatformFilter("")}
              style={{
                padding: "5px 11px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${platformFilter === "" ? T.accent : T.line}`,
                background: platformFilter === "" ? T.accent : T.surface, color: platformFilter === "" ? "#fff" : T.ink2,
              }}>
              {t("detail.platformAll")}
            </button>
            {employee.matches_count_by_platform!.filter((p) => p.slug).map((p) => {
              const active = platformFilter === p.slug;
              return (
                <button key={p.slug} type="button"
                  onClick={() => setPlatformFilter((prev) => (prev === p.slug ? "" : p.slug))}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 6,
                    padding: "5px 11px 5px 7px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${active ? T.accent : T.line}`,
                    background: active ? T.accent : T.surface, color: active ? "#fff" : T.ink2,
                  }}>
                  {p.logo && (
                    <img
                      src={p.logo}
                      alt=""
                      width={15}
                      height={15}
                      style={{ borderRadius: 3, objectFit: "contain", background: "#fff" }}
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                    />
                  )}
                  {p.name} <span style={{ opacity: 0.7 }}>{p.count}</span>
                </button>
              );
            })}
          </>
        )}
        {/* sort — pushed to the right */}
        <span style={{ marginLeft: "auto", display: "inline-flex", gap: 4, alignItems: "center" }}>
          <span style={{ fontSize: 11.5, color: T.ink4 }}>{t("detail.sortLabel")}</span>
          {([["score", t("detail.sortScore")], ["newest", t("detail.sortNewest")]] as const).map(([key, label]) => (
            <button key={key} type="button" onClick={() => setSortBy(key)}
              style={{
                padding: "5px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${sortBy === key ? T.accent : T.line}`,
                background: sortBy === key ? T.accent50 : T.surface,
                color: sortBy === key ? T.accent : T.ink3,
              }}>
              {label}
            </button>
          ))}
        </span>
      </div>

      {/* LinkedIn-style browser */}
      {matches.length === 0 ? (
        <Card style={{ display: "grid", placeItems: "center", height: 240, color: T.ink3 }}>
          <div style={{ textAlign: "center" }}>
            <IconBriefcase size={30} style={{ margin: "0 auto 10px", color: T.ink4 }} />
            <div style={{ fontWeight: 600 }}>{tab === "all" ? t("detail.emptyAllTitle") : t("detail.emptyStatusTitle")}</div>
            <div style={{ fontSize: 13 }}>{tab === "all" ? t("detail.emptyAllHint") : t("detail.emptyStatusHint")}</div>
          </div>
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 380px) 1fr", gap: 14, alignItems: "stretch", height: "calc(100vh - 220px)" }}>
          {/* left list — page-based pagination */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", minHeight: 0, overflow: "auto", paddingRight: 4 }}>
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
                  <button key={p} type="button" disabled={loadingMore || active}
                    onClick={() => void goToPage(p)}
                    style={{
                      minWidth: 28, height: 28, padding: "0 6px", borderRadius: 8, cursor: active ? "default" : "pointer",
                      fontSize: 12.5, fontWeight: 600, fontVariantNumeric: "tabular-nums",
                      border: `1px solid ${active ? T.accent : T.line}`,
                      background: active ? T.accent : T.surface, color: active ? "#fff" : T.ink2,
                    }}>
                    {p}
                  </button>
                );
              };
              const arrow = (dir: -1 | 1, disabled: boolean) => (
                <button type="button" disabled={disabled || loadingMore} onClick={() => void goToPage(page + dir)}
                  aria-label={dir < 0 ? "Prev" : "Next"}
                  style={{
                    width: 28, height: 28, borderRadius: 8, display: "grid", placeItems: "center",
                    cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1,
                    border: `1px solid ${T.line}`, background: T.surface, color: T.ink2,
                  }}>
                  {dir < 0 ? <IconChevronLeft size={15} /> : <IconChevronRight size={15} />}
                </button>
              );
              const ell = (k: string) => (
                <span key={k} style={{ minWidth: 18, textAlign: "center", color: T.ink4, fontSize: 12.5 }}>…</span>
              );
              return (
                <div className="shrink-0" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: 4, padding: "10px 4px" }}>
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
          <Card padding={0} style={{ height: "100%", overflow: "auto" }}>
            {selected ? (
              <JobDetailPanel match={selected} onApply={setApplyTarget} onDismiss={dismissMatch} />
            ) : (
              <div style={{ display: "grid", placeItems: "center", height: 200, color: T.ink4 }}>{t("detail.selectJob")}</div>
            )}
          </Card>
        </div>
      )}

      {/* duplicate-apply modal */}
      <Modal isOpen={dup !== null} onOpenChange={(open) => !open && setDup(null)} size="md">
        <ModalContent>
          <ModalHeader>{t("duplicate.title")}</ModalHeader>
          <ModalBody className="text-sm">
            {dup && (
              <p>
                <Trans
                  i18nKey="duplicate.body"
                  t={t}
                  values={{ name: dup.frontman.employee_name, status: dup.frontman.status }}
                  components={[<span key="0" className="font-semibold" />]}
                />
              </p>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDup(null)}>{t("common:actions.cancel")}</Button>
            <Button color="warning" onPress={() => dup && void applyToJob(dup.match, true)}>{t("duplicate.applyAnyway")}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* apply options modal */}
      <Modal isOpen={applyTarget !== null} onOpenChange={(open) => !open && setApplyTarget(null)} size="md">
        <ModalContent>
          <ModalHeader>{t("applyModal.title")}</ModalHeader>
          <ModalBody className="text-sm">
            <p className="text-default-500">
              <Trans
                i18nKey="applyModal.question"
                t={t}
                values={{ title: applyTarget?.job.title }}
                components={[<span key="0" className="font-semibold text-foreground" />]}
              />
            </p>
            <div className="flex flex-col gap-2 pb-1">
              <Button variant="flat" color="primary" className="h-auto justify-start py-3"
                startContent={<IconExternalLink size={18} />}
                onPress={() => applyTarget && void applyToJob(applyTarget)}>
                <span className="text-left">
                  <span className="block font-semibold">{t("applyModal.openPostingTitle")}</span>
                  <span className="block text-xs opacity-70">{t("applyModal.openPostingDesc")}</span>
                </span>
              </Button>
              <Button variant="flat" className="h-auto justify-start py-3"
                startContent={<IconMail size={18} />}
                onPress={() => applyTarget && goWriteEmail(applyTarget)}>
                <span className="text-left">
                  <span className="block font-semibold">{t("applyModal.writeEmailTitle")}</span>
                  <span className="block text-xs opacity-70">{t("applyModal.writeEmailDesc")}</span>
                </span>
              </Button>
            </div>
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setApplyTarget(null)}>{t("common:actions.cancel")}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

    </div>
  );
}

