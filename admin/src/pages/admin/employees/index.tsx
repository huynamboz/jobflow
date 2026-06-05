import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Card, CardBody } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import { Spinner } from "@heroui/spinner";
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
} from "@heroui/modal";
import {
  IconAlertTriangle,
  IconChevronRight,
  IconCloudUpload,
  IconSearch,
  IconSparkles,
  IconUserPlus,
  IconUsers,
} from "@tabler/icons-react";

import { EmployeeStatusChip } from "@/components/employee-status-chip";
import { employeeService } from "@/services/employee.service";
import type { Employee, EmployeeStatus } from "@/types/employee.types";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

const STATUS_OPTS: { key: EmployeeStatus | "all"; label: string }[] = [
  { key: "all", label: "All statuses" },
  { key: "bench", label: "On bench" },
  { key: "pursuing", label: "Pursuing" },
  { key: "placed", label: "Placed" },
  { key: "inactive", label: "Inactive" },
];

const MAX_FILES = 50;

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function StatTile({ label, value, tone = "default" }: { label: string; value: number; tone?: string }) {
  const toneText: Record<string, string> = {
    default: "text-foreground",
    primary: "text-primary-600",
    warning: "text-warning-600",
    success: "text-success-700",
  };
  return (
    <Card shadow="sm" radius="lg">
      <CardBody className="px-4 py-3">
        <div className={`text-xl font-bold leading-none ${toneText[tone]}`}>{value}</div>
        <div className="mt-1 text-xs font-medium text-default-500">{label}</div>
      </CardBody>
    </Card>
  );
}

function EmployeeRow({ emp, onClick }: { emp: Employee; onClick: () => void }) {
  const skills = emp.skills ?? [];
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full cursor-pointer items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-default-50"
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary-100 text-sm font-semibold text-primary-700">
        {initials(emp.full_name)}
      </span>

      {/* identity */}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium text-foreground">{emp.full_name}</span>
          {emp.is_parse_failed && (
            <Chip size="sm" color="warning" variant="flat" startContent={<IconAlertTriangle size={12} />}>
              parse failed
            </Chip>
          )}
        </span>
        <span className="block truncate text-xs text-default-500">
          {emp.position || "—"}{emp.email ? ` · ${emp.email}` : ""}
        </span>
      </span>

      {/* skills (hidden on small) */}
      <span className="hidden max-w-[280px] flex-wrap gap-1 lg:flex">
        {skills.slice(0, 3).map((s) => (
          <Chip key={s} size="sm" variant="flat">{s}</Chip>
        ))}
        {skills.length > 3 && (
          <span className="self-center text-xs text-default-400">+{skills.length - 3}</span>
        )}
      </span>

      {/* meta */}
      <span className="hidden w-16 shrink-0 text-right text-xs text-default-500 sm:block">
        {SENIORITY_LABELS[emp.seniority] ?? emp.seniority}
      </span>
      <span className="w-24 shrink-0 text-right">
        {emp.match_count ? (
          <Chip size="sm" color="primary" variant="flat" startContent={<IconSparkles size={12} />}>
            {emp.match_count} new
          </Chip>
        ) : (
          <span className="text-default-300">—</span>
        )}
      </span>
      <span className="hidden w-20 shrink-0 sm:flex sm:justify-end">
        <EmployeeStatusChip status={emp.status} />
      </span>
      <IconChevronRight size={16} className="shrink-0 text-default-300 transition-colors group-hover:text-default-500" />
    </button>
  );
}

