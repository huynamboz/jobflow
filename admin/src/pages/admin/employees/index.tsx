import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
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
  IconCloudUpload,
  IconLoader2,
  IconSearch,
  IconSparkles,
  IconUserPlus,
  IconUsers,
} from "@tabler/icons-react";

import { employeeService } from "@/services/employee.service";
import type { Employee, EmployeeStatus } from "@/types/employee.types";

const T = {
  accent: "oklch(0.55 0.20 240)", accent50: "oklch(0.97 0.03 240)",
  success: "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger: "oklch(0.60 0.22 25)", danger50: "oklch(0.96 0.03 25)",
  warning: "oklch(0.62 0.13 70)", warning50: "oklch(0.97 0.04 75)",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface: "#ffffff", surface2: "oklch(0.97 0.005 85)", surface3: "oklch(0.945 0.006 85)",
  line: "oklch(0.92 0.006 85)",
};

const POLL_INTERVAL = 3000;
const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];
const MAX_FILES = 50;

const STATUS_OPTS: { key: EmployeeStatus | "all"; label: string }[] = [
  { key: "all", label: "All statuses" },
  { key: "bench", label: "On bench" },
  { key: "pursuing", label: "Pursuing" },
  { key: "placed", label: "Placed" },
  { key: "inactive", label: "Inactive" },
];

type BadgeState = { label: string; bg: string; color: string; pulse?: boolean };

function badgeFor(emp: Employee): BadgeState {
  const parsing = !emp.parsed_at && !emp.is_parse_failed;
  if (parsing) return { label: "Parsing…", bg: "oklch(0.93 0.05 240)", color: "oklch(0.42 0.16 240)", pulse: true };
  if (emp.is_parse_failed) return { label: "Parse failed", bg: T.danger50, color: T.danger };
  const map: Record<string, BadgeState> = {
    bench: { label: "On bench", bg: T.surface3, color: T.ink2 },
    pursuing: { label: "Pursuing", bg: "oklch(0.93 0.05 240)", color: "oklch(0.42 0.16 240)" },
    placed: { label: "Placed", bg: T.success50, color: T.success },
    inactive: { label: "Inactive", bg: T.surface3, color: T.ink4 },
  };
  return map[emp.status] ?? map.bench;
}

function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN", { dateStyle: "short" });
}

