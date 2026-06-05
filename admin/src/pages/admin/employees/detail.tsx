import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Input, Textarea } from "@heroui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@heroui/popover";
import { Select, SelectItem } from "@heroui/select";
import { Tabs, Tab } from "@heroui/tabs";
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
} from "@heroui/modal";
import {
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
} from "@heroui/table";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconInfoCircle,
  IconPencil,
  IconRefresh,
} from "@tabler/icons-react";

import { EmployeeStatusChip } from "@/components/employee-status-chip";
import { MatchScoreBadge } from "@/components/match-score-badge";
import { MatchStatusChip } from "@/components/match-status-chip";
import { employeeService } from "@/services/employee.service";
import { matchService } from "@/services/match.service";
import type { DuplicateApplyError, DuplicateApplyFrontman } from "@/services/match.service";
import type { Employee } from "@/types/employee.types";
import type { EmployeeJobMatch, MatchStatus } from "@/types/match.types";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

interface EditForm {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  seniority: number;
  experience_years: string;
  skills: string; // comma-separated for editing
  notes: string;
}

function toForm(e: Employee): EditForm {
  return {
    full_name: e.full_name ?? "",
    email: e.email ?? "",
    phone: e.phone ?? "",
    position: e.position ?? "",
    seniority: e.seniority ?? 2,
    experience_years: e.experience_years != null ? String(e.experience_years) : "",
    skills: (e.skills ?? []).join(", "),
    notes: e.notes ?? "",
  };
}

/** Human-readable seniority gap (job_seniority - employee_seniority). */
function seniorityGapLabel(gap: number | null): string {
  if (gap === null || gap === undefined) return "Seniority data unavailable";
  if (gap === 0) return "Matches required seniority";
  if (gap > 0) return `Job needs ${gap} level(s) higher`;
  return `Employee is ${-gap} level(s) higher`;
}