export default function EmployeesPage() {
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<EmployeeStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (status !== "all") params.status = status;
      if (search) params.search = search;
      const res = await employeeService.list(params as never);
      setEmployees(res.results);
      setTotal(res.count ?? res.results.length);
    } catch {
      addToast({ title: "Failed to load employees", color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  useEffect(() => { void load(); }, [load]);

  const onBench = employees.filter((e) => e.status === "bench").length;
  const withNewJobs = employees.filter((e) => (e.match_count ?? 0) > 0).length;
  const parseErrors = employees.filter((e) => e.is_parse_failed).length;

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">Employees</h1>
            <Chip size="sm" variant="flat">{total}</Chip>
          </div>
          <p className="mt-1 text-sm text-default-500">
            Your company's bench — upload CVs, review matches, drive applications.
          </p>
        </div>
        <Button color="primary" startContent={<IconUserPlus size={16} />} onPress={() => setUploadOpen(true)}>
          Add employees
        </Button>
      </div>

      {/* summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Loaded" value={employees.length} />
        <StatTile label="On bench" value={onBench} tone="primary" />
        <StatTile label="With new jobs" value={withNewJobs} tone="success" />
        <StatTile label="Parse errors" value={parseErrors} tone={parseErrors ? "warning" : "default"} />
      </div>

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search name, email, position…"
          startContent={<IconSearch size={16} className="text-default-400" />}
          value={search}
          onValueChange={setSearch}
          className="max-w-xs"
          isClearable
          onClear={() => setSearch("")}
        />
        <Select
          aria-label="Filter by status"
          size="md"
          selectedKeys={[status]}
          onSelectionChange={(keys) => setStatus(Array.from(keys)[0] as EmployeeStatus | "all")}
          className="max-w-[180px]"
        >
          {STATUS_OPTS.map((opt) => (
            <SelectItem key={opt.key}>{opt.label}</SelectItem>
          ))}
        </Select>
      </div>

      {/* list */}
      <Card radius="lg">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16"><Spinner /></div>
          ) : employees.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-default-100 text-default-400">
                <IconUsers size={22} />
              </span>
              <p className="text-sm font-medium text-foreground">No employees found</p>
              <p className="max-w-sm text-xs text-default-500">
                {search || status !== "all"
                  ? "Try clearing the search or status filter."
                  : "Click “Add employees” to upload CVs — they'll be parsed and matched automatically."}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-default-100">
              {employees.map((emp) => (
                <li key={emp.id}>
                  <EmployeeRow emp={emp} onClick={() => navigate(`/admin/employees/${emp.id}`)} />
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <BulkUploadModal
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => { setUploadOpen(false); void load(); }}
      />
    </div>
  );
}

function BulkUploadModal({
  isOpen,
  onClose,
  onUploaded,
}: {
  isOpen: boolean;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);

  const onPick = (list: FileList | null) => {
    if (!list) return;
    const arr = Array.from(list).slice(0, MAX_FILES);
    setFiles(arr);
  };

  const submit = async () => {
    if (!files.length) return;
    setUploading(true);
    try {
      const res = await employeeService.bulkUpload(files);
      addToast({
        title: `Queued ${res.data.length} employees`,
        description: "Parsing + matching in background. List will refresh.",
        color: "success",
      });
      setFiles([]);
      onUploaded();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Upload failed";
      addToast({ title: "Upload failed", description: message, color: "danger" });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onOpenChange={(open) => !open && onClose()} size="lg">
      <ModalContent>
        <ModalHeader>Add employees (bulk)</ModalHeader>
        <ModalBody>
          <p className="text-sm text-default-500">
            Pick PDF/DOCX files (max {MAX_FILES}). Each becomes a new Employee record;
            CV is parsed + matched in background.
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => onPick(e.target.files)}
            className="hidden"
          />
          <div className="flex flex-col gap-2">
            <Button
              variant="bordered"
              startContent={<IconCloudUpload size={16} />}
              onPress={() => inputRef.current?.click()}
            >
              {files.length ? `${files.length} files selected` : "Choose files"}
            </Button>
            {files.length > 0 && (
              <ul className="text-xs text-default-600 max-h-40 overflow-auto">
                {files.map((f) => (
                  <li key={f.name}>{f.name} ({(f.size / 1024).toFixed(0)} KB)</li>
                ))}
              </ul>
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose} isDisabled={uploading}>Cancel</Button>
          <Button color="primary" onPress={submit} isDisabled={!files.length || uploading} isLoading={uploading}>
            Upload {files.length || ""}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
