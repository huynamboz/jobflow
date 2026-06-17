import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardBody } from "@heroui/card";
import { AlertTriangle, ArrowLeft, FileUp, Loader2, Plus, Save, Trash2, X } from "lucide-react";

import { cvAdminService } from "@/services/cv-admin.service";
import type { CVExtractResult, CVSkillEdit, WorkExperienceItem } from "@/types/cv-admin.types";

const EDUCATION_OPTIONS = [
  { value: 0, label: "education.none" },
  { value: 1, label: "education.college" },
  { value: 2, label: "education.bachelor" },
  { value: 3, label: "education.master" },
  { value: 4, label: "education.phd" },
];
const SENIORITY_OPTIONS = [
  { value: 0, label: "seniority.intern" },
  { value: 1, label: "seniority.junior" },
  { value: 2, label: "seniority.mid" },
  { value: 3, label: "seniority.senior" },
  { value: 4, label: "seniority.lead" },
  { value: 5, label: "seniority.manager" },
];

// ─── Skills editor ───────────────────────────────────────────────────────────

function SkillsEditor({
  skills,
  onChange,
}: {
  skills: CVSkillEdit[];
  onChange: (s: CVSkillEdit[]) => void;
}) {
  const { t } = useTranslation("cvs");
  const [input, setInput] = useState("");

  const add = () => {
    const name = input.trim();
    if (!name || skills.some((s) => s.name.toLowerCase() === name.toLowerCase())) return;
    onChange([...skills, { name, proficiency: 3 }]);
    setInput("");
  };

  const remove = (i: number) => onChange(skills.filter((_, idx) => idx !== i));

  const setProficiency = (i: number, p: number) => {
    const next = [...skills];
    next[i] = { ...next[i], proficiency: p };
    onChange(next);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {skills.map((s, i) => (
          <div key={i} className="flex items-center gap-1 rounded-lg border border-default-200 bg-default-50 pl-2.5 pr-1 py-1">
            <span className="text-xs text-default-700">{s.name}</span>
            <select
              value={s.proficiency}
              onChange={(e) => setProficiency(i, Number(e.target.value))}
              className="ml-1 rounded border-0 bg-transparent text-xs text-default-500 outline-none"
            >
              {[1, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v}★</option>)}
            </select>
            <button onClick={() => remove(i)} className="ml-0.5 rounded p-0.5 text-default-300 hover:text-red-400">
              <X className="size-3" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder={t("skillsEditor.addPlaceholder")}
          className="h-8 flex-1 rounded-lg border border-default-200 px-3 text-sm outline-none focus:border-blue-400"
        />
        <button onClick={add} className="flex items-center gap-1 rounded-lg border border-default-200 px-3 py-1.5 text-sm text-default-600 hover:bg-default-50">
          <Plus className="size-3.5" /> {t("skillsEditor.add")}
        </button>
      </div>
    </div>
  );
}

// ─── Work experience editor ───────────────────────────────────────────────────

function WorkExpEditor({
  items,
  onChange,
}: {
  items: WorkExperienceItem[];
  onChange: (items: WorkExperienceItem[]) => void;
}) {
  const { t } = useTranslation("cvs");
  const empty: WorkExperienceItem = { title: "", company: "", duration: "", description: "" };

  const update = (i: number, field: keyof WorkExperienceItem, val: string) => {
    const next = [...items];
    next[i] = { ...next[i], [field]: val };
    onChange(next);
  };

  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-3">
      {items.map((w, i) => (
        <div key={i} className="space-y-2 rounded-xl border border-default-200 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-default-500">#{i + 1}</span>
            <button onClick={() => remove(i)} className="rounded-lg p-1 text-default-300 hover:text-red-400">
              <Trash2 className="size-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              value={w.title} placeholder={t("workExpEditor.jobTitle")}
              onChange={(e) => update(i, "title", e.target.value)}
              className="col-span-2 rounded-lg border border-default-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400"
            />
            <input
              value={w.company} placeholder={t("workExpEditor.company")}
              onChange={(e) => update(i, "company", e.target.value)}
              className="rounded-lg border border-default-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400"
            />
            <input
              value={w.duration} placeholder={t("workExpEditor.duration")}
              onChange={(e) => update(i, "duration", e.target.value)}
              className="rounded-lg border border-default-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400"
            />
            <textarea
              value={w.description} placeholder={t("workExpEditor.description")}
              onChange={(e) => update(i, "description", e.target.value)}
              rows={2}
              className="col-span-2 rounded-lg border border-default-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400 resize-none"
            />
          </div>
        </div>
      ))}
      <button
        onClick={() => onChange([...items, { ...empty }])}
        className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-default-300 py-2.5 text-sm text-default-500 hover:border-blue-400 hover:text-blue-600"
      >
        <Plus className="size-4" /> {t("workExpEditor.addWorkExperience")}
      </button>
    </div>
  );
}

// ─── Drop zone ────────────────────────────────────────────────────────────────

function DropZone({ onFile }: { onFile: (f: File) => void }) {
  const { t } = useTranslation("cvs");
  const ref = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handle = (f: File) => {
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx", "txt"].includes(ext)) return;
    onFile(f);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handle(f); }}
      onClick={() => ref.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed py-16 transition-colors ${
        dragging ? "border-blue-400 bg-blue-50" : "border-default-200 hover:border-blue-300 hover:bg-default-50"
      }`}
    >
      <FileUp className="size-10 text-default-300" />
      <div className="text-center">
        <p className="text-sm font-medium text-default-700">{t("dropZone.instruction")}</p>
        <p className="mt-0.5 text-xs text-default-400">{t("dropZone.fileTypes")}</p>
      </div>
      <input ref={ref} type="file" accept=".pdf,.docx,.txt" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handle(f); }} />
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

type Step = "pick" | "extracting" | "editing" | "saving";

export default function CVUploadPage() {
  const { t } = useTranslation("cvs");
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("pick");
  const [form, setForm] = useState<CVExtractResult | null>(null);
  const [error, setError] = useState("");

  const set = <K extends keyof CVExtractResult>(k: K, v: CVExtractResult[K]) =>
    setForm((f) => f ? { ...f, [k]: v } : f);

  const handleFile = async (file: File) => {
    setStep("extracting");
    setError("");
    try {
      const result = await cvAdminService.extractCV(file);
      setForm(result);
      setStep("editing");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("upload.extractionFailed"));
      setStep("pick");
    }
  };

  const handleSave = async () => {
    if (!form) return;
    setStep("saving");
    setError("");
    try {
      await cvAdminService.saveCV(form);
      navigate("/admin/cvs");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("upload.saveFailed"));
      setStep("editing");
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate("/admin/cvs")}
          className="rounded-lg p-1.5 text-default-400 hover:bg-default-100">
          <ArrowLeft className="size-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-default-900">{t("upload.title")}</h1>
          <p className="text-sm text-default-500">
            {step === "pick" && t("upload.stepPick")}
            {step === "extracting" && t("upload.stepExtracting")}
            {step === "editing" && t("upload.stepEditing")}
            {step === "saving" && t("upload.stepSaving")}
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {step === "pick" && <DropZone onFile={handleFile} />}

      {step === "extracting" && (
        <div className="flex flex-col items-center justify-center gap-3 py-24 text-default-400">
          <Loader2 className="size-10 animate-spin text-blue-500" />
          <p className="text-sm">{t("upload.extracting")}</p>
        </div>
      )}

      {(step === "editing" || step === "saving") && form && !form.llm_used && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{t("upload.ruleBasedWarning")}</span>
        </div>
      )}

      {(step === "editing" || step === "saving") && form && (
        <div className="space-y-5">
          {/* Basic info */}
          <Card className="shadow-sm">
            <CardBody className="space-y-4 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-default-400">{t("upload.basicInformation")}</p>

              <div>
                <label className="mb-1 block text-xs font-medium text-default-600">{t("upload.fullName")}</label>
                <input
                  value={form.candidate_name}
                  onChange={(e) => set("candidate_name", e.target.value)}
                  placeholder={t("upload.candidateNamePlaceholder")}
                  className="w-full rounded-lg border border-default-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-default-600">{t("upload.experienceYears")}</label>
                  <input
                    type="number" min={0} step={0.5}
                    value={form.experience_years}
                    onChange={(e) => set("experience_years", parseFloat(e.target.value) || 0)}
                    className="w-full rounded-lg border border-default-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-default-600">{t("upload.seniority")}</label>
                  <select
                    value={form.seniority}
                    onChange={(e) => set("seniority", Number(e.target.value))}
                    className="w-full rounded-lg border border-default-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                  >
                    {SENIORITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-default-600">{t("upload.education")}</label>
                  <select
                    value={form.education}
                    onChange={(e) => set("education", Number(e.target.value))}
                    className="w-full rounded-lg border border-default-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                  >
                    {EDUCATION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
                  </select>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Skills */}
          <Card className="shadow-sm">
            <CardBody className="space-y-3 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-default-400">
                {t("upload.skillsHeading", { count: form.skills.length })}
              </p>
              <SkillsEditor skills={form.skills} onChange={(s) => set("skills", s)} />
            </CardBody>
          </Card>

          {/* Work experience */}
          <Card className="shadow-sm">
            <CardBody className="space-y-3 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-default-400">
                {t("upload.workExperienceHeading", { count: form.work_experience.length })}
              </p>
              <WorkExpEditor items={form.work_experience} onChange={(items) => set("work_experience", items)} />
            </CardBody>
          </Card>

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => { setForm(null); setStep("pick"); }}
              className="rounded-xl border border-default-200 px-5 py-2.5 text-sm text-default-600 hover:bg-default-50">
              {t("upload.reUpload")}
            </button>
            <button
              onClick={handleSave}
              disabled={step === "saving"}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {step === "saving" ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
              {step === "saving" ? t("upload.saving") : t("upload.saveCv")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
