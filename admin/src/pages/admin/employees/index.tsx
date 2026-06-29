import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addToast } from "@heroui/toast";
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
  IconSparkles,
  IconUserPlus,
  IconUsers,
  IconMail,
  IconPhone,
  IconCalendar,
  IconMessage,
  IconDots,
  IconDownload,
  IconPlus,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { Avatar, Badge, Button, Card, PageHeader, SearchInput, useReveal } from "@/components/ui";
import type { BadgeColor } from "@/components/ui";
import { cn } from "@/lib/utils";
import { employeeService } from "@/services/employee.service";
import type { Employee } from "@/types/employee.types";

const POLL_INTERVAL = 3000;
const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];
const MAX_FILES = 50;

// Soft cover gradients assigned deterministically per employee for visual variety.
const COVERS = [
  "linear-gradient(120deg,#E8F1FE,#DCEBFF)",
  "linear-gradient(120deg,#F2ECFB,#EADFF8)",
  "linear-gradient(120deg,#E7F6EF,#D5EFE2)",
  "linear-gradient(120deg,#FBF1DC,#F8E9C8)",
  "linear-gradient(120deg,#E2F5F5,#D2EFEF)",
  "linear-gradient(120deg,#FCEDEA,#F7DDD7)",
];

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN", { dateStyle: "short" });
}

type Status = { label: string; color: "amber" | "red" | "green"; pulse?: boolean };
function statusFor(emp: Employee, t: TFunction): Status {
  if (!emp.parsed_at && !emp.is_parse_failed) return { label: t("card.parsing"), color: "amber", pulse: true };
  if (emp.is_parse_failed) return { label: t("card.parseFailed"), color: "red" };
  return { label: t("card.ready"), color: "green" };
}

// Seniority → coloured chip (mirrors the mockup's department pill).
const SENIORITY_TINT: BadgeColor[] = ["neutral", "blue", "green", "violet", "amber", "red"];

/** Small square action button on the card footer (message / call). Renders as
 *  an <a> when `href` is given (e.g. tel:) so we never nest a button in a link. */
function CardIconBtn({
  children,
  onClick,
  title,
  href,
}: {
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title?: string;
  href?: string;
}) {
  const cls =
    "grid h-[42px] w-[42px] shrink-0 place-items-center rounded-jn-btn border border-jn-line-3 bg-jn-surface text-jn-ink-mute transition-colors hover:bg-jn-sunken";
  if (href) {
    return (
      <a href={href} title={title} onClick={onClick} className={cls}>
        {children}
      </a>
    );
  }
  return (
    <button type="button" title={title} onClick={onClick} className={cls}>
      {children}
    </button>
  );
}

