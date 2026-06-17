import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import {
  IconArrowLeft, IconBriefcase, IconCheck, IconMail, IconPhone, IconRefresh,
  IconTrash, IconUser, IconSettings, IconAlertTriangle,
} from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";

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
    try { await employeeService.rematch(empId); addToast({ title: t("info.jobsRefreshed"), color: "success" }); }
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
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="h-28 animate-pulse rounded-2xl bg-default-100" />
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="h-72 animate-pulse rounded-2xl bg-default-100 lg:col-span-2" />
          <div className="h-72 animate-pulse rounded-2xl bg-default-100" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      {/* ── Hero header ── */}
      <Card padding={20} className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <Button isIconOnly variant="light" radius="full" className="shrink-0" onPress={() => navigate(`/admin/employees/${empId}`)}>
          <IconArrowLeft size={18} />
        </Button>
        <div className="grid size-14 shrink-0 place-items-center rounded-full bg-default-100 text-lg font-semibold text-default-600">
          {initials(emp.full_name)}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-bold tracking-tight text-foreground">{emp.full_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-default-500">
            <span className="font-medium text-default-600">{emp.position || "—"}</span>
            <span className="text-default-300">·</span>
            <span>{SENIORITY_LABELS[emp.seniority] ?? emp.seniority}</span>
            {emp.experience_years != null && <><span className="text-default-300">·</span><span>{t("detail.expYears", { years: emp.experience_years })}</span></>}
            {emp.email && <span className="inline-flex items-center gap-1"><IconMail size={13} className="text-default-400" />{emp.email}</span>}
            {emp.phone && <span className="inline-flex items-center gap-1"><IconPhone size={13} className="text-default-400" />{emp.phone}</span>}
          </div>
        </div>
        <Button variant="bordered" size="sm" className="shrink-0" startContent={<IconBriefcase size={14} />}
          onPress={() => navigate(`/admin/employees/${empId}`)}>{t("detail.backToJobs")}</Button>
      </Card>

      {/* ── CV versions (drives ranking) ── */}
      <CvVersionsCard employeeId={empId} onChanged={load} />

      {/* ── Bento: settings (2col) + side stack ── */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Settings */}
        <Card padding={20} className="lg:col-span-2">
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

        {/* Side stack: email + danger */}
        <div className="flex flex-col gap-4">
          <section>
            <SectionHeading icon={<IconUser size={16} />}>{t("info.emailAccount")}</SectionHeading>
            <EmailAccountCard employeeId={empId} />
          </section>

          <section>
            <SectionHeading icon={<IconAlertTriangle size={16} />} danger>{t("info.dangerZone")}</SectionHeading>
            <Card padding={16}>
              <p className="text-xs leading-relaxed text-default-500">
                {t("info.dangerDescription")}
              </p>
              <Button color="danger" size="sm" variant="light" className="mt-2 w-full justify-start px-2" startContent={<IconTrash size={14} />}
                onPress={() => setDeleteOpen(true)}>{t("info.deleteEmployee")}</Button>
            </Card>
          </section>
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
