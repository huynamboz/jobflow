import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";
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
  IconCheck,
  IconExternalLink,
  IconMapPin,
  IconPencil,
  IconRefresh,
  IconTrash,
  IconUsers,
  IconX,
} from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import { employeeService } from "@/services/employee.service";
import { jobService } from "@/services/job.service";
import { matchService } from "@/services/match.service";
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

const STATUS_META: Record<MatchStatus, { label: string; bg: string; color: string }> = {
  suggested: { label: "Suggested", bg: T.surface3, color: T.ink2 },
  pursuing: { label: "Pursuing", bg: T.accent100, color: "#0e5353" },
  applied: { label: "Applied", bg: "oklch(0.94 0.05 280)", color: "oklch(0.45 0.16 280)" },
  won: { label: "Won", bg: T.success50, color: T.success },
  lost: { label: "Lost", bg: T.danger50, color: T.danger },
};

const TABS: { key: MatchStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "suggested", label: "Suggested" },
  { key: "pursuing", label: "Pursuing" },
  { key: "applied", label: "Applied" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function fmtSalary(j: JobLite): string {
  const c = j.salary_currency || "$";
  const k = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`);
  if (j.salary_min && j.salary_max) return `${c}${k(j.salary_min)}–${c}${k(j.salary_max)}`;
  if (j.salary_min) return `${c}${k(j.salary_min)}+`;
  return "";
}

function seniorityGapLabel(gap: number | null): string {
  if (gap === null || gap === undefined) return "Seniority data unavailable";
  if (gap === 0) return "Matches required seniority";
  if (gap > 0) return `Job needs ${gap} level(s) higher`;
  return `Employee is ${-gap} level(s) higher`;
}

function StatusChip({ status }: { status: MatchStatus }) {
  const m = STATUS_META[status];
  return (
    <span style={{ padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600, background: m.bg, color: m.color }}>
      {m.label}
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
  const j = match.job;
  const matched = match.matched_skills?.length ?? 0;
  const missing = match.missing_skills?.length ?? 0;
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
        <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 700, color: T.accent }}>
          {Math.round((match.match_score || 0) * 100)}%
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: T.ink3, marginTop: 3 }}>
        {j.company_name || "—"}{j.location ? ` · ${j.location}` : ""}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        <StatusChip status={match.status} />
        <span style={{ fontSize: 11.5, color: T.ink4 }}>
          {matched} match{missing ? ` · ${missing} missing` : ""}
        </span>
      </div>
    </button>
  );
}

/* ---------------- right: job detail panel ---------------- */
function JobDetailPanel({
  match,
  onStatus,
}: {
  match: EmployeeJobMatch;
  onStatus: (status: MatchStatus) => void;
}) {
  const j = match.job;
  const salary = fmtSalary(j);
  const [desc, setDesc] = useState<string | null>(null);
  const [descLoading, setDescLoading] = useState(true);
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
            {j.applicant_count && <MetaRow icon={<IconUsers size={14} />}>{j.applicant_count} applicants</MetaRow>}
            {j.date_posted && <MetaRow icon={<IconCalendar size={14} />}>{new Date(j.date_posted).toLocaleDateString("vi-VN")}</MetaRow>}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
            {salary && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 600, background: T.success50, color: T.success }}>{salary}</span>}
            {j.job_type && <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 500, background: T.surface3, color: T.ink2 }}>{j.job_type}</span>}
            <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 500, background: j.is_active ? T.success50 : T.surface3, color: j.is_active ? T.success : T.ink4 }}>
              {j.is_active ? "Active" : "Closed"}
            </span>
          </div>
        </div>
        <div style={{ flexShrink: 0, textAlign: "center" }}>
          <div style={{ fontSize: 30, fontWeight: 800, color: T.accent, lineHeight: 1 }}>{Math.round((match.match_score || 0) * 100)}<span style={{ fontSize: 15 }}>%</span></div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: T.ink4, marginTop: 2 }}>match</div>
        </div>
      </div>

      {j.source_url && (
        <a href={j.source_url} target="_blank" rel="noreferrer"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 14, fontSize: 13, fontWeight: 600, color: T.accent, textDecoration: "none" }}>
          View original posting <IconExternalLink size={14} />
        </a>
      )}

      {/* Why it matches */}
      <div style={{ marginTop: 20, padding: 16, borderRadius: 14, background: T.surface2 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 10 }}>Why it matches</div>
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: T.ink3, marginBottom: 4 }}>Matched skills</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {(match.matched_skills ?? []).map((s) => (
              <span key={s} style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.success50, color: T.success }}>{s}</span>
            ))}
            {!match.matched_skills?.length && <span style={{ fontSize: 12, color: T.ink4 }}>none</span>}
          </div>
        </div>
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: T.ink3, marginBottom: 4 }}>Missing skills</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {(match.missing_skills ?? []).map((s) => (
              <span key={s} style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.danger50, color: T.danger }}>{s}</span>
            ))}
            {!match.missing_skills?.length && <span style={{ fontSize: 12, color: T.success }}>meets all required skills</span>}
          </div>
        </div>
        <div style={{ fontSize: 12.5, color: T.ink2 }}>
          <span style={{ color: T.ink3 }}>Seniority: </span>{seniorityGapLabel(match.seniority_gap)}
        </div>
      </div>

      {/* Job description */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 8 }}>Job description</div>
        {descLoading ? (
          <div style={{ fontSize: 13, color: T.ink4 }}>Loading description…</div>
        ) : desc ? (
          <div style={{ fontSize: 13, lineHeight: 1.65, color: T.ink2, whiteSpace: "pre-line" }}>{desc}</div>
        ) : (
          <div style={{ fontSize: 13, color: T.ink4 }}>No description available.</div>
        )}
      </div>

      {/* Actions */}
      <div style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12.5, color: T.ink3 }}>Pipeline:</span>
        <Select
          aria-label="Change status"
          size="sm"
          selectedKeys={[match.status]}
          onSelectionChange={(keys) => {
            const next = Array.from(keys)[0] as MatchStatus;
            if (next !== match.status) onStatus(next);
          }}
          className="max-w-[160px]"
        >
          <SelectItem key="suggested">Suggested</SelectItem>
          <SelectItem key="pursuing">Pursuing</SelectItem>
          <SelectItem key="applied">Applied</SelectItem>
          <SelectItem key="won">Won</SelectItem>
          <SelectItem key="lost">Lost</SelectItem>
        </Select>
        {match.status === "suggested" && (
          <Button size="sm" color="primary" startContent={<IconCheck size={14} />} onPress={() => onStatus("pursuing")}>
            Pursue
          </Button>
        )}
        {match.status === "pursuing" && (
          <Button size="sm" color="primary" onPress={() => onStatus("applied")}>Mark applied</Button>
        )}
      </div>
    </div>
  );
}

/* ============================ page ============================ */
export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const empId = Number(id);
  const navigate = useNavigate();

  const [employee, setEmployee] = useState<Employee | null>(null);
  const [matches, setMatches] = useState<EmployeeJobMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<MatchStatus | "all">("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dup, setDup] = useState<{ matchId: number; frontman: DuplicateApplyFrontman } | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [emp, m] = await Promise.all([
        employeeService.get(empId),
        matchService.list({ employee: empId }),
      ]);
      setEmployee(emp);
      setMatches(m.results);
    } catch {
      addToast({ title: "Failed to load employee", color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [empId]);

  useEffect(() => { void reload(); }, [reload]);

  const visible = useMemo(
    () => (tab === "all" ? matches : matches.filter((m) => m.status === tab)),
    [matches, tab],
  );

  useEffect(() => {
    if (visible.length && !visible.some((m) => m.id === selectedId)) {
      setSelectedId(visible[0].id);
    }
  }, [visible, selectedId]);

  const selected = matches.find((m) => m.id === selectedId) || null;

  const updateStatus = async (matchId: number, status: MatchStatus, confirmDuplicate = false) => {
    try {
      await matchService.update(matchId, { status, confirm_duplicate: confirmDuplicate });
      addToast({ title: "Status updated", color: "success" });
      setDup(null);
      void reload();
    } catch (e: unknown) {
      const resp = (e as { response?: { status?: number; data?: { error?: DuplicateApplyError } } }).response;
      if (resp?.status === 409 && resp.data?.error?.code === "DUPLICATE_APPLY") {
        setDup({ matchId, frontman: resp.data.error.frontman });
        return;
      }
      addToast({ title: "Update failed", color: "danger" });
    }
  };

  const rescore = async () => {
    try {
      await employeeService.rescore(empId);
      addToast({ title: "Re-score queued", color: "success" });
    } catch {
      addToast({ title: "Re-score failed (Celery offline?)", color: "warning" });
    }
  };

  const startEdit = () => { if (employee) { setForm(toForm(employee)); setEditing(true); } };
  const saveEdit = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const skills = form.skills.split(",").map((s) => s.trim()).filter(Boolean);
      const exp = form.experience_years.trim();
      await employeeService.update(empId, {
        full_name: form.full_name.trim(), email: form.email.trim(), phone: form.phone.trim(),
        position: form.position.trim(), seniority: form.seniority,
        experience_years: exp === "" ? null : Number(exp), skills, notes: form.notes,
      });
      addToast({ title: "Employee updated", color: "success" });
      setEditing(false); setForm(null);
      void reload();
    } catch {
      addToast({ title: "Update failed", color: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    setDeleting(true);
    try {
      await employeeService.remove(empId);
      addToast({ title: "Employee deleted", color: "success" });
      navigate("/admin/employees");
    } catch {
      addToast({ title: "Delete failed (admin only?)", color: "danger" });
      setDeleting(false);
    }
  };

  if (loading && !employee) return <div style={{ padding: 40, color: T.ink3 }}>Loading…</div>;
  if (!employee) return <div style={{ padding: 40, color: T.ink3 }}>Employee not found.</div>;

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
            {employee.experience_years != null && ` · ${employee.experience_years}y exp`}
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Button variant="bordered" size="sm" startContent={<IconRefresh size={14} />} onPress={rescore}>Re-score</Button>
          <Button variant="bordered" size="sm" startContent={<IconPencil size={14} />} onPress={startEdit}>Edit</Button>
          <Button variant="light" size="sm" color="danger" startContent={<IconTrash size={14} />} onPress={() => setDeleteOpen(true)}>Delete</Button>
        </div>
      </div>

      {/* contact + skills strip */}
      <Card padding={0} style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", padding: "12px 16px" }}>
        <MetaRow icon={<IconUsers size={14} />}>{employee.email || "no email"}</MetaRow>
        {employee.phone && <MetaRow icon={<IconBriefcase size={14} />}>{employee.phone}</MetaRow>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginLeft: "auto" }}>
          {(employee.skills ?? []).slice(0, 8).map((s) => (
            <span key={s} style={{ padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.surface2, color: T.ink2 }}>{s}</span>
          ))}
          {(employee.skills?.length ?? 0) > 8 && <span style={{ fontSize: 11.5, color: T.ink4, alignSelf: "center" }}>+{employee.skills.length - 8}</span>}
          {!employee.skills?.length && <span style={{ fontSize: 12, color: T.ink4 }}>no skills parsed</span>}
        </div>
      </Card>

      {/* tabs */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {TABS.map((t) => {
          const count = t.key === "all" ? matches.length : matches.filter((m) => m.status === t.key).length;
          const active = tab === t.key;
          return (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              style={{
                padding: "6px 12px", borderRadius: 999, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${active ? T.accent : T.line}`,
                background: active ? T.accent : T.surface, color: active ? "#fff" : T.ink2,
              }}>
              {t.label} <span style={{ opacity: 0.7 }}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* LinkedIn-style browser */}
      {matches.length === 0 ? (
        <Card style={{ display: "grid", placeItems: "center", height: 240, color: T.ink3 }}>
          <div style={{ textAlign: "center" }}>
            <IconBriefcase size={30} style={{ margin: "0 auto 10px", color: T.ink4 }} />
            <div style={{ fontWeight: 600 }}>No matched jobs yet</div>
            <div style={{ fontSize: 13 }}>Re-score after the CV is parsed, or add jobs to the catalog.</div>
          </div>
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 380px) 1fr", gap: 14, alignItems: "stretch", height: "calc(100vh - 220px)" }}>
          {/* left list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", minHeight: 0, overflow: "auto", paddingRight: 4 }}>
            {visible.map((m) => (
              <JobListItem key={m.id} match={m} selected={m.id === selectedId} onSelect={() => setSelectedId(m.id)} />
            ))}
            {visible.length === 0 && <div style={{ padding: 16, fontSize: 13, color: T.ink4 }}>No jobs in this status.</div>}
          </div>
          {/* right detail */}
          <Card padding={0} style={{ height: "100%", overflow: "auto" }}>
            {selected ? (
              <JobDetailPanel match={selected} onStatus={(s) => updateStatus(selected.id, s)} />
            ) : (
              <div style={{ display: "grid", placeItems: "center", height: 200, color: T.ink4 }}>Select a job</div>
            )}
          </Card>
        </div>
      )}

      {/* duplicate-apply modal */}
      <Modal isOpen={dup !== null} onOpenChange={(open) => !open && setDup(null)} size="md">
        <ModalContent>
          <ModalHeader>Job already applied</ModalHeader>
          <ModalBody className="text-sm">
            {dup && (
              <p>
                This job is already being fronted by{" "}
                <span className="font-semibold">{dup.frontman.employee_name}</span>{" "}
                (status: {dup.frontman.status}). Applying twice can expose the shadow
                model to the client. Continue anyway?
              </p>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDup(null)}>Cancel</Button>
            <Button color="warning" onPress={() => dup && void updateStatus(dup.matchId, "applied", true)}>Apply anyway</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* delete confirm modal */}
      <Modal isOpen={deleteOpen} onOpenChange={(open) => !open && setDeleteOpen(false)} size="sm">
        <ModalContent>
          <ModalHeader>Delete employee</ModalHeader>
          <ModalBody className="text-sm">
            Permanently delete <span className="font-semibold">{employee.full_name}</span> and all their job matches? This cannot be undone.
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDeleteOpen(false)} isDisabled={deleting}>Cancel</Button>
            <Button color="danger" startContent={<IconTrash size={14} />} onPress={doDelete} isLoading={deleting}>Delete</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* edit modal */}
      <Modal isOpen={editing} onOpenChange={(open) => !open && setEditing(false)} size="lg">
        <ModalContent>
          <ModalHeader>Edit employee</ModalHeader>
          <ModalBody>
            {form && (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Input size="sm" label="Full name" value={form.full_name} onValueChange={(v) => setForm({ ...form, full_name: v })} />
                <Input size="sm" label="Email" value={form.email} onValueChange={(v) => setForm({ ...form, email: v })} />
                <Input size="sm" label="Phone" value={form.phone} onValueChange={(v) => setForm({ ...form, phone: v })} />
                <Input size="sm" label="Position" value={form.position} onValueChange={(v) => setForm({ ...form, position: v })} />
                <Select size="sm" label="Seniority" selectedKeys={[String(form.seniority)]}
                  onSelectionChange={(keys) => setForm({ ...form, seniority: Number(Array.from(keys)[0]) })}>
                  {SENIORITY_LABELS.map((label, i) => <SelectItem key={String(i)}>{label}</SelectItem>)}
                </Select>
                <Input size="sm" type="number" label="Experience (years)" value={form.experience_years} onValueChange={(v) => setForm({ ...form, experience_years: v })} />
                <Input size="sm" className="md:col-span-2" label="Skills (comma-separated)" value={form.skills} onValueChange={(v) => setForm({ ...form, skills: v })} />
                <Textarea size="sm" className="md:col-span-2" label="Notes" value={form.notes} onValueChange={(v) => setForm({ ...form, notes: v })} />
              </div>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setEditing(false)} isDisabled={saving} startContent={<IconX size={14} />}>Cancel</Button>
            <Button color="primary" onPress={saveEdit} isLoading={saving} startContent={<IconCheck size={14} />}>Save</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}

interface EditForm {
  full_name: string; email: string; phone: string; position: string;
  seniority: number; experience_years: string; skills: string; notes: string;
}

function toForm(e: Employee): EditForm {
  return {
    full_name: e.full_name ?? "", email: e.email ?? "", phone: e.phone ?? "",
    position: e.position ?? "", seniority: e.seniority ?? 2,
    experience_years: e.experience_years != null ? String(e.experience_years) : "",
    skills: (e.skills ?? []).join(", "), notes: e.notes ?? "",
  };
}