function EmployeeCard({ emp, onClick }: { emp: Employee; onClick: () => void }) {
  const { t } = useTranslation("employees");
  const st = statusFor(emp, t);
  const parsing = !emp.parsed_at && !emp.is_parse_failed;
  const cover = COVERS[emp.id % COVERS.length];
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <Card radius="lg" padding={0} hoverable onClick={onClick} className="jn-reveal relative overflow-hidden">
      {parsing && (
        <span
          className="absolute inset-x-0 top-0 z-20 h-[3px]"
          style={{
            background: "linear-gradient(90deg,transparent,#0064E5,transparent)",
            backgroundSize: "200% 100%",
            animation: "jb-shimmer 1.6s linear infinite",
          }}
        />
      )}

      {/* cover + more */}
      <div className="relative h-[74px]" style={{ background: cover }}>
        <button
          type="button"
          onClick={stop}
          className="absolute right-3 top-3 grid h-[30px] w-[30px] place-items-center rounded-[9px] bg-white/85 text-jn-ink-mute transition-colors hover:bg-white"
        >
          <IconDots size={16} />
        </button>
      </div>

      <div className="relative z-[1] -mt-[38px] px-6 pb-6">
        {/* avatar — 76px with 4px white ring (matches mockup) */}
        <div
          className="w-fit rounded-full"
          style={{ border: "4px solid #fff", boxShadow: "0 4px 14px rgba(0,0,0,.1)" }}
        >
          <Avatar name={emp.full_name} size={68} />
        </div>

        {/* name + status */}
        <div className="mt-3.5 flex items-center gap-2.5">
          <span className="truncate text-[18px] font-bold tracking-[-0.01em] text-jn-ink">{emp.full_name}</span>
          <Badge color={st.color} dot className={cn(st.pulse && "[&>span:first-child]:animate-pulse")}>
            {st.label}
          </Badge>
        </div>

        {/* role */}
        <div className="mt-1 truncate text-[13.5px] text-jn-ink-mute">
          {emp.position || (parsing ? t("card.readingCv") : "—")}
        </div>

        {/* seniority pill + id */}
        <div className="mt-2.5 flex items-center gap-2.5">
          <Badge color={SENIORITY_TINT[emp.seniority] ?? "neutral"} dot>
            {SENIORITY_LABELS[emp.seniority] ?? emp.seniority}
          </Badge>
          {emp.experience_years != null && (
            <span className="text-[12px] text-jn-muted">{t("card.experienceYears", { count: emp.experience_years })}</span>
          )}
          <span className="ml-auto font-mono text-[12px] text-jn-faint">
            {t("card.empId", { id: String(emp.id).padStart(4, "0") })}
          </span>
        </div>

        <div className="my-[18px] h-px bg-jn-line-soft" />

        {/* contact rows */}
        <div className="flex flex-col gap-[11px]">
          <ContactRow icon={<IconMail size={15} />} truncate>
            {emp.email || "—"}
          </ContactRow>
          <ContactRow icon={<IconPhone size={15} />}>{emp.phone || t("card.noPhone")}</ContactRow>
          <ContactRow icon={<IconSparkles size={15} />}>
            {emp.match_count ? (
              <span className="font-semibold text-jn-primary">{t("card.newMatches", { count: emp.match_count })}</span>
            ) : (
              <span className="text-jn-muted">{t("card.noMatches")}</span>
            )}
          </ContactRow>
          <ContactRow icon={<IconCalendar size={15} />}>{t("card.joined", { date: fmtDate(emp.created_at) })}</ContactRow>
        </div>

        {/* actions */}
        <div className="mt-5 flex gap-2.5">
          <Button variant="primary" className="flex-1" onClick={(e) => { stop(e); onClick(); }}>
            {t("card.viewProfile")}
          </Button>
          <CardIconBtn title="Message" onClick={(e) => { stop(e); onClick(); }}>
            <IconMessage size={16} />
          </CardIconBtn>
          {emp.phone ? (
            <CardIconBtn title="Call" href={`tel:${emp.phone}`} onClick={stop}>
              <IconPhone size={16} />
            </CardIconBtn>
          ) : (
            <CardIconBtn title="Call" onClick={(e) => { stop(e); onClick(); }}>
              <IconPhone size={16} />
            </CardIconBtn>
          )}
        </div>
      </div>
    </Card>
  );
}

