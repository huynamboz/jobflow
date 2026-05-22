import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Select, SelectItem } from "@heroui/select";
import { Tabs, Tab } from "@heroui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
} from "@heroui/table";
import { IconArrowLeft, IconRefresh } from "@tabler/icons-react";

import { EmployeeStatusChip } from "@/components/employee-status-chip";
import { MatchScoreBadge } from "@/components/match-score-badge";
import { MatchStatusChip } from "@/components/match-status-chip";
import { employeeService } from "@/services/employee.service";
import { matchService } from "@/services/match.service";
import type { Employee } from "@/types/employee.types";
import type { EmployeeJobMatch, MatchStatus } from "@/types/match.types";

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

  const updateStatus = async (matchId: number, status: MatchStatus) => {
    try {
      await matchService.update(matchId, { status });
      addToast({ title: "Match status updated", color: "success" });
      void reload();
    } catch {
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

      <Card>
        <CardHeader>Profile</CardHeader>
        <CardBody className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
          <div><span className="text-default-500">Email: </span>{employee.email || "—"}</div>
          <div><span className="text-default-500">Phone: </span>{employee.phone || "—"}</div>
          <div><span className="text-default-500">Position: </span>{employee.position || "—"}</div>
          <div><span className="text-default-500">Seniority: </span>{employee.seniority}</div>
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
                <TableColumn>Status</TableColumn>
                <TableColumn>Updated</TableColumn>
              </TableHeader>
              <TableBody items={matches} emptyContent={loading ? "Loading…" : "No matches"}>
                {(m) => (
                  <TableRow key={m.id}>
                    <TableCell>{m.job.title}</TableCell>
                    <TableCell className="text-xs text-default-500">{m.job.company_name ?? "—"}</TableCell>
                    <TableCell><MatchScoreBadge score={m.match_score} /></TableCell>
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
    </div>
  );
}
