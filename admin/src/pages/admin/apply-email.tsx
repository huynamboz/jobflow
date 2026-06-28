import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { mailService } from "@/services/mail.service";
import { Input } from "@heroui/input";
import { Spinner } from "@heroui/spinner";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import { IconArrowLeft, IconBriefcase, IconBuilding, IconEye, IconFileText, IconMail, IconMailExclamation, IconMapPin, IconPaperclip, IconSparkles, IconTrash, IconUpload, IconUser } from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import { QuillEditor, type QuillHandle } from "@/components/quill-editor";
import { API_CONFIG, STORAGE_KEYS } from "@/config/api";
import { employeeService } from "@/services/employee.service";
import { jobService } from "@/services/job.service";
import { matchService } from "@/services/match.service";
import type { Employee } from "@/types/employee.types";
import type { JobDetail } from "@/types/job.types";

const T = {
  accent: "#167a7a",
  ink: "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3: "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface2: "oklch(0.97 0.005 85)",
};

function initials(name: string): string {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function draftBody(emp: Employee | null, job: JobDetail | null): string {
  const name = emp?.full_name || "the candidate";
  const role = job?.title || "the role";
  const company = job?.company?.name ? ` at ${job.company.name}` : "";
  const skills = (emp?.skills ?? []).slice(0, 6).join(", ");
  return [
    `<p>Dear Hiring Manager,</p>`,
    `<p>I'm writing to apply for the <strong>${role}</strong> position${company}.`,
    skills ? ` I bring hands-on experience with ${skills}, and I'm confident I would be a strong fit for your team.` : ``,
    `</p>`,
    `<p>I've attached my CV and would welcome the chance to discuss how I can contribute.</p>`,
    `<p>Best regards,<br/>${name}${emp?.email ? `<br/>${emp.email}` : ""}${emp?.phone ? ` · ${emp.phone}` : ""}</p>`,
  ].join("");
}

export default function ApplyEmailPage() {
  const { t } = useTranslation("mail");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const employeeId = Number(params.get("employee"));
  const jobId = Number(params.get("job"));
  const matchId = Number(params.get("match"));

  const [emp, setEmp] = useState<Employee | null>(null);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [to, setTo] = useState("");
  const [linked, setLinked] = useState(false);
  const [linkedAddr, setLinkedAddr] = useState("");
  const [credChecked, setCredChecked] = useState(false);
  const [sending, setSending] = useState(false);
  const [subject, setSubject] = useState("");
  const [bodyHTML, setBodyHTML] = useState("");
  const bodyText = useRef("");
  const [marking, setMarking] = useState(false);
  const [generating, setGenerating] = useState(false);
  const editorRef = useRef<QuillHandle>(null);

  // Attachment: HR can preview, remove, or replace the CV that gets attached.
  const [customCv, setCustomCv] = useState<File | null>(null);
  const [cvRemoved, setCvRemoved] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const customCvUrl = useMemo(() => (customCv ? URL.createObjectURL(customCv) : ""), [customCv]);
  useEffect(() => () => { if (customCvUrl) URL.revokeObjectURL(customCvUrl); }, [customCvUrl]);

  // Effective attachment: uploaded file wins, else the employee's active CV
  // (unless HR removed it).
  const empCvName = emp?.cv_file ? decodeURIComponent(emp.cv_file.split("/").pop() || "CV.pdf") : "";
  const attachName = customCv ? customCv.name : (cvRemoved ? "" : empCvName);
  const attachUrl = customCv ? customCvUrl : (cvRemoved ? "" : (emp?.cv_file || ""));
  const hasAttachment = !!attachName;

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) { setCustomCv(f); setCvRemoved(false); }
    e.target.value = "";
  };
  const removeAttachment = () => { setCustomCv(null); setCvRemoved(true); };

  useEffect(() => {
    let alive = true;
    Promise.all([
      employeeId ? employeeService.get(employeeId) : Promise.resolve(null),
      jobId ? jobService.getJob(jobId) : Promise.resolve(null),
    ])
      .then(([e, j]) => {
        if (!alive) return;
        setEmp(e);
        setJob(j);
        setSubject(j
          ? (e
            ? t("compose.applicationSubjectWithName", { title: j.title, name: e.full_name })
            : t("compose.applicationSubject", { title: j.title }))
          : t("compose.applicationSubjectFallback"));
        setBodyHTML(draftBody(e, j));
      })
      .catch(() => alive && addToast({ title: t("composeToast.loadFailed"), color: "danger" }))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [employeeId, jobId]);

  // 026: load linked-email status to enable in-system Send.
  useEffect(() => {
    if (!employeeId) return;
    mailService.credentialStatus(employeeId)
      .then((c) => { setLinked(!!c.linked && c.status === "active"); setLinkedAddr(c.gmail_address || ""); })
      .catch(() => setLinked(false))
      .finally(() => setCredChecked(true));
  }, [employeeId]);

  // 026: send the application from the employee's linked Gmail, with CV attached.
  const sendFromSystem = async () => {
    if (!matchId || !to) { addToast({ title: t("composeToast.recipientRequired"), color: "warning" }); return; }
    const body = bodyText.current || bodyHTML.replace(/<[^>]+>/g, " ");
    setSending(true);
    try {
      const r = await mailService.sendApply(matchId, to, subject, body, {
        cvFile: customCv,
        noCv: cvRemoved && !customCv,
      });
      addToast({ title: t("composeToast.sentApplied"), description: r.cv_attached ? t("composeToast.sentWithCv") : t("composeToast.sentNoCv"), color: "success" });
      navigate(-1);
    } catch (e: any) {
      const msg = e?.response?.data?.error?.message || t("composeToast.sendFailed");
      addToast({ title: t("composeToast.sendFailed"), description: msg, color: "danger" });
    } finally {
      setSending(false);
    }
  };

  const onEditorChange = useCallback((html: string, text: string) => {
    setBodyHTML(html);
    bodyText.current = text;
  }, []);

  // Stream an LLM-written draft straight into the editor.
  const generateEmail = async () => {
    if (!employeeId || !jobId || generating) return;
    setGenerating(true);
    editorRef.current?.setText("");
    try {
      const token = localStorage.getItem(STORAGE_KEYS.accessToken);
      const resp = await fetch(`${API_CONFIG.baseURL}/admin/application-email/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ employee: employeeId, job: jobId }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        editorRef.current?.setText(acc);
      }
      bodyText.current = acc;
    } catch {
      addToast({ title: t("composeToast.generateFailed"), description: t("composeToast.generateFailedHint"), color: "danger" });
    } finally {
      setGenerating(false);
    }
  };

  const openInGmail = async () => {
    const body = bodyText.current || bodyHTML.replace(/<[^>]+>/g, " ");
    const url =
      "https://mail.google.com/mail/?view=cm&fs=1" +
      (to ? `&to=${encodeURIComponent(to)}` : "") +
      `&su=${encodeURIComponent(subject)}` +
      `&body=${encodeURIComponent(body)}`;
    window.open(url, "_blank", "noopener,noreferrer");

    // Opening the email IS the apply action → mark the match applied.
    if (matchId) {
      setMarking(true);
      try {
        await matchService.update(matchId, { status: "applied" });
        addToast({ title: t("composeToast.openedGmailApplied"), description: t("composeToast.openedGmailAppliedHint"), color: "success" });
      } catch {
        addToast({ title: t("composeToast.openedGmailNotApplied"), color: "warning" });
      } finally {
        setMarking(false);
      }
    }
  };

  if (loading) {
    return <div style={{ display: "grid", placeItems: "center", height: 300 }}><Spinner /></div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Button variant="light" isIconOnly onPress={() => navigate(-1)}><IconArrowLeft size={18} /></Button>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: T.ink, letterSpacing: "-0.02em" }}>{t("compose.title")}</h1>
          <p style={{ fontSize: 13, color: T.ink3, margin: 0 }}>{t("compose.subtitle")}</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 320px) 1fr", gap: 16, alignItems: "start" }}>
        {/* left: context */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
              <span style={{ width: 42, height: 42, borderRadius: "50%", display: "grid", placeItems: "center", background: "#e8f4f4", color: T.accent, fontWeight: 700, fontSize: 14 }}>
                {initials(emp?.full_name || "?")}
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: T.ink }}>{emp?.full_name || "—"}</div>
                <div style={{ fontSize: 12, color: T.ink3 }}>{emp?.position || "—"}</div>
              </div>
            </div>
            <div style={{ fontSize: 12.5, color: T.ink2, display: "flex", flexDirection: "column", gap: 4 }}>
              {emp?.email && <span><IconMail size={12} style={{ display: "inline", marginRight: 5, color: T.ink4 }} />{emp.email}</span>}
              {emp?.phone && <span><IconUser size={12} style={{ display: "inline", marginRight: 5, color: T.ink4 }} />{emp.phone}</span>}
            </div>
            {!!(emp?.skills?.length) && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 10 }}>
                {emp!.skills.slice(0, 10).map((s) => (
                  <span key={s} style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 500, background: T.surface2, color: T.ink2 }}>{s}</span>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.ink, marginBottom: 6 }}>{job?.title || "—"}</div>
            <div style={{ fontSize: 12.5, color: T.ink2, display: "flex", flexDirection: "column", gap: 4 }}>
              {job?.company?.name && <span><IconBuilding size={12} style={{ display: "inline", marginRight: 5, color: T.ink4 }} />{job.company.name}</span>}
              {job?.location && <span><IconMapPin size={12} style={{ display: "inline", marginRight: 5, color: T.ink4 }} />{job.location}</span>}
              {job?.seniority != null && <span><IconBriefcase size={12} style={{ display: "inline", marginRight: 5, color: T.ink4 }} />{t("compose.seniority", { level: job.seniority })}</span>}
            </div>
            {job?.source_url && (
              <a href={job.source_url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 10, fontSize: 12.5, fontWeight: 600, color: T.accent, textDecoration: "none" }}>
                {t("compose.viewPosting")}
              </a>
            )}
          </Card>
        </div>

        {/* right: composer */}
        <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Gửi từ — the linked Gmail the email is sent from */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 12, background: T.surface2, border: `1px solid ${T.line}` }}>
            <IconMail size={15} style={{ color: T.ink4, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: T.ink3 }}>{t("compose.fromLabel")}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: linked ? T.ink : T.ink4 }}>
              {linkedAddr || t("compose.fromNotLinked")}
            </span>
          </div>

          <Input size="sm" label={t("compose.toLabel")} placeholder={t("compose.toPlaceholder")} value={to} onValueChange={setTo} type="email" />
          <Input size="sm" label={t("compose.subjectLabel")} value={subject} onValueChange={setSubject} />

          {/* Attachment — preview / remove / replace the CV PDF */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.ink3, marginBottom: 6 }}>{t("compose.attachmentLabel")}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {hasAttachment ? (
                <button type="button" onClick={() => setPreviewOpen(true)}
                  style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 12, border: `1px solid ${T.line}`, background: T.surface, cursor: "pointer", maxWidth: "100%" }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, display: "grid", placeItems: "center", background: "#fde8e8", color: "#dc2626", flexShrink: 0 }}>
                    <IconFileText size={16} />
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>{attachName}</span>
                  <IconEye size={15} style={{ color: T.accent, flexShrink: 0 }} />
                </button>
              ) : (
                <span style={{ fontSize: 12.5, color: T.ink4, fontStyle: "italic" }}>{t("compose.attachmentNone")}</span>
              )}
              {hasAttachment && (
                <Button size="sm" variant="light" color="danger" isIconOnly onPress={removeAttachment} title={t("compose.attachmentRemove")}>
                  <IconTrash size={15} />
                </Button>
              )}
              <Button size="sm" variant="flat" startContent={<IconUpload size={14} />} onPress={() => fileInputRef.current?.click()}>
                {hasAttachment ? t("compose.attachmentReplace") : t("compose.attachmentUpload")}
              </Button>
              <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={onPickFile} />
            </div>
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.ink3 }}>{t("compose.message")}</div>
              <Button size="sm" variant="flat" color="primary" startContent={<IconSparkles size={14} />} isLoading={generating} onPress={generateEmail}>
                {generating ? t("compose.generating") : t("compose.generateEmail")}
              </Button>
            </div>
            <QuillEditor ref={editorRef} initialHTML={bodyHTML} placeholder={t("compose.editorPlaceholder")} onChange={onEditorChange} minHeight={300} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, color: T.ink3 }}>
              {linked ? t("compose.sendFromHint", { addr: linkedAddr }) : t("compose.linkToSendHint")}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <Button variant="light" onPress={() => navigate(-1)}>{t("common:actions.cancel")}</Button>
              <Button variant="flat" startContent={<IconMail size={16} />} isLoading={marking} onPress={openInGmail}>
                {t("compose.openInGmail")}
              </Button>
              <Button color="primary" startContent={<IconMail size={16} />} isDisabled={!linked} isLoading={sending} onPress={sendFromSystem}>
                {t("compose.send")}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* 026: block compose if the employee has no linked Gmail */}
      <Modal isOpen={credChecked && !linked && !!employeeId} hideCloseButton isDismissable={false} isKeyboardDismissDisabled size="md">
        <ModalContent>
          <ModalHeader className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-xl bg-warning/10 text-warning">
              <IconMailExclamation size={20} stroke={1.75} />
            </span>
            {t("linkModal.title")}
          </ModalHeader>
          <ModalBody className="text-sm text-default-600">
            <p>
              {t("linkModal.bodyPrefix")}<span className="font-semibold text-foreground">{emp?.full_name || t("linkModal.thisEmployee")}</span>{t("linkModal.bodySuffix")}
            </p>
            <p className="text-xs text-default-400">
              {t("linkModal.hint")}
            </p>
          </ModalBody>
          <ModalFooter>
            <Button variant="light" startContent={<IconArrowLeft size={16} />} onPress={() => navigate(-1)}>{t("linkModal.back")}</Button>
            <Button color="primary" startContent={<IconMail size={16} />}
              onPress={() => navigate(`/admin/employees/${employeeId}/info`)}>{t("linkModal.linkEmail")}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Attachment preview — large PDF viewer */}
      <Modal isOpen={previewOpen} onOpenChange={setPreviewOpen} size="5xl" scrollBehavior="inside">
        <ModalContent>
          <ModalHeader className="flex items-center gap-2">
            <IconPaperclip size={18} className="text-default-500" />
            <span className="truncate">{attachName}</span>
          </ModalHeader>
          <ModalBody className="p-0">
            {attachUrl
              ? <iframe src={attachUrl} title={attachName} className="h-[78vh] w-full border-0" />
              : <div className="grid h-[40vh] place-items-center text-default-400">{t("compose.attachmentNone")}</div>}
          </ModalBody>
          <ModalFooter>
            <Button size="sm" variant="flat" startContent={<IconUpload size={14} />} onPress={() => fileInputRef.current?.click()}>
              {t("compose.attachmentReplace")}
            </Button>
            {hasAttachment && (
              <Button size="sm" variant="light" color="danger" startContent={<IconTrash size={14} />}
                onPress={() => { removeAttachment(); setPreviewOpen(false); }}>
                {t("compose.attachmentRemove")}
              </Button>
            )}
            <Button size="sm" color="primary" onPress={() => setPreviewOpen(false)}>{t("common:actions.close")}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