function ContactRow({ icon, children, truncate }: { icon: React.ReactNode; children: React.ReactNode; truncate?: boolean }) {
  return (
    <div className="flex items-center gap-[11px] text-[13px] text-jn-ink-soft">
      <span className="flex shrink-0 text-jn-muted">{icon}</span>
      <span className={cn("min-w-0", truncate && "truncate")}>{children}</span>
    </div>
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
  const reveal = useReveal([employees]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => { void load(); }, [load]);

  // Live-poll while any employee is still being parsed in the background.
  const anyParsing = employees.some((e) => !e.parsed_at && !e.is_parse_failed);
  useEffect(() => {
    if (!anyParsing) return;
    const id = setInterval(load, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [anyParsing, load]);

  const exportCsv = () => {
    const head = ["id", "full_name", "email", "phone", "position", "seniority", "experience_years", "skills", "match_count", "created_at"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = employees.map((e) =>
      [e.id, e.full_name, e.email, e.phone ?? "", e.position, SENIORITY_LABELS[e.seniority] ?? e.seniority,
       e.experience_years ?? "", (e.skills ?? []).join("; "), e.match_count ?? 0, e.created_at].map(esc).join(","),
    );
    const blob = new Blob(["﻿" + [head.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `employees-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div ref={reveal} className="flex flex-col gap-5">
      <style>{`
        @keyframes jb-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes jb-spin    { to{transform:rotate(360deg)} }
      `}</style>

      <PageHeader
        className="jn-reveal"
        title={t("list.title")}
        pill={<Badge color="blue">{t("stats.totalUnitCount", { count: total })}</Badge>}
        subtitle={t("list.subtitle")}
        actions={
          <>
            <Button variant="secondary" leftIcon={<IconDownload size={15} />} onClick={exportCsv} disabled={!employees.length}>
              {t("list.export")}
            </Button>
            <Button variant="primary" leftIcon={<IconUserPlus size={15} />} onClick={() => setUploadOpen(true)}>
              {t("list.addEmployees")}
            </Button>
          </>
        }
      />

      <SearchInput
        className="jn-reveal max-w-sm"
        placeholder={t("list.searchPlaceholder")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {loading ? (
        <div className="grid h-[200px] place-items-center text-jn-muted">
          <IconLoader2 size={22} className="animate-spin" />
        </div>
      ) : employees.length === 0 ? (
        <div className="grid h-[280px] place-items-center text-center text-jn-ink-mute">
          <div>
            <IconUsers size={32} className="mx-auto mb-3 text-jn-faint" />
            <div className="mb-1 font-semibold text-jn-ink">{search ? t("list.emptySearchTitle") : t("list.emptyTitle")}</div>
            <div className="text-[13px] text-jn-muted">{search ? t("list.emptySearchHint") : t("list.emptyHint")}</div>
          </div>
        </div>
      ) : (
        <div className="grid gap-[22px]" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}>
          {employees.map((emp) => (
            <EmployeeCard key={emp.id} emp={emp} onClick={() => navigate(`/admin/employees/${emp.id}`)} />
          ))}

          {/* add-member card */}
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="jn-reveal flex min-h-[300px] flex-col items-center justify-center gap-3.5 rounded-jn-card-lg border-[1.5px] border-dashed border-jn-line-3 text-jn-muted transition-colors hover:border-jn-primary-border hover:bg-jn-primary-soft/40 hover:text-jn-primary"
          >
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-jn-sunken text-current">
              <IconPlus size={26} />
            </span>
            <div className="text-center">
              <div className="text-[14.5px] font-bold text-jn-ink-soft">{t("list.addEmployees")}</div>
              <div className="mt-0.5 text-[12.5px]">{t("upload.fileFormats")}</div>
            </div>
          </button>
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
        <ModalHeader className="text-[17px] font-bold text-jn-ink">{t("upload.title")}</ModalHeader>
        <ModalBody>
          <p className="mb-2 text-[13px] text-jn-ink-mute">{t("upload.description", { max: MAX_FILES })}</p>
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
            className={cn(
              "flex w-full flex-col items-center gap-2 rounded-jn-card border-[1.5px] border-dashed px-4 py-7 transition-colors",
              files.length ? "border-jn-primary bg-jn-primary-soft/50" : "border-jn-line-3 bg-jn-sunken",
            )}
          >
            <IconCloudUpload size={26} className={files.length ? "text-jn-primary" : "text-jn-faint"} />
            <span className="text-[13.5px] font-semibold text-jn-ink-soft">
              {files.length ? t("upload.filesSelected", { count: files.length }) : t("upload.chooseFiles")}
            </span>
            <span className="text-[12px] text-jn-faint">{t("upload.fileFormats")}</span>
          </button>
          {files.length > 0 && (
            <ul className="mt-2.5 max-h-[140px] overflow-auto pl-1 text-[12px] text-jn-ink-mute">
              {files.map((f) => (
                <li key={f.name} className="py-0.5">{f.name} · {(f.size / 1024).toFixed(0)} KB</li>
              ))}
            </ul>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={onClose} disabled={uploading}>{t("common:actions.cancel")}</Button>
          <Button variant="primary" onClick={submit} disabled={!files.length || uploading} loading={uploading}>
            {t("upload.uploadButton")} {files.length || ""}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
