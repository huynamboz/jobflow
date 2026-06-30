import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { addToast } from "@heroui/toast";
import { Button } from "@heroui/button";
import { mailService } from "@/services/mail.service";
import { Input, Textarea } from "@heroui/input";
import { Spinner } from "@heroui/spinner";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";
import { IconArrowLeft, IconArrowRight, IconEye, IconFileText, IconLoader2, IconMail, IconMailExclamation, IconPaperclip, IconSparkles, IconTrash, IconUpload } from "@tabler/icons-react";

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

// small uppercase section label
const LABEL: CSSProperties = {
  fontSize: 10.5, fontWeight: 700, textTransform: "uppercase",
  letterSpacing: "0.05em", color: "oklch(0.72 0.008 265)", marginBottom: 7,
};

function initials(name: string): string {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

/** Company avatar — real logo (object-cover) with a neutral-initial fallback. */
function CompanyAvatar({ logo, name, size = 46 }: { logo?: string; name?: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const radius = Math.round(size * 0.3);
  if (logo && !failed) {
    return (
      <img
        src={logo}
        alt=""
        onError={() => setFailed(true)}
        style={{ width: size, height: size, borderRadius: radius, objectFit: "cover", background: "#fff", border: "1px solid #ECECEE", flexShrink: 0 }}
      />
    );
  }
  return (
    <span style={{ width: size, height: size, borderRadius: radius, display: "grid", placeItems: "center", background: "#F2F2F2", border: "1px solid #ECECEE", color: T.ink3, fontWeight: 800, fontSize: size * 0.36, flexShrink: 0 }}>
      {(name || "?").charAt(0).toUpperCase()}
    </span>
  );
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
  const [feedback, setFeedback] = useState("");
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

  // Stream an LLM-written draft straight into the editor. When `withFeedback`
  // is set, send the current draft + HR's feedback so the LLM revises it.
  const generateEmail = async (withFeedback = false) => {
    if (!employeeId || !jobId || generating) return;
    const fb = withFeedback ? feedback.trim() : "";
    if (withFeedback && !fb) return;
    const currentDraft = bodyText.current || "";
    setGenerating(true);
    editorRef.current?.setText("");
    try {
      const token = localStorage.getItem(STORAGE_KEYS.accessToken);
      const resp = await fetch(`${API_CONFIG.baseURL}/admin/application-email/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          employee: employeeId, job: jobId,
          ...(fb ? { feedback: fb, current_draft: currentDraft } : {}),
        }),
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
      if (fb) setFeedback("");
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
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 900, marginInline: "auto", width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Button variant="light" isIconOnly onPress={() => navigate(-1)}><IconArrowLeft size={18} /></Button>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: T.ink, letterSpacing: "-0.02em" }}>{t("compose.title")}</h1>
          <p style={{ fontSize: 13, color: T.ink3, margin: 0 }}>{t("compose.subtitle")}</p>
        </div>
      </div>

      {/* Who is applying to which job — the only context HR needs here */}
      <Card padding={16}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          {/* employee */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: "1 1 220px" }}>
            <span style={{ width: 44, height: 44, borderRadius: 13, display: "grid", placeItems: "center", background: "#e8f4f4", color: T.accent, fontWeight: 800, fontSize: 15, flexShrink: 0 }}>
              {initials(emp?.full_name || "?")}
            </span>
            <div style={{ minWidth: 0 }}>
              <div style={LABEL}>{t("compose.applicant")}</div>
              <div style={{ fontWeight: 700, fontSize: 15, color: T.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{emp?.full_name || "—"}</div>
              <div style={{ fontSize: 12.5, color: T.ink3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{emp?.position || "—"}</div>
            </div>
          </div>

          {/* applying-to */}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 999, background: "#e8f4f4", color: T.accent, fontWeight: 600, fontSize: 12, flexShrink: 0 }}>
            {t("compose.applyingTo")} <IconArrowRight size={13} />
          </span>

          {/* job */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: "1 1 220px" }}>
            <CompanyAvatar logo={job?.company?.logo_url} name={job?.company?.name || job?.title} size={44} />
            <div style={{ minWidth: 0 }}>
              <div style={LABEL}>{t("compose.position")}</div>
              <div style={{ fontWeight: 700, fontSize: 15, color: T.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{job?.title || "—"}</div>
              <div style={{ fontSize: 12.5, color: T.ink3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {job?.company?.name || "—"}{job?.location ? ` · ${job.location}` : ""}
              </div>
            </div>
          </div>

          {job?.source_url && (
            <a href={job.source_url} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12.5, fontWeight: 600, color: T.accent, textDecoration: "none", flexShrink: 0, marginLeft: "auto" }}>
              {t("compose.viewPosting")}
            </a>
          )}
        </div>
      </Card>

      {/* composer */}
      <Card style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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
              <button
                type="button"
                onClick={() => generateEmail(false)}
                disabled={generating}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "7px 14px", borderRadius: 10, border: "none",
                  fontSize: 12.5, fontWeight: 600, color: "#fff",
                  background: "linear-gradient(135deg, #167a7a, #0E9CA6)",
                  boxShadow: "0 1px 2px rgba(22,122,122,.25)",
                  cursor: generating ? "default" : "pointer", opacity: generating ? 0.7 : 1,
                  transition: "filter .15s, opacity .15s",
                }}
                onMouseEnter={(e) => { if (!generating) e.currentTarget.style.filter = "brightness(1.07)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.filter = "none"; }}
              >
                {generating ? <IconLoader2 size={14} className="animate-spin" /> : <IconSparkles size={14} />}
                {generating ? t("compose.generating") : t("compose.generateEmail")}
              </button>
            </div>
            <QuillEditor ref={editorRef} initialHTML={bodyHTML} placeholder={t("compose.editorPlaceholder")} onChange={onEditorChange} minHeight={300} />
            {/* Feedback → regenerate: tell the LLM what to change and rewrite the draft */}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginTop: 8 }}>
              <Textarea
                size="sm"
                minRows={1}
                maxRows={3}
                value={feedback}
                onValueChange={setFeedback}
                placeholder={t("compose.feedbackPlaceholder")}
                isDisabled={generating}
                classNames={{ inputWrapper: "bg-default-50" }}
                className="flex-1"
              />
              <button
                type="button"
                onClick={() => generateEmail(true)}
                disabled={generating || !feedback.trim()}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, flexShrink: 0,
                  padding: "8px 14px", borderRadius: 10, border: `1px solid ${T.accent}33`,
                  fontSize: 12.5, fontWeight: 600, color: T.accent, background: "#e8f4f4",
                  cursor: generating || !feedback.trim() ? "default" : "pointer",
                  opacity: generating || !feedback.trim() ? 0.5 : 1, transition: "filter .15s, opacity .15s",
                }}
                onMouseEnter={(e) => { if (!(generating || !feedback.trim())) e.currentTarget.style.filter = "brightness(0.97)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.filter = "none"; }}
              >
                <IconSparkles size={14} />
                {t("compose.regenerate")}
              </button>
            </div>
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
