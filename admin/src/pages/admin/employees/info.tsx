import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import {
  IconArrowLeft, IconBriefcase, IconCheck, IconChevronRight, IconMail, IconPhone,
  IconRefresh, IconTrash, IconUser, IconSettings, IconAlertTriangle, IconFileCv,
  IconCalendar, IconBolt, IconSparkles,
} from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Card } from "@/components/ui/card";
import EmailAccountCard from "@/components/admin/email-account-card";
import CvVersionsCard from "@/components/admin/cv-versions-card";
import { employeeService } from "@/services/employee.service";
import type { Employee } from "@/types/employee.types";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

function initials(name: string): string {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

// Relative-day label for timeline / last-activity stamps.
function relDays(iso: string | null | undefined, t: TFunction): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days <= 0) return t("posted.today");
  if (days === 1) return t("posted.dayAgo");
  if (days < 30) return t("posted.daysAgo", { count: days });
  return d.toLocaleDateString("vi-VN", { dateStyle: "short" });
}

interface Form {
  full_name: string; email: string; phone: string; position: string;
  seniority: number; experience_years: string; skills: string; notes: string;
}
const toForm = (e: Employee): Form => ({
  full_name: e.full_name ?? "", email: e.email ?? "", phone: e.phone ?? "",
  position: e.position ?? "", seniority: e.seniority ?? 2,
  experience_years: e.experience_years != null ? String(e.experience_years) : "",
  skills: (e.skills ?? []).join(", "), notes: e.notes ?? "",
});

function SectionHeading({ icon, children, danger }: { icon: React.ReactNode; children: React.ReactNode; danger?: boolean }) {
  return (
    <div className={`mb-3 flex items-center gap-2 text-sm font-semibold ${danger ? "text-danger" : "text-foreground"}`}>
      <span className={danger ? "text-danger/70" : "text-default-400"}>{icon}</span>
      {children}
    </div>
  );
}

/* ---------------- left sidebar pieces ---------------- */
function InfoLine({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10.5px] font-bold uppercase tracking-[0.05em] text-default-400">{label}</span>
      <span className="text-[13px] font-medium text-foreground">{value}</span>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <Card padding={16} className="flex flex-col gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-default-500">
        <span className="text-default-400">{icon}</span>{label}
      </span>
      <span className="text-2xl font-extrabold leading-none tabular-nums text-foreground">{value}</span>
    </Card>
  );
}

type SidebarTab = "info" | "activity";

