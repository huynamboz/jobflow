import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import {
  IconArrowLeft, IconBriefcase, IconCheck, IconMail, IconPhone, IconRefresh, IconTrash, IconUser,
} from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import EmailAccountCard from "@/components/admin/email-account-card";
import { employeeService } from "@/services/employee.service";
import type { Employee } from "@/types/employee.types";

const T = {
  accent: "#167a7a", accent50: "#e8f4f4",
  danger: "oklch(0.60 0.22 25)",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface: "#ffffff", surface2: "oklch(0.97 0.005 85)", line: "rgba(226,232,240,0.7)",
};
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

export default function EmployeeInfoPage() {
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
    catch { addToast({ title: "Failed to load employee", color: "danger" }); }
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
      addToast({ title: "Saved", color: "success" });
      await load();
    } catch { addToast({ title: "Save failed", color: "danger" }); }
    finally { setSaving(false); }
  };

  const refreshJobs = async () => {
    setRefreshing(true);
    try { await employeeService.rematch(empId); addToast({ title: "Jobs refreshed", color: "success" }); }
    catch { addToast({ title: "Refresh failed", color: "danger" }); }
    finally { setRefreshing(false); }
  };
  const rescore = async () => {
    try { await employeeService.rescore(empId); addToast({ title: "Re-score queued", color: "success" }); }
    catch { addToast({ title: "Re-score failed (Celery offline?)", color: "warning" }); }
  };
  const doDelete = async () => {
    setDeleting(true);
    try { await employeeService.remove(empId); addToast({ title: "Employee deleted", color: "default" }); navigate("/admin/employees"); }
    catch { addToast({ title: "Delete failed (admin only?)", color: "danger" }); setDeleting(false); }
  };

  if (loading || !emp || !form) return <div style={{ padding: 40, color: T.ink4 }}>Loading…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 760 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Button variant="light" isIconOnly onPress={() => navigate(`/admin/employees/${empId}`)}><IconArrowLeft size={18} /></Button>
        <span style={{ width: 48, height: 48, borderRadius: "50%", display: "grid", placeItems: "center", background: T.accent50, color: T.accent, fontWeight: 700, fontSize: 17 }}>
          {initials(emp.full_name)}
        </span>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: T.ink, letterSpacing: "-0.02em" }}>{emp.full_name}</h1>
          <div style={{ fontSize: 13, color: T.ink3 }}>Employee information & settings</div>
        </div>
        <Button variant="bordered" size="sm" style={{ marginLeft: "auto" }} startContent={<IconBriefcase size={14} />}
          onPress={() => navigate(`/admin/employees/${empId}`)}>Back to jobs</Button>
      </div>

      {/* contact glance */}
      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 18, fontSize: 13, color: T.ink2 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><IconUser size={14} style={{ color: T.ink4 }} />{emp.position || "—"} · {SENIORITY_LABELS[emp.seniority] ?? emp.seniority}{emp.experience_years != null ? ` · ${emp.experience_years}y` : ""}</span>
          {emp.email && <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><IconMail size={14} style={{ color: T.ink4 }} />{emp.email}</span>}
          {emp.phone && <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><IconPhone size={14} style={{ color: T.ink4 }} />{emp.phone}</span>}
        </div>
      </Card>

      {/* email link section */}
      <section>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 8 }}>Email account</div>
        <EmailAccountCard employeeId={empId} />
      </section>

      {/* settings / edit */}
      <section>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.ink3, marginBottom: 8 }}>Settings</div>
        <Card>
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
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <Button color="primary" size="sm" startContent={<IconCheck size={14} />} isLoading={saving} onPress={save}>Save changes</Button>
            <Button variant="bordered" size="sm" startContent={<IconBriefcase size={14} />} isLoading={refreshing} onPress={refreshJobs}>Refresh jobs</Button>
            <Button variant="bordered" size="sm" startContent={<IconRefresh size={14} />} onPress={rescore}>Re-score (re-parse CV)</Button>
          </div>
        </Card>
      </section>

      {/* danger zone */}
      <section>
        <div style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: T.danger, marginBottom: 8 }}>Danger zone</div>
        <div style={{ border: `1px solid ${T.danger}`, borderRadius: 12, padding: "12px 14px", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, color: T.ink2 }}>Delete this employee and all their job matches. This cannot be undone.</span>
          <Button color="danger" size="sm" variant="flat" style={{ marginLeft: "auto" }} startContent={<IconTrash size={14} />} onPress={() => setDeleteOpen(true)}>Delete employee</Button>
        </div>
      </section>

      <Modal isOpen={deleteOpen} onOpenChange={(o) => !o && setDeleteOpen(false)} size="sm">
        <ModalContent>
          <ModalHeader>Delete employee</ModalHeader>
          <ModalBody className="text-sm">
            Permanently delete <span className="font-semibold">{emp.full_name}</span> and all their job matches? This cannot be undone.
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDeleteOpen(false)} isDisabled={deleting}>Cancel</Button>
            <Button color="danger" startContent={<IconTrash size={14} />} onPress={doDelete} isLoading={deleting}>Delete</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
