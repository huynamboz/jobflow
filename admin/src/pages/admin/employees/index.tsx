import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Card, CardBody } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
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
import { IconCloudUpload, IconSearch, IconUserPlus } from "@tabler/icons-react";

import { EmployeeStatusChip } from "@/components/employee-status-chip";
import { employeeService } from "@/services/employee.service";
import type { Employee, EmployeeStatus } from "@/types/employee.types";

const STATUS_OPTS: { key: EmployeeStatus | "all"; label: string }[] = [
  { key: "all", label: "All statuses" },
  { key: "bench", label: "On bench" },
  { key: "pursuing", label: "Pursuing" },
  { key: "placed", label: "Placed" },
  { key: "inactive", label: "Inactive" },
];

const MAX_FILES = 50;

export default function EmployeesPage() {
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
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
    } catch (e) {
      addToast({ title: "Failed to load employees", color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Employees</h1>
          <p className="text-sm text-default-500">
            Manage your company's bench — upload CVs, track placements.
          </p>
        </div>
        <Button color="primary" startContent={<IconUserPlus size={16} />} onPress={() => setUploadOpen(true)}>
          Add employees
        </Button>
      </div>

      <Card>
        <CardBody className="flex flex-row gap-3">
          <Input
            placeholder="Search by name, email, position"
            startContent={<IconSearch size={16} />}
            value={search}
            onValueChange={setSearch}
            className="max-w-xs"
          />
          <Select
            label="Status"
            size="sm"
            selectedKeys={[status]}
            onSelectionChange={(keys) => setStatus(Array.from(keys)[0] as EmployeeStatus | "all")}
            className="max-w-[200px]"
          >
            {STATUS_OPTS.map((opt) => (
              <SelectItem key={opt.key}>{opt.label}</SelectItem>
            ))}
          </Select>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="p-0">
          <Table aria-label="Employees" removeWrapper>
            <TableHeader>
              <TableColumn>Name</TableColumn>
              <TableColumn>Position</TableColumn>
              <TableColumn>Skills</TableColumn>
              <TableColumn>Status</TableColumn>
              <TableColumn>Matches</TableColumn>
              <TableColumn>Created</TableColumn>
            </TableHeader>
            <TableBody
              items={employees}
              isLoading={loading}
              loadingContent="Loading…"
              emptyContent="No employees yet. Click 'Add employees' to upload CVs."
            >
              {(emp) => (
                <TableRow
                  key={emp.id}
                  onClick={() => navigate(`/admin/employees/${emp.id}`)}
                  className="cursor-pointer hover:bg-default-50"
                >
                  <TableCell>
                    <p className="font-medium">{emp.full_name}</p>
                    <p className="text-xs text-default-500">{emp.email || "—"}</p>
                  </TableCell>
                  <TableCell>{emp.position || "—"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {(emp.skills ?? []).slice(0, 4).map((s) => (
                        <Chip key={s} size="sm" variant="flat">{s}</Chip>
                      ))}
                      {(emp.skills ?? []).length > 4 && (
                        <span className="text-xs text-default-400 self-center">
                          +{emp.skills.length - 4}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell><EmployeeStatusChip status={emp.status} /></TableCell>
                  <TableCell>{emp.match_count ?? 0}</TableCell>
                  <TableCell className="text-xs text-default-500">
                    {new Date(emp.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
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
