import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
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
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Card } from "@/components/ui/card";
import { employeeService } from "@/services/employee.service";
import type { Employee } from "@/types/employee.types";

const T = {
  accent: "#167a7a", accent50: "#e8f4f4",
  success: "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger: "oklch(0.60 0.22 25)", danger50: "oklch(0.96 0.03 25)",
  warning: "oklch(0.62 0.13 70)", warning50: "oklch(0.97 0.04 75)",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface: "#ffffff", surface2: "oklch(0.97 0.005 85)", surface3: "oklch(0.945 0.006 85)",
  line: "rgba(226,232,240,0.7)",
};

const POLL_INTERVAL = 3000;
const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];
const MAX_FILES = 50;

type BadgeState = { label: string; bg: string; color: string; pulse?: boolean };

function badgeFor(emp: Employee, t: TFunction): BadgeState | null {
  const parsing = !emp.parsed_at && !emp.is_parse_failed;
  if (parsing) return { label: t("card.parsing"), bg: "#c8e5e5", color: "#0e5353", pulse: true };
  if (emp.is_parse_failed) return { label: t("card.parseFailed"), bg: T.danger50, color: T.danger };
  return null;
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
  const { t } = useTranslation("employees");
  const b = badgeFor(emp, t);
  const parsing = !emp.parsed_at && !emp.is_parse_failed;
  const skills = emp.skills ?? [];

  return (
    <Card hoverable onClick={onClick} style={{ position: "relative", overflow: "hidden" }}>
      {parsing && <span style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg,transparent,#167a7a,transparent)", backgroundSize: "200% 100%", animation: "jb-shimmer 1.6s linear infinite" }} />}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        {b ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600, background: b.bg, color: b.color }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", flexShrink: 0, animation: b.pulse ? "jb-pulse 1.4s ease-in-out infinite" : undefined }} />
            {b.label}
          </span>
        ) : <span />}
        <span style={{ fontFamily: "monospace", fontSize: 11, color: T.ink4 }}>{fmtDate(emp.created_at)}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span style={{ width: 44, height: 44, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: T.accent50, color: T.accent, fontWeight: 700, fontSize: 15 }}>
          {initials(emp.full_name)}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: T.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{emp.full_name}</div>
          <div style={{ fontSize: 12, color: T.ink3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {emp.position || (parsing ? t("card.readingCv") : "—")}{emp.email ? ` · ${emp.email}` : ""}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, minHeight: 24 }}>
        {parsing && skills.length === 0 ? (
          <span style={{ fontSize: 12, color: T.ink4, fontStyle: "italic" }}>{t("card.extractingSkills")}</span>
        ) : skills.length === 0 ? (
          <span style={{ fontSize: 12, color: T.ink4 }}>{t("card.noSkills")}</span>
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
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>{t("card.seniority")}</div>
          <div style={{ marginTop: 2, color: T.ink2, fontWeight: 600 }}>{SENIORITY_LABELS[emp.seniority] ?? emp.seniority}</div>
        </div>
        <div>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>{t("card.experience")}</div>
          <div style={{ marginTop: 2, color: T.ink2, fontWeight: 600 }}>{emp.experience_years != null ? t("card.experienceYears", { count: emp.experience_years }) : "—"}</div>
        </div>
        {emp.match_count ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, background: T.accent, color: "#fff" }}>
            <IconSparkles size={13} /> {t("card.newMatches", { count: emp.match_count })}
          </span>
        ) : (
          <span style={{ fontSize: 11.5, color: T.ink4 }}>—</span>
        )}
      </div>
    </Card>
  );
}

export default function EmployeesPage() {
  const { t } = useTranslation("employees");
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      const res = await employeeService.list(params as never);
      setEmployees(res.results);
      setTotal(res.count ?? res.results.length);
    } catch {
      addToast({ title: t("list.loadFailed"), color: "danger" });
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { void load(); }, [load]);

  // Live-poll while any employee is still being parsed in the background.
  const anyParsing = employees.some((e) => !e.parsed_at && !e.is_parse_failed);
  useEffect(() => {
    if (!anyParsing) return;
    const id = setInterval(load, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [anyParsing, load]);

  const withNewJobs = employees.filter((e) => (e.match_count ?? 0) > 0).length;
  const parsing = employees.filter((e) => !e.parsed_at && !e.is_parse_failed).length;

  const stats = [
    { label: t("stats.total"), value: total, unit: t("stats.totalUnit") },
    { label: t("stats.withNewJobs"), value: withNewJobs, unit: t("stats.withNewJobsUnit") },
    { label: t("stats.parsing"), value: parsing, unit: t("stats.parsingUnit"), accent: parsing > 0 },
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
            <span style={{ fontStyle: "italic", color: T.accent, fontWeight: 400 }}>{t("list.title")}</span>
          </h1>
          <p style={{ margin: "4px 0 0", color: T.ink3, fontSize: 14 }}>
            {t("list.subtitle")}
          </p>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <Button color="primary" startContent={<IconUserPlus size={14} />} onPress={() => setUploadOpen(true)}>
            {t("list.addEmployees")}
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
          placeholder={t("list.searchPlaceholder")}
          startContent={<IconSearch size={16} className="text-default-400" />}
          value={search}
          onValueChange={setSearch}
          className="max-w-xs"
          isClearable
          onClear={() => setSearch("")}
        />
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
              {search ? t("list.emptySearchTitle") : t("list.emptyTitle")}
            </div>
            <div style={{ fontSize: 13 }}>
              {search ? t("list.emptySearchHint") : t("list.emptyHint")}
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
  const { t } = useTranslation("employees");
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
        title: t("upload.addedToast", { count: res.data.length }),
        description: t("upload.addedToastDesc"),
        color: "success",
      });
      setFiles([]);
      onUploaded();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : t("upload.uploadFailed");
      addToast({ title: t("upload.uploadFailed"), description: message, color: "danger" });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onOpenChange={(open) => !open && onClose()} size="lg">
      <ModalContent>
        <ModalHeader style={{ fontWeight: 700, fontSize: 17 }}>{t("upload.title")}</ModalHeader>
        <ModalBody>
          <p style={{ fontSize: 13, color: T.ink3, margin: "0 0 8px" }}>
            {t("upload.description", { max: MAX_FILES })}
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
              {files.length ? t("upload.filesSelected", { count: files.length }) : t("upload.chooseFiles")}
            </span>
            <span style={{ fontSize: 12, color: T.ink4 }}>{t("upload.fileFormats")}</span>
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
          <Button variant="light" onPress={onClose} isDisabled={uploading}>{t("common:actions.cancel")}</Button>
          <Button color="primary" onPress={submit} isDisabled={!files.length || uploading} isLoading={uploading}>
            {t("upload.uploadButton")} {files.length || ""}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