function ProfileSidebar({
  emp, onRefresh, refreshing,
}: {
  emp: Employee; onRefresh: () => void; refreshing: boolean;
}) {
  const { t } = useTranslation("employees");
  const navigate = useNavigate();
  const [tab, setTab] = useState<SidebarTab>("info");

  const timeline = useMemo(() => {
    const ev: { id: string; date: string; label: string; danger?: boolean }[] = [];
    if (emp.parsed_at)
      ev.push({ id: "parsed", date: emp.parsed_at, label: emp.is_parse_failed ? t("info.timelineParseFailed") : t("info.timelineParsed"), danger: emp.is_parse_failed });
    if (emp.updated_at) ev.push({ id: "updated", date: emp.updated_at, label: t("info.timelineUpdated") });
    if (emp.created_at) ev.push({ id: "created", date: emp.created_at, label: t("info.timelineCreated") });
    return ev.sort((a, b) => +new Date(b.date) - +new Date(a.date));
  }, [emp, t]);

  const ActionBtn = ({ icon, label, onClick, href }: { icon: React.ReactNode; label: string; onClick?: () => void; href?: string }) => {
    const inner = (
      <>
        <span className="grid size-9 place-items-center rounded-xl border border-card-border bg-default-50 text-default-600">{icon}</span>
        <span className="text-[11px] font-medium text-default-500">{label}</span>
      </>
    );
    const cls = "flex flex-col items-center gap-1.5 no-underline";
    return href
      ? <a href={href} className={cls}>{inner}</a>
      : <button type="button" onClick={onClick} className={cls}>{inner}</button>;
  };

  return (
    <Card padding={0} className="sticky top-2 overflow-hidden">
      {/* identity */}
      <div className="flex flex-col items-center px-5 pb-4 pt-6 text-center">
        <span className="grid size-[72px] place-items-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
          {initials(emp.full_name)}
        </span>
        <h2 className="mb-0.5 mt-3 text-[17px] font-bold tracking-tight text-foreground">{emp.full_name}</h2>
        <div className="text-xs text-default-400">{t("detail.employeeTag")} · #{emp.id}</div>
      </div>

      {/* quick actions */}
      <div className="flex justify-center gap-7 px-5 pb-4">
        {emp.email && <ActionBtn icon={<IconMail size={18} />} label={t("info.email")} href={`mailto:${emp.email}`} />}
        <ActionBtn icon={<IconBriefcase size={18} />} label={t("detail.backToJobs")} onClick={() => navigate(`/admin/employees/${emp.id}`)} />
        <ActionBtn icon={<IconRefresh size={18} className={refreshing ? "animate-spin" : ""} />} label={t("info.refreshJobs")} onClick={onRefresh} />
      </div>

      {/* last activity */}
      <div className="flex items-center gap-1.5 border-y border-card-border px-5 py-2.5 text-[11.5px] text-default-500">
        <IconCalendar size={13} className="text-default-400" />
        {t("detail.lastActivity")} · <span className="font-semibold text-default-600">{relDays(emp.updated_at, t)}</span>
      </div>

      {/* toggle */}
      <div className="flex gap-6 px-5 pt-3">
        {(["info", "activity"] as const).map((k) => (
          <button key={k} type="button" onClick={() => setTab(k)}
            className={`border-b-2 pb-2.5 text-[13px] font-semibold ${tab === k ? "border-primary text-foreground" : "border-transparent text-default-400"}`}>
            {t(k === "info" ? "detail.tabInfo" : "detail.tabActivity")}
          </button>
        ))}
      </div>

      <div className="border-t border-card-border p-5">
        {tab === "info" ? (
          <div className="flex flex-col gap-3.5">
            <InfoLine label={t("info.position")} value={emp.position || "—"} />
            <InfoLine label={t("info.seniorityLabel")} value={SENIORITY_LABELS[emp.seniority] ?? emp.seniority} />
            {emp.experience_years != null && <InfoLine label={t("info.experienceYears")} value={t("detail.expYears", { years: emp.experience_years })} />}
            {emp.email && <InfoLine label={t("info.email")} value={<span className="inline-flex items-center gap-1.5 break-all"><IconMail size={13} className="shrink-0 text-default-400" />{emp.email}</span>} />}
            {emp.phone && <InfoLine label={t("info.phone")} value={<span className="inline-flex items-center gap-1.5"><IconPhone size={13} className="text-default-400" />{emp.phone}</span>} />}
            {(emp.skills?.length ?? 0) > 0 && (
              <div className="flex flex-col gap-1.5">
                <span className="text-[10.5px] font-bold uppercase tracking-[0.05em] text-default-400">{t("info.skills")}</span>
                <div className="flex flex-wrap gap-1.5">
                  {emp.skills.map((s) => (
                    <span key={s} className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11.5px] font-medium text-primary">{s}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col">
            {timeline.map((e, i) => (
              <div key={e.id} className="flex gap-2.5">
                <div className="flex flex-col items-center">
                  <span className={`mt-1 size-2.5 shrink-0 rounded-full ${e.danger ? "bg-danger" : "bg-primary"}`} />
                  {i < timeline.length - 1 && <span className="mt-0.5 w-px flex-1 bg-card-border" />}
                </div>
                <div className="min-w-0 pb-3.5">
                  <div className="text-[12.5px] font-medium leading-tight text-foreground">{e.label}</div>
                  <div className="mt-0.5 text-[11px] text-default-400">{relDays(e.date, t)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

/* ============================ page ============================ */
type MainTab = "details" | "cv" | "email" | "danger";

export default function EmployeeInfoPage() {
  const { t } = useTranslation("employees");
  const { id } = useParams<{ id: string }>();
  const empId = Number(id);
  const navigate = useNavigate();

  const [emp, setEmp] = useState<Employee | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [mainTab, setMainTab] = useState<MainTab>("details");

  const load = useCallback(async () => {
    setLoading(true);
    try { const e = await employeeService.get(empId); setEmp(e); setForm(toForm(e)); }
    catch { addToast({ title: t("info.loadFailed"), color: "danger" }); }
    finally { setLoading(false); }
  }, [empId]);
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
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
      addToast({ title: t("info.saved"), color: "success" });
      await load();
    } catch { addToast({ title: t("info.saveFailed"), color: "danger" }); }
    finally { setSaving(false); }
  };

  const refreshJobs = async () => {
    setRefreshing(true);
    try { await employeeService.rematch(empId); addToast({ title: t("info.jobsRefreshed"), color: "success" }); await load(); }
    catch { addToast({ title: t("info.refreshFailed"), color: "danger" }); }
    finally { setRefreshing(false); }
  };
  const rescore = async () => {
    try { await employeeService.rescore(empId); addToast({ title: t("info.rescoreQueued"), color: "success" }); }
    catch { addToast({ title: t("info.rescoreFailed"), color: "warning" }); }
  };
  const doDelete = async () => {
    setDeleting(true);
    try { await employeeService.remove(empId); addToast({ title: t("info.deleted"), color: "default" }); navigate("/admin/employees"); }
    catch { addToast({ title: t("info.deleteFailed"), color: "danger" }); setDeleting(false); }
  };

  if (loading || !emp || !form) {
    return (
      <div className="flex flex-col gap-4">
        <div className="h-6 w-48 animate-pulse rounded bg-default-100" />
        <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="h-96 animate-pulse rounded-2xl bg-default-100" />
          <div className="flex flex-col gap-4">
            <div className="h-20 animate-pulse rounded-2xl bg-default-100" />
            <div className="h-72 animate-pulse rounded-2xl bg-default-100" />
          </div>
        </div>
      </div>
    );
  }

  const TABS: { key: MainTab; label: string; icon: React.ReactNode }[] = [
    { key: "details", label: t("info.settings"), icon: <IconSettings size={15} /> },
    { key: "cv", label: t("cvVersions.title"), icon: <IconFileCv size={15} /> },
    { key: "email", label: t("info.emailAccount"), icon: <IconMail size={15} /> },
    { key: "danger", label: t("info.dangerZone"), icon: <IconAlertTriangle size={15} /> },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* breadcrumb */}
      <div className="flex items-center gap-2">
        <Button variant="light" isIconOnly size="sm" onPress={() => navigate("/admin/employees")}>
          <IconArrowLeft size={18} />
        </Button>
        <button type="button" onClick={() => navigate("/admin/employees")} className="text-[13px] font-semibold text-default-500">
          {t("detail.breadcrumbEmployees")}
        </button>
        <IconChevronRight size={14} className="text-default-300" />
        <span className="text-[13px] font-semibold text-foreground">{emp.full_name}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] lg:items-start">
        {/* LEFT — profile sidebar */}
        <ProfileSidebar emp={emp} onRefresh={refreshJobs} refreshing={refreshing} />

        {/* RIGHT — main */}
        <div className="flex min-w-0 flex-col gap-4">
          {/* title header */}
          <div className="flex flex-wrap items-start gap-3">
            <div className="min-w-0">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">{emp.full_name}</h1>
              <div className="mt-1 inline-flex items-center gap-1.5 text-[12.5px] text-default-500">
                <IconCalendar size={13} className="text-default-400" />
                {t("detail.createdOn", { date: new Date(emp.created_at).toLocaleDateString("vi-VN") })}
              </div>
            </div>
            <div className="ml-auto flex gap-2">
              <Button variant="bordered" size="sm" startContent={<IconRefresh size={14} className={refreshing ? "animate-spin" : ""} />} isLoading={refreshing} onPress={refreshJobs}>
                {t("info.refreshJobs")}
              </Button>
              <Button color="primary" size="sm" startContent={<IconBriefcase size={14} />} onPress={() => navigate(`/admin/employees/${empId}`)}>
                {t("detail.backToJobs")}
              </Button>
            </div>
          </div>

          {/* stat cards */}
          <div className="grid grid-cols-3 gap-3">
            <StatCard icon={<IconBriefcase size={15} />} label={t("detail.statMatches")} value={emp.match_count ?? 0} />
            <StatCard icon={<IconSparkles size={15} />} label={t("info.statSkills")} value={emp.skills?.length ?? 0} />
            <StatCard icon={<IconBolt size={15} />} label={t("info.statExperience")} value={emp.experience_years != null ? t("detail.expYears", { years: emp.experience_years }) : "—"} />
          </div>

          {/* tab bar */}
          <div className="flex flex-wrap gap-1 border-b border-card-border">
            {TABS.map((tb) => {
              const active = mainTab === tb.key;
              const danger = tb.key === "danger";
              return (
                <button key={tb.key} type="button" onClick={() => setMainTab(tb.key)}
                  className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-semibold ${
                    active
                      ? danger ? "border-danger text-danger" : "border-primary text-foreground"
                      : "border-transparent text-default-400 hover:text-default-600"
                  }`}>
                  {tb.icon}{tb.label}
                </button>
              );
            })}
          </div>

          {/* tab content */}
          {mainTab === "details" && (
            <Card padding={20}>
              <SectionHeading icon={<IconSettings size={16} />}>{t("info.settings")}</SectionHeading>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Input size="sm" label={t("info.fullName")} value={form.full_name} onValueChange={(v) => setForm({ ...form, full_name: v })} />
                <Input size="sm" label={t("info.email")} value={form.email} onValueChange={(v) => setForm({ ...form, email: v })} />
                <Input size="sm" label={t("info.phone")} value={form.phone} onValueChange={(v) => setForm({ ...form, phone: v })} />
                <Input size="sm" label={t("info.position")} value={form.position} onValueChange={(v) => setForm({ ...form, position: v })} />
                <Select size="sm" label={t("info.seniorityLabel")} selectedKeys={[String(form.seniority)]}
                  onSelectionChange={(keys) => setForm({ ...form, seniority: Number(Array.from(keys)[0]) })}>
                  {SENIORITY_LABELS.map((label, i) => <SelectItem key={String(i)}>{label}</SelectItem>)}
                </Select>
                <Input size="sm" type="number" label={t("info.experienceYears")} value={form.experience_years} onValueChange={(v) => setForm({ ...form, experience_years: v })} />
                <Input size="sm" className="md:col-span-2" label={t("info.skills")} value={form.skills} onValueChange={(v) => setForm({ ...form, skills: v })} />
                <Textarea size="sm" className="md:col-span-2" label={t("info.notes")} value={form.notes} onValueChange={(v) => setForm({ ...form, notes: v })} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button color="primary" size="sm" startContent={<IconCheck size={14} />} isLoading={saving} onPress={save}>{t("info.saveChanges")}</Button>
                <Button variant="bordered" size="sm" startContent={<IconBriefcase size={14} />} isLoading={refreshing} onPress={refreshJobs}>{t("info.refreshJobs")}</Button>
                <Button variant="bordered" size="sm" startContent={<IconRefresh size={14} />} onPress={rescore}>{t("info.rescore")}</Button>
              </div>
            </Card>
          )}

          {mainTab === "cv" && <CvVersionsCard employeeId={empId} onChanged={load} />}

          {mainTab === "email" && <EmailAccountCard employeeId={empId} />}

          {mainTab === "danger" && (
            <Card padding={20}>
              <SectionHeading icon={<IconAlertTriangle size={16} />} danger>{t("info.dangerZone")}</SectionHeading>
              <p className="text-xs leading-relaxed text-default-500">{t("info.dangerDescription")}</p>
              <Button color="danger" size="sm" variant="flat" className="mt-3" startContent={<IconTrash size={14} />}
                onPress={() => setDeleteOpen(true)}>{t("info.deleteEmployee")}</Button>
            </Card>
          )}
        </div>
      </div>

      <Modal isOpen={deleteOpen} onOpenChange={(o) => !o && setDeleteOpen(false)} size="sm">
        <ModalContent>
          <ModalHeader>{t("info.deleteTitle")}</ModalHeader>
          <ModalBody className="text-sm">
            <Trans i18nKey="info.deleteConfirm" t={t} values={{ name: emp.full_name }}>
              Permanently delete <span className="font-semibold">{{ name: emp.full_name } as never}</span> and all their job matches? This cannot be undone.
            </Trans>
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDeleteOpen(false)} isDisabled={deleting}>{t("common:actions.cancel")}</Button>
            <Button color="danger" startContent={<IconTrash size={14} />} onPress={doDelete} isLoading={deleting}>{t("common:actions.delete")}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
