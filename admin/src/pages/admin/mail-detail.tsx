import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { addToast } from "@heroui/toast";
import {
  IconArrowLeft, IconArrowDownLeft, IconArrowUpRight, IconAlertTriangle,
  IconMail, IconMailCheck, IconMailExclamation, IconPaperclip, IconUser,
  IconBriefcase, IconMapPin, IconPhone, IconExternalLink, IconSparkles,
} from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import { mailService, type MailLog, type MailLogDetail } from "@/services/mail.service";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

function initials(name: string): string {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function Message({ m, active }: { m: MailLog; active: boolean }) {
  const inbound = m.direction === "in";
  return (
    <div className={`rounded-2xl border p-4 transition-colors ${
      active ? "border-primary/40 bg-primary-50/30" : "border-default-100 bg-white"}`}>
      <div className="flex items-center gap-2.5">
        <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${
          m.is_bounce ? "bg-danger/10 text-danger"
            : inbound ? "bg-emerald-500/10 text-emerald-600"
              : "bg-default-100 text-default-500"}`}>
          {m.is_bounce ? <IconAlertTriangle size={16} /> : inbound ? <IconArrowDownLeft size={16} /> : <IconArrowUpRight size={16} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-foreground">
            {inbound ? `Reply from ${m.from_addr}` : `Sent to ${m.to_addr}`}
          </div>
          <div className="truncate text-xs text-default-400">{m.subject}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {m.cv_attached && <Chip size="sm" variant="flat" startContent={<IconPaperclip size={12} />}>CV</Chip>}
          {m.is_bounce && <Chip size="sm" variant="flat" color="danger">bounced</Chip>}
          {m.status === "failed" && !m.is_bounce && <Chip size="sm" variant="flat" color="danger">failed</Chip>}
        </div>
      </div>
      <div className="mt-3 whitespace-pre-wrap break-words border-t border-default-100 pt-3 text-sm leading-relaxed text-default-700">
        {m.body_text?.trim() || <span className="italic text-default-400">(no body)</span>}
      </div>
      <div className="mt-2 text-[11px] tabular-nums text-default-400">{new Date(m.created_at).toLocaleString("vi-VN")}</div>
    </div>
  );
}

export default function MailDetailPage() {
  const { id } = useParams<{ id: string }>();
  const logId = Number(id);
  const navigate = useNavigate();
  const [data, setData] = useState<MailLogDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await mailService.logDetail(logId)); }
    catch { addToast({ title: "Failed to load mail", color: "danger" }); }
    finally { setLoading(false); }
  }, [logId]);
  useEffect(() => { void load(); }, [load]);

  if (loading || !data) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="h-24 animate-pulse rounded-2xl bg-default-100" />
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="h-96 animate-pulse rounded-2xl bg-default-100 lg:col-span-2" />
          <div className="h-96 animate-pulse rounded-2xl bg-default-100" />
        </div>
      </div>
    );
  }

  const { log, employee: emp, job, match, thread } = data;
  const replies = thread.filter((m) => m.direction === "in").length;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      {/* ── Hero header ── */}
      <Card padding={20} className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <Button isIconOnly variant="light" radius="full" className="shrink-0" onPress={() => navigate("/admin/mail")}>
          <IconArrowLeft size={18} />
        </Button>
        <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
          <IconMail size={24} stroke={1.75} />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-bold tracking-tight text-foreground">{log.subject || "(no subject)"}</h1>
          <div className="mt-1 truncate text-sm text-default-500">
            {emp?.full_name || log.employee_name}{job ? ` · ${job.title}` : ""}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Chip size="sm" variant="flat" color={log.direction === "in" ? "success" : "default"}>
            {log.direction === "in" ? "Reply" : "Sent"}
          </Chip>
          {replies > 0 && <Chip size="sm" variant="flat" color="success">{replies} repl{replies === 1 ? "y" : "ies"}</Chip>}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── Conversation ── */}
        <Card padding={20} className="space-y-3 lg:col-span-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <IconMail size={16} className="text-primary" />
            Conversation
            <Chip size="sm" variant="flat" className="ml-auto">{thread.length} message{thread.length === 1 ? "" : "s"}</Chip>
          </div>
          <div className="space-y-3">
            {thread.map((m) => <Message key={m.id} m={m} active={m.id === log.id} />)}
          </div>
        </Card>

        {/* ── Candidate + Job ── */}
        <div className="flex flex-col gap-4">
          {emp && (
            <Card padding={18} className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconUser size={16} className="text-primary" /> Candidate
              </div>
              <div className="flex items-center gap-3">
                <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-sm font-bold text-primary">
                  {initials(emp.full_name)}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">{emp.full_name}</div>
                  <div className="truncate text-xs text-default-500">{emp.position || "—"}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Chip size="sm" variant="flat">{SENIORITY_LABELS[emp.seniority] ?? emp.seniority}</Chip>
                {emp.experience_years != null && <Chip size="sm" variant="flat">{emp.experience_years}y exp</Chip>}
              </div>
              <div className="space-y-1 text-xs text-default-500">
                {emp.email && <div className="flex items-center gap-1.5"><IconMail size={13} className="text-default-400" />{emp.email}</div>}
                {emp.phone && <div className="flex items-center gap-1.5"><IconPhone size={13} className="text-default-400" />{emp.phone}</div>}
              </div>
              {/* Linked Gmail — the address mail is sent FROM */}
              {emp.linked_email ? (
                <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs ${
                  emp.linked_status === "error" ? "bg-danger-50/40 text-danger" : "bg-success-50/40 text-success-700"}`}>
                  {emp.linked_status === "error"
                    ? <IconMailExclamation size={15} className="shrink-0 text-danger" />
                    : <IconMailCheck size={15} className="shrink-0 text-success" />}
                  <span className="min-w-0">
                    <span className="block text-[10px] uppercase tracking-wide opacity-70">Linked Gmail</span>
                    <span className="block truncate font-medium">{emp.linked_email}</span>
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-xl bg-default-50 px-3 py-2 text-xs text-default-400">
                  <IconMail size={15} className="shrink-0" />
                  <span>No Gmail linked</span>
                </div>
              )}
              {emp.skills.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {emp.skills.slice(0, 8).map((s) => <Chip key={s} size="sm" variant="flat" className="bg-default-100">{s}</Chip>)}
                  {emp.skills.length > 8 && <Chip size="sm" variant="flat">+{emp.skills.length - 8}</Chip>}
                </div>
              )}
              <Button size="sm" variant="bordered" className="w-full" startContent={<IconUser size={14} />}
                onPress={() => navigate(`/admin/employees/${emp.id}/info`)}>View employee</Button>
            </Card>
          )}

          {job && (
            <Card padding={18} className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconBriefcase size={16} className="text-primary" /> Job
              </div>
              <div>
                <div className="text-sm font-semibold leading-snug text-foreground">{job.title}</div>
                {job.company && <div className="mt-0.5 text-xs text-default-500">{job.company}</div>}
              </div>
              <div className="space-y-1 text-xs text-default-500">
                {job.location && <div className="flex items-center gap-1.5"><IconMapPin size={13} className="text-default-400" />{job.location}</div>}
                {job.job_type && <div className="flex items-center gap-1.5"><IconBriefcase size={13} className="text-default-400" />{job.job_type}</div>}
              </div>
              {match && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <Chip size="sm" variant="flat" color="primary" startContent={<IconSparkles size={12} />}>{match.status}</Chip>
                  {match.match_score != null && <Chip size="sm" variant="flat" color="success">{Math.round(match.match_score * 100)}%</Chip>}
                </div>
              )}
              <div className="flex flex-col gap-2">
                {match && (
                  <Button size="sm" variant="bordered" className="w-full" startContent={<IconBriefcase size={14} />}
                    onPress={() => navigate(`/admin/employees/${emp?.id}?match=${match.id}`)}>View match</Button>
                )}
                {job.source_url && (
                  <Button size="sm" variant="light" className="w-full" startContent={<IconExternalLink size={14} />}
                    onPress={() => window.open(job.source_url, "_blank", "noopener")}>Open job posting</Button>
                )}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