/** Explainability popover: matched / missing skills + seniority gap. */
function WhyMatch({ match }: { match: EmployeeJobMatch }) {
  return (
    <Popover placement="left" showArrow>
      <PopoverTrigger>
        <Button size="sm" variant="light" isIconOnly aria-label="Why it matches">
          <IconInfoCircle size={16} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-w-xs">
        <div className="space-y-2 p-1 text-xs">
          <p className="font-semibold">Why it matches</p>
          <div>
            <span className="text-default-500">Matched skills: </span>
            <div className="mt-1 flex flex-wrap gap-1">
              {(match.matched_skills ?? []).map((s) => (
                <Chip key={s} size="sm" color="success" variant="flat">{s}</Chip>
              ))}
              {!match.matched_skills?.length && <span className="text-default-400">none</span>}
            </div>
          </div>
          <div>
            <span className="text-default-500">Missing skills: </span>
            <div className="mt-1 flex flex-wrap gap-1">
              {(match.missing_skills ?? []).map((s) => (
                <Chip key={s} size="sm" color="danger" variant="flat">{s}</Chip>
              ))}
              {!match.missing_skills?.length && (
                <span className="text-success">meets all required skills</span>
              )}
            </div>
          </div>
          <div>
            <span className="text-default-500">Seniority: </span>
            <span>{seniorityGapLabel(match.seniority_gap)}</span>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

const MATCH_STATUSES: { key: MatchStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "suggested", label: "Suggested" },
  { key: "pursuing", label: "Pursuing" },
  { key: "applied", label: "Applied" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const empId = Number(id);
  const navigate = useNavigate();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [matches, setMatches] = useState<EmployeeJobMatch[]>([]);
  const [activeTab, setActiveTab] = useState<MatchStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [dup, setDup] = useState<{ matchId: number; frontman: DuplicateApplyFrontman } | null>(null);
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [emp, m] = await Promise.all([
        employeeService.get(empId),
        matchService.list({ employee: empId, ...(activeTab !== "all" ? { status: activeTab } : {}) }),
      ]);
      setEmployee(emp);
      setMatches(m.results);
    } catch {
      addToast({ title: "Failed to load employee", color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [empId, activeTab]);

  useEffect(() => { void reload(); }, [reload]);

  const updateStatus = async (
    matchId: number,
    status: MatchStatus,
    confirmDuplicate = false,
  ) => {
    try {
      await matchService.update(matchId, { status, confirm_duplicate: confirmDuplicate });
      addToast({ title: "Match status updated", color: "success" });
      setDup(null);
      void reload();
    } catch (e: unknown) {
      const resp = (e as { response?: { status?: number; data?: { error?: DuplicateApplyError } } })
        .response;
      if (resp?.status === 409 && resp.data?.error?.code === "DUPLICATE_APPLY") {
        // US3: another employee already fronts this job — ask HR to confirm.
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

  const startEdit = () => employee && setForm(toForm(employee));
  const cancelEdit = () => setForm(null);

  const saveEdit = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const skills = form.skills
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const exp = form.experience_years.trim();
      await employeeService.update(empId, {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        position: form.position.trim(),
        seniority: form.seniority,
        experience_years: exp === "" ? null : Number(exp),
        skills,
        notes: form.notes,
      });
      addToast({ title: "Employee updated", color: "success" });
      setForm(null);
      void reload();
    } catch {
      addToast({ title: "Update failed", color: "danger" });
    } finally {
      setSaving(false);
    }
  };

  if (loading && !employee) return <p>Loading…</p>;
  if (!employee) return <p>Employee not found.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="light" isIconOnly onPress={() => navigate("/admin/employees")}>
          <IconArrowLeft size={18} />
        </Button>
        <h1 className="text-2xl font-bold">{employee.full_name}</h1>
        <EmployeeStatusChip status={employee.status} />
        <div className="ml-auto flex gap-2">
          <Button variant="bordered" size="sm" startContent={<IconRefresh size={14} />} onPress={rescore}>
            Re-score
          </Button>
        </div>
      </div>

      {employee.is_parse_failed && !form && (
        <Card className="border border-warning-300 bg-warning-50">
          <CardBody className="flex flex-row items-center gap-3 text-sm text-warning-700">
            <IconAlertTriangle size={18} />
            <span className="flex-1">
              CV could not be parsed — enter skills &amp; details manually so it can be matched.
            </span>
            <Button size="sm" color="warning" variant="flat" startContent={<IconPencil size={14} />} onPress={startEdit}>
              Edit manually
            </Button>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span>Profile</span>
          {!form ? (
            <Button size="sm" variant="light" startContent={<IconPencil size={14} />} onPress={startEdit}>
              Edit
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button size="sm" variant="light" onPress={cancelEdit} isDisabled={saving}>Cancel</Button>
              <Button size="sm" color="primary" onPress={saveEdit} isLoading={saving}>Save</Button>
            </div>
          )}
        </CardHeader>
        {!form ? (
          <CardBody className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
            <div><span className="text-default-500">Email: </span>{employee.email || "—"}</div>
            <div><span className="text-default-500">Phone: </span>{employee.phone || "—"}</div>
            <div><span className="text-default-500">Position: </span>{employee.position || "—"}</div>
            <div>
              <span className="text-default-500">Seniority: </span>
              {SENIORITY_LABELS[employee.seniority] ?? employee.seniority}
            </div>
            <div><span className="text-default-500">Experience: </span>{employee.experience_years ?? "—"} years</div>
            <div className="md:col-span-2">
              <span className="text-default-500">Skills: </span>
              <div className="mt-1 flex flex-wrap gap-1">
                {(employee.skills ?? []).map((s) => (
                  <Chip key={s} size="sm" variant="flat">{s}</Chip>
                ))}
                {!employee.skills?.length && <span className="text-default-400">none parsed</span>}
              </div>
            </div>
            {employee.cv_file && (
              <div className="md:col-span-2">
                <a href={employee.cv_file} target="_blank" rel="noreferrer" className="text-primary text-xs underline">
                  Download CV
                </a>
              </div>
            )}
          </CardBody>
        ) : (
          <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Input size="sm" label="Full name" value={form.full_name}
              onValueChange={(v) => setForm({ ...form, full_name: v })} />
            <Input size="sm" label="Email" value={form.email}
              onValueChange={(v) => setForm({ ...form, email: v })} />
            <Input size="sm" label="Phone" value={form.phone}
              onValueChange={(v) => setForm({ ...form, phone: v })} />
            <Input size="sm" label="Position" value={form.position}
              onValueChange={(v) => setForm({ ...form, position: v })} />
            <Select
              size="sm"
              label="Seniority"
              selectedKeys={[String(form.seniority)]}
              onSelectionChange={(keys) =>
                setForm({ ...form, seniority: Number(Array.from(keys)[0]) })
              }
            >
              {SENIORITY_LABELS.map((label, i) => (
                <SelectItem key={String(i)}>{label}</SelectItem>
              ))}
            </Select>
            <Input size="sm" type="number" label="Experience (years)" value={form.experience_years}
              onValueChange={(v) => setForm({ ...form, experience_years: v })} />
            <div className="md:col-span-2">
              <Input size="sm" label="Skills (comma-separated)" value={form.skills}
                onValueChange={(v) => setForm({ ...form, skills: v })} />
              <div className="mt-1 flex flex-wrap gap-1">
                {form.skills.split(",").map((s) => s.trim()).filter(Boolean).map((s) => (
                  <Chip key={s} size="sm" variant="flat">{s}</Chip>
                ))}
              </div>
            </div>
            <Textarea size="sm" label="Notes" className="md:col-span-2" value={form.notes}
              onValueChange={(v) => setForm({ ...form, notes: v })} />
          </CardBody>
        )}
      </Card>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span>Matches</span>
        </CardHeader>
        <CardBody>
          <Tabs
            selectedKey={activeTab}
            onSelectionChange={(k) => setActiveTab(k as MatchStatus | "all")}
            size="sm"
          >
            {MATCH_STATUSES.map((s) => <Tab key={s.key} title={s.label} />)}
          </Tabs>

          <div className="mt-3">
            <Table aria-label="Matches" removeWrapper>
              <TableHeader>
                <TableColumn>Job</TableColumn>
                <TableColumn>Company</TableColumn>
                <TableColumn>Score</TableColumn>
                <TableColumn>Why</TableColumn>
                <TableColumn>Status</TableColumn>
                <TableColumn>Updated</TableColumn>
              </TableHeader>
              <TableBody items={matches} emptyContent={loading ? "Loading…" : "No matches"}>
                {(m) => (
                  <TableRow key={m.id}>
                    <TableCell>{m.job.title}</TableCell>
                    <TableCell className="text-xs text-default-500">{m.job.company_name ?? "—"}</TableCell>
                    <TableCell><MatchScoreBadge score={m.match_score} /></TableCell>
                    <TableCell><WhyMatch match={m} /></TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <MatchStatusChip status={m.status} />
                        <Select
                          aria-label="Change status"
                          size="sm"
                          selectedKeys={[m.status]}
                          onSelectionChange={(keys) => {
                            const next = Array.from(keys)[0] as MatchStatus;
                            if (next !== m.status) void updateStatus(m.id, next);
                          }}
                          className="min-w-[120px]"
                        >
                          <SelectItem key="suggested">Suggested</SelectItem>
                          <SelectItem key="pursuing">Pursuing</SelectItem>
                          <SelectItem key="applied">Applied</SelectItem>
                          <SelectItem key="won">Won</SelectItem>
                          <SelectItem key="lost">Lost</SelectItem>
                        </Select>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-default-500">
                      {new Date(m.updated_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardBody>
      </Card>

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
            <Button
              color="warning"
              onPress={() => dup && void updateStatus(dup.matchId, "applied", true)}
            >
              Apply anyway
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
