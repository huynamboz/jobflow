import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { addToast } from "@heroui/toast";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import {
  IconFileTypePdf, IconUpload, IconTrash, IconCheck, IconDownload,
  IconAlertTriangle, IconLoader2, IconStar, IconEye,
} from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import { employeeService, type EmployeeCV } from "@/services/employee.service";

const SENIORITY_LABELS = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"];

function summary(cv: EmployeeCV): string {
  const bits = [
    cv.position || null,
    SENIORITY_LABELS[cv.seniority] ?? null,
    cv.experience_years != null ? `${cv.experience_years}y` : null,
    `${cv.skills_count} skills`,
  ].filter(Boolean);
  return bits.join(" · ");
}

/** 027: a candidate can hold several CV versions; one is active (used for
 *  ranking). Upload parses a version without switching; HR selects one. */
export default function CvVersionsCard({ employeeId, onChanged }: { employeeId: number; onChanged?: () => void }) {
  const [cvs, setCvs] = useState<EmployeeCV[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [viewer, setViewer] = useState<EmployeeCV | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try { setCvs(await employeeService.listCvs(employeeId)); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, [employeeId]);
  useEffect(() => { void load(); }, [load]);

  // poll while any version is still parsing
  useEffect(() => {
    if (!cvs.some((c) => c.parsing)) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [cvs, load]);

  const onPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await employeeService.uploadCv(employeeId, file);
      addToast({ title: "CV uploaded — parsing…", color: "success" });
      await load();
    } catch (err: any) {
      addToast({ title: "Upload failed", description: err?.response?.data?.error?.message || "", color: "danger" });
    } finally { setUploading(false); }
  };

  const activate = async (cv: EmployeeCV) => {
    setBusyId(cv.id);
    try {
      await employeeService.activateCv(employeeId, cv.id);
      addToast({ title: "Now using this version", description: "Job matches are refreshing in the background.", color: "success" });
      await load();
      onChanged?.();
    } catch (err: any) {
      addToast({ title: "Couldn't activate", description: err?.response?.data?.error?.message || "", color: "danger" });
    } finally { setBusyId(null); }
  };

  const remove = async (cv: EmployeeCV) => {
    setBusyId(cv.id);
    try {
      await employeeService.deleteCv(employeeId, cv.id);
      addToast({ title: "Version deleted", color: "default" });
      await load();
    } catch (err: any) {
      addToast({ title: "Couldn't delete", description: err?.response?.data?.error?.message || "", color: "danger" });
    } finally { setBusyId(null); }
  };

  const isPdf = (cv: EmployeeCV | null) => !!cv && (cv.filename || cv.cv_file).toLowerCase().endsWith(".pdf");

  return (
    <>
    <Card padding={20} className="space-y-3">
      <div className="flex items-center gap-2">
        <IconFileTypePdf size={16} className="text-default-400" stroke={1.75} />
        <h3 className="text-sm font-semibold text-foreground">CV versions</h3>
        {cvs.length > 0 && <Chip size="sm" variant="flat" className="ml-1">{cvs.length}</Chip>}
        <input ref={fileRef} type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={onPick} />
        <Button size="sm" color="primary" className="ml-auto"
          startContent={!uploading && <IconUpload size={15} />} isLoading={uploading}
          onPress={() => fileRef.current?.click()}>Upload CV</Button>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[0, 1].map((i) => <div key={i} className="h-16 animate-pulse rounded-xl bg-default-100" />)}
        </div>
      ) : cvs.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <div className="grid size-12 place-items-center rounded-2xl bg-default-100 text-default-400">
            <IconFileTypePdf size={24} stroke={1.5} />
          </div>
          <div className="text-sm font-medium text-default-500">No CV yet</div>
          <p className="max-w-xs text-xs text-default-400">Upload the first CV — it'll be used for ranking automatically.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {cvs.map((cv) => {
            const busy = busyId === cv.id;
            return (
              <div key={cv.id}
                className={`flex items-center gap-3 rounded-xl border bg-white p-3 transition-colors ${
                  cv.is_active ? "border-default-200 border-l-[3px] border-l-primary" : "border-default-100 hover:bg-default-50"}`}>
                <IconFileTypePdf size={22} stroke={1.75} className={`shrink-0 ${
                  cv.is_parse_failed ? "text-danger" : cv.is_active ? "text-primary" : "text-default-400"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-semibold text-foreground" title={cv.label || cv.filename}>
                      {cv.label || cv.filename || `CV #${cv.id}`}
                    </span>
                    {cv.is_active && <Chip size="sm" variant="flat" color="success" startContent={<IconStar size={12} />}>In use</Chip>}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-default-500">
                    {cv.parsing
                      ? <span className="inline-flex items-center gap-1 text-default-400"><IconLoader2 size={13} className="animate-spin" />Parsing…</span>
                      : cv.is_parse_failed
                        ? <span className="inline-flex items-center gap-1 text-danger"><IconAlertTriangle size={13} />Parse failed</span>
                        : summary(cv)}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {cv.cv_file && (
                    <Button isIconOnly size="sm" variant="light" title="View"
                      onPress={() => setViewer(cv)}>
                      <IconEye size={16} className="text-default-500" />
                    </Button>
                  )}
                  {cv.cv_file && (
                    <Button isIconOnly size="sm" variant="light" title="Download"
                      onPress={() => window.open(cv.cv_file, "_blank", "noopener")}>
                      <IconDownload size={16} className="text-default-500" />
                    </Button>
                  )}
                  {!cv.is_active && (
                    <Button size="sm" variant="bordered" color="primary" isLoading={busy}
                      isDisabled={cv.parsing || cv.is_parse_failed}
                      startContent={!busy && <IconCheck size={14} />} onPress={() => activate(cv)}>
                      Use
                    </Button>
                  )}
                  {!cv.is_active && (
                    <Button isIconOnly size="sm" variant="light" color="danger" title="Delete" isLoading={busy}
                      onPress={() => remove(cv)}>
                      <IconTrash size={16} />
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>

    <Modal isOpen={!!viewer} onOpenChange={(o) => !o && setViewer(null)} size="5xl" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader className="flex items-center gap-2">
          <IconFileTypePdf size={18} className="text-default-400" />
          <span className="truncate text-sm">{viewer?.label || viewer?.filename || "CV"}</span>
        </ModalHeader>
        <ModalBody className="p-0">
          {isPdf(viewer) ? (
            <iframe key={viewer?.id} src={viewer?.cv_file} title="CV preview" className="h-[78vh] w-full border-0" />
          ) : (
            <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
              <div className="grid size-12 place-items-center rounded-2xl bg-default-100 text-default-400">
                <IconFileTypePdf size={24} stroke={1.5} />
              </div>
              <div className="text-sm font-medium text-default-500">Preview only available for PDF</div>
              <p className="text-xs text-default-400">Download the file to open it.</p>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={() => setViewer(null)}>Close</Button>
          {viewer?.cv_file && (
            <Button color="primary" startContent={<IconDownload size={15} />}
              onPress={() => window.open(viewer.cv_file, "_blank", "noopener")}>Download</Button>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
    </>
  );
}