function EmployeeCard({ emp, onClick }: { emp: Employee; onClick: () => void }) {
  const b = badgeFor(emp);
  const parsing = !emp.parsed_at && !emp.is_parse_failed;
  const skills = emp.skills ?? [];

  return (
    <div className="jb-card-hover" onClick={onClick} style={{
      background: T.surface, border: `1px solid ${T.line}`,
      borderRadius: 20, padding: 18, cursor: "pointer",
      transition: "transform 0.14s, box-shadow 0.14s", position: "relative", overflow: "hidden",
    }}>
      {parsing && <span style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg,transparent,oklch(0.55 0.20 240),transparent)", backgroundSize: "200% 100%", animation: "jb-shimmer 1.6s linear infinite" }} />}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600, background: b.bg, color: b.color }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", flexShrink: 0, animation: b.pulse ? "jb-pulse 1.4s ease-in-out infinite" : undefined }} />
          {b.label}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: T.ink4 }}>{fmtDate(emp.created_at)}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span style={{ width: 44, height: 44, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: T.accent50, color: T.accent, fontWeight: 700, fontSize: 15 }}>
          {initials(emp.full_name)}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: T.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{emp.full_name}</div>
          <div style={{ fontSize: 12, color: T.ink3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {emp.position || (parsing ? "reading CV…" : "—")}{emp.email ? ` · ${emp.email}` : ""}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, minHeight: 24 }}>
        {parsing && skills.length === 0 ? (
          <span style={{ fontSize: 12, color: T.ink4, fontStyle: "italic" }}>Extracting skills…</span>
        ) : skills.length === 0 ? (
          <span style={{ fontSize: 12, color: T.ink4 }}>No skills parsed</span>
        ) : (
          <>
            {skills.slice(0, 5).map((s) => (
              <span key={s} style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11.5, fontWeight: 500, background: T.surface2, color: T.ink2 }}>{s}</span>
            ))}
            {skills.length > 5 && <span style={{ fontSize: 11.5, color: T.ink4, alignSelf: "center" }}>+{skills.length - 5}</span>}
          </>
        )}
      </div>

      <div style={{ height: 1, background: T.line, margin: "12px 0" }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8, fontSize: 11.5, alignItems: "center" }}>
        <div>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>Seniority</div>
          <div style={{ marginTop: 2, color: T.ink2, fontWeight: 600 }}>{SENIORITY_LABELS[emp.seniority] ?? emp.seniority}</div>
        </div>
        <div>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>Experience</div>
          <div style={{ marginTop: 2, color: T.ink2, fontWeight: 600 }}>{emp.experience_years != null ? `${emp.experience_years}y` : "—"}</div>
        </div>
        {emp.match_count ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, background: T.accent, color: "#fff" }}>
            <IconSparkles size={13} /> {emp.match_count} new
          </span>
        ) : (
          <span style={{ fontSize: 11.5, color: T.ink4 }}>—</span>
        )}
      </div>
    </div>
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

  // Live-poll while any employee is still being parsed in the background.
  const anyParsing = employees.some((e) => !e.parsed_at && !e.is_parse_failed);
  useEffect(() => {
    if (!anyParsing) return;
    const id = setInterval(load, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [anyParsing, load]);

  const onBench = employees.filter((e) => e.status === "bench").length;
  const withNewJobs = employees.filter((e) => (e.match_count ?? 0) > 0).length;
  const parsing = employees.filter((e) => !e.parsed_at && !e.is_parse_failed).length;

  const stats = [
    { label: "Total", value: total, unit: "employees" },
    { label: "On bench", value: onBench, unit: "available" },
    { label: "With new jobs", value: withNewJobs, unit: "to review" },
    { label: "Parsing", value: parsing, unit: "in progress", accent: parsing > 0 },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <style>{`
        @keyframes jb-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes jb-pulse   { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes jb-spin    { to{transform:rotate(360deg)} }
        .jb-card-hover:hover { transform:translateY(-2px); box-shadow:0 2px 4px rgba(20,18,30,.04),0 8px 24px rgba(20,18,30,.06); }
      `}</style>

      <div style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.025em", margin: 0, color: T.ink }}>
            Employee <span style={{ fontStyle: "italic", color: T.accent, fontWeight: 400 }}>Bench</span>
          </h1>
          <p style={{ margin: "4px 0 0", color: T.ink3, fontSize: 14 }}>
            Upload CVs, review AI-parsed profiles and matched jobs.
          </p>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <Button color="primary" startContent={<IconUserPlus size={14} />} onPress={() => setUploadOpen(true)}>
            Add employees
          </Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
        {stats.map((s) => (
          <div key={s.label} style={{
            background: s.accent ? T.accent : T.surface, border: `1px solid ${s.accent ? T.accent : T.line}`,
            borderRadius: 16, padding: "14px 16px", color: s.accent ? "#fff" : T.ink,
          }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: s.accent ? "rgba(255,255,255,0.75)" : T.ink3 }}>{s.label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.02em", marginTop: 4, display: "flex", alignItems: "baseline", gap: 6 }}>
              {s.value}
              <span style={{ fontSize: 13, fontWeight: 500, color: s.accent ? "rgba(255,255,255,0.7)" : T.ink3 }}>{s.unit}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
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
          selectedKeys={[status]}
          onSelectionChange={(keys) => setStatus(Array.from(keys)[0] as EmployeeStatus | "all")}
          className="max-w-[180px]"
        >
          {STATUS_OPTS.map((opt) => <SelectItem key={opt.key}>{opt.label}</SelectItem>)}
        </Select>
      </div>

      {loading ? (
        <div style={{ display: "grid", placeItems: "center", height: 200, color: T.ink3 }}>
          <IconLoader2 size={22} style={{ animation: "jb-spin 0.7s linear infinite" }} />
        </div>
      ) : employees.length === 0 ? (
        <div style={{ display: "grid", placeItems: "center", height: 280, color: T.ink3 }}>
          <div style={{ textAlign: "center" }}>
            <IconUsers size={32} style={{ margin: "0 auto 12px", color: T.ink4 }} />
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              {search || status !== "all" ? "No matching employees" : "No employees yet"}
            </div>
            <div style={{ fontSize: 13 }}>
              {search || status !== "all" ? "Try clearing the search or status filter." : "Click “Add employees” to upload CVs — they're parsed automatically."}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))", gap: 14 }}>
          {employees.map((emp) => (
            <EmployeeCard key={emp.id} emp={emp} onClick={() => navigate(`/admin/employees/${emp.id}`)} />
          ))}
        </div>
      )}

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
    setFiles(Array.from(list).slice(0, MAX_FILES));
  };

  const submit = async () => {
    if (!files.length) return;
    setUploading(true);
    try {
      const res = await employeeService.bulkUpload(files);
      addToast({
        title: `Added ${res.data.length} employee${res.data.length > 1 ? "s" : ""}`,
        description: "CVs are being parsed in the background — profiles update automatically.",
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
        <ModalHeader style={{ fontWeight: 700, fontSize: 17 }}>Add employees</ModalHeader>
        <ModalBody>
          <p style={{ fontSize: 13, color: T.ink3, margin: "0 0 8px" }}>
            Pick PDF/DOCX CVs (max {MAX_FILES}). Each becomes an employee; the CV
            is parsed by AI in the background — you don't need to wait here.
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => onPick(e.target.files)}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
              width: "100%", padding: "28px 16px", borderRadius: 16, cursor: "pointer",
              border: `1.5px dashed ${files.length ? T.accent : T.line}`,
              background: files.length ? T.accent50 : T.surface2, transition: "all 0.14s",
            }}
          >
            <IconCloudUpload size={26} style={{ color: files.length ? T.accent : T.ink4 }} />
            <span style={{ fontSize: 13.5, fontWeight: 600, color: T.ink2 }}>
              {files.length ? `${files.length} file${files.length > 1 ? "s" : ""} selected` : "Choose CV files"}
            </span>
            <span style={{ fontSize: 12, color: T.ink4 }}>PDF or DOCX</span>
          </button>
          {files.length > 0 && (
            <ul style={{ fontSize: 12, color: T.ink3, maxHeight: 140, overflow: "auto", margin: "10px 0 0", paddingLeft: 4 }}>
              {files.map((f) => (
                <li key={f.name} style={{ padding: "2px 0" }}>{f.name} · {(f.size / 1024).toFixed(0)} KB</li>
              ))}
            </ul>
          )}
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
