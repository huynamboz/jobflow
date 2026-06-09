import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Select, SelectItem } from "@heroui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
} from "@heroui/table";

import { MatchScoreBadge } from "@/components/match-score-badge";
import { MatchStatusChip } from "@/components/match-status-chip";
import { matchService } from "@/services/match.service";
import type { EmployeeJobMatch, MatchStatus, PipelineKpi } from "@/types/match.types";

const STATUSES: { key: MatchStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "suggested", label: "Suggested" },
  { key: "pursuing", label: "Pursuing" },
  { key: "applied", label: "Applied" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

export default function PipelinePage() {
  const navigate = useNavigate();
  const [matches, setMatches] = useState<EmployeeJobMatch[]>([]);
  const [kpi, setKpi] = useState<PipelineKpi | null>(null);
  const [status, setStatus] = useState<MatchStatus | "all">("all");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, k] = await Promise.all([
        matchService.list(status !== "all" ? { status } : {}),
        matchService.kpi(),
      ]);
      setMatches(list.results);
      setKpi(k);
    } catch {
      addToast({ title: "Failed to load pipeline", color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Pipeline</h1>
        <p className="text-sm text-default-500">All employee × job matches across the company.</p>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Employees"     value={kpi?.total_employees ?? 0}            tone="default" />
        <KpiCard label="Pursuing (7d)" value={kpi?.matches_this_week?.pursuing ?? 0} tone="primary" />
        <KpiCard label="Applied (7d)"  value={kpi?.matches_this_week?.applied ?? 0}  tone="secondary" />
        <KpiCard label="Accepted (7d)" value={kpi?.matches_this_week?.won ?? 0}      tone="success" />
      </div>

      <Card>
        <CardHeader className="flex items-center gap-3">
          <span>Filter</span>
          <Select
            label="Status"
            size="sm"
            selectedKeys={[status]}
            onSelectionChange={(keys) => setStatus(Array.from(keys)[0] as MatchStatus | "all")}
            className="max-w-[200px]"
          >
            {STATUSES.map((s) => <SelectItem key={s.key}>{s.label}</SelectItem>)}
          </Select>
        </CardHeader>
        <CardBody className="p-0">
          <Table aria-label="Pipeline" removeWrapper>
            <TableHeader>
              <TableColumn>Employee</TableColumn>
              <TableColumn>Job</TableColumn>
              <TableColumn>Company</TableColumn>
              <TableColumn>Score</TableColumn>
              <TableColumn>Status</TableColumn>
              <TableColumn>Updated</TableColumn>
            </TableHeader>
            <TableBody items={matches} emptyContent={loading ? "Loading…" : "No matches"}>
              {(m) => (
                <TableRow
                  key={m.id}
                  className="cursor-pointer hover:bg-default-50"
                  onClick={() => navigate(`/admin/employees/${m.employee}`)}
                >
                  <TableCell>{m.employee_name}</TableCell>
                  <TableCell>{m.job.title}</TableCell>
                  <TableCell className="text-xs text-default-500">{m.job.company_name ?? "—"}</TableCell>
                  <TableCell><MatchScoreBadge score={m.match_score} /></TableCell>
                  <TableCell><MatchStatusChip status={m.status} /></TableCell>
                  <TableCell className="text-xs text-default-500">
                    {new Date(m.updated_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardBody>
      </Card>
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "default" | "primary" | "secondary" | "success";
}) {
  const palette: Record<string, string> = {
    default: "text-default-700",
    primary: "text-primary",
    secondary: "text-secondary",
    success: "text-success",
  };
  return (
    <Card>
      <CardBody className="text-center">
        <p className={`text-3xl font-bold ${palette[tone]}`}>{value}</p>
        <p className="text-xs uppercase tracking-wider text-default-500">{label}</p>
      </CardBody>
    </Card>
  );
}
