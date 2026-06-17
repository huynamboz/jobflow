import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import {
  IconChevronLeft,
  IconChevronRight,
  IconCircleCheck,
  IconFileText,
  IconLoader2,
  IconSparkles,
  IconUpload,
  IconX,
} from "@tabler/icons-react";

import { cn } from "@/lib/utils";
import { jobService } from "@/services/job.service";
import { LIMIT_OPTIONS } from "./_tokens";
import { Badge, Card, CardBody, CardHead, FieldChip, KeyframeStyle } from "./_primitives";

export default function JDBatchNew() {
  const { t } = useTranslation("llm");
  const navigate = useNavigate();
  const [step, setStep] = useState<0 | 1>(0);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<{
    total: number; fields: string[];
    sample: Record<string, unknown>[]; filename: string;
  } | null>(null);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [limit, setLimit] = useState<number | null>(null);
  const [customLimit, setCustomLimit] = useState("");
  const [workers, setWorkers] = useState(3);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const loadFile = async (f: File) => {
    setFile(f);
    setLoading(true);
    setError("");
    setPreview(null);
    setSelectedFields([]);
    try {
      const data = await jobService.previewBatch(f);
      setPreview(data);
      const prefer = ["title", "description", "seniority_hint", "raw_skills"];
      setSelectedFields(data.fields.filter((x) => prefer.includes(x)));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("batch.new.errors.readFile"));
    } finally {
      setLoading(false);
    }
  };

  const toggleField = (f: string) =>
    setSelectedFields((prev) => prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]);

  const effectiveLimit =
    limit === null ? null : limit === -1 ? (parseInt(customLimit) || null) : limit;

  const previewText = preview && selectedFields.length > 0
    ? selectedFields.map((f) => `${f.toUpperCase()}\n${preview.sample[0]?.[f] ?? "—"}`).join("\n\n---\n\n")
    : "";

  const handleStart = async () => {
    if (!file || !preview || selectedFields.length === 0) return;
    setStarting(true);
    setError("");
    try {
      const batch = await jobService.createBatch(file, selectedFields, effectiveLimit, workers);
      navigate(`/admin/jd-batch/${batch.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("batch.new.errors.startBatch"));
      setStarting(false);
    }
  };

  const steps = [t("batch.new.steps.upload"), t("batch.new.steps.fieldsPrompt"), t("batch.new.steps.run")];

  return (
    <div className="flex flex-col gap-5">
      <KeyframeStyle />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div>
          <h1 className="text-[26px] sm:text-[32px] font-bold tracking-[-0.025em] m-0 text-jb-ink">
            {t("batch.new.titlePrefix")} <span className="italic text-jb-accent font-normal">{t("batch.new.titleAccent")}</span>
          </h1>
          <p className="mt-1 text-jb-ink3 text-sm m-0">
            {t("batch.new.description")}
          </p>
        </div>
        <div className="sm:ml-auto">
          <button
            type="button"
            onClick={() => navigate("/admin/jd-batch")}
            className="flex items-center gap-1.5 py-2 px-3.5 rounded-[10px] border border-jb-line bg-jb-surface text-jb-ink2 text-[13px] font-medium"
          >
            <IconChevronLeft size={14} /> {t("batch.new.allBatches")}
          </button>
        </div>
      </div>

      <div className="max-w-[900px]">
        {/* Wizard stepper */}
        <div className="flex items-center gap-2.5 mb-7">
          {steps.map((s, i) => (
            <div key={s} className="contents">
              <div className="flex items-center gap-2">
                <div className={cn(
                  "w-[22px] h-[22px] rounded-full grid place-items-center text-[11px] font-bold",
                  i <= step ? "bg-jb-accent text-white" : "bg-jb-surface3 text-jb-ink3",
                )}>
                  {i < step ? <IconCircleCheck size={12} /> : i + 1}
                </div>
                <span className={cn("text-[12.5px] font-semibold", i === step ? "text-jb-ink" : "text-jb-ink3")}>{s}</span>
              </div>
              {i < steps.length - 1 && (
                <div className={cn("flex-1 h-[1.5px]", i < step ? "bg-jb-accent" : "bg-jb-surface3")} />
              )}
            </div>
          ))}
        </div>

        {/* Step 0 — Upload */}
        {step === 0 && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-[28px] font-bold tracking-[-0.025em] m-0 text-jb-ink">
                {t("batch.new.uploadStep.headingPrefix")} <span className="italic text-jb-accent">{t("batch.new.uploadStep.headingAccent")}</span> {t("batch.new.uploadStep.headingSuffix")}
              </h2>
              <p className="mt-1 text-jb-ink3 text-sm">
                {t("batch.new.uploadStep.description")}
              </p>
            </div>

            {!file ? (
              <label
                className={cn(
                  "block border-2 border-dashed rounded-3xl px-6 py-12 text-center cursor-pointer transition-colors",
                  dragging ? "border-jb-accent bg-jb-accent50" : "border-jb-linestrong bg-jb-surface2/70",
                )}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault(); setDragging(false);
                  const f = e.dataTransfer.files[0]; if (f) loadFile(f);
                }}
              >
                <input
                  ref={inputRef} type="file" accept=".jsonl,.json"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) loadFile(f); }}
                />
                <div className="w-14 h-14 rounded-2xl bg-jb-surface mx-auto mb-4 grid place-items-center text-jb-accent shadow-[0_1px_2px_rgba(20,18,30,0.04)]">
                  <IconUpload size={22} />
                </div>
                <div className="text-[18px] font-bold tracking-[-0.01em] mb-1 text-jb-ink">
                  {t("batch.new.uploadStep.dropTitle")}
                </div>
                <p className="m-0 text-jb-ink3 text-[13px]">
                  {t("batch.new.uploadStep.orBrowsePrefix")}{" "}
                  <span className="text-jb-accent font-semibold underline">
                    {t("batch.new.uploadStep.browse")}
                  </span>{" "}
                  {t("batch.new.uploadStep.maxSize")}
                </p>
              </label>
            ) : (
              <div className="flex flex-col gap-3.5">
                <Card>
                  <CardBody className="flex items-center gap-3.5">
                    {loading ? (
                      <div className="flex items-center gap-3 text-jb-ink3">
                        <IconLoader2 size={20} className="animate-[jb-spin_0.7s_linear_infinite]" />
                        <span className="text-[13px]">{t("batch.new.uploadStep.readingFile")}</span>
                      </div>
                    ) : (
                      <>
                        <div className="w-11 h-11 rounded-xl bg-jb-accent50 text-jb-accent grid place-items-center shrink-0">
                          <IconFileText size={20} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-bold">{file.name}</div>
                          <div className="text-[12.5px] text-jb-ink3 mt-0.5">
                            {(file.size / 1024).toFixed(1)} KB
                            {preview && (
                              <> · <strong className="text-jb-ink2">{preview.total}</strong> {t("batch.new.uploadStep.rowsDetected")}</>
                            )}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => { setFile(null); setPreview(null); setSelectedFields([]); }}
                          className="flex items-center gap-1.5 py-1.5 px-2.5 rounded-lg border border-jb-line bg-jb-surface2 text-jb-ink2 text-[12.5px]"
                        >
                          <IconX size={14} /> {t("batch.new.uploadStep.remove")}
                        </button>
                      </>
                    )}
                  </CardBody>
                </Card>

                {preview && (
                  <Card>
                    <CardHead>
                      <span className="font-semibold text-[15px]">{t("batch.new.uploadStep.previewRows")}</span>
                      <Badge status="pending" label={t("batch.new.uploadStep.totalBadge", { count: preview.total })} />
                    </CardHead>
                    <CardBody>
                      {preview.sample.slice(0, 3).map((row, i) => (
                        <div key={i} className="grid grid-cols-[auto_1fr_auto] gap-3 items-center p-3 mb-2 rounded-xl border border-dashed border-jb-linestrong bg-jb-surface2/50">
                          <span className="font-mono text-xs text-jb-ink4">#{i + 1}</span>
                          <div className="min-w-0">
                            <div className="font-semibold text-[13.5px]">
                              {String(row.title ?? row.job_title ?? "—")}
                            </div>
                            <div className="font-mono text-[11px] text-jb-ink3 overflow-hidden text-ellipsis whitespace-nowrap mt-0.5">
                              {JSON.stringify(row).slice(0, 80)}…
                            </div>
                          </div>
                          <Badge status="pending" label={t("batch.new.uploadStep.valid")} />
                        </div>
                      ))}
                      {preview.total > 3 && (
                        <div className="text-center text-xs text-jb-ink3 mt-2">
                          {t("batch.new.uploadStep.moreRows", { count: preview.total - 3 })}
                        </div>
                      )}
                    </CardBody>
                  </Card>
                )}

                {error && <p className="text-jb-danger text-[13px]">{error}</p>}

                {preview && (
                  <div className="flex justify-end">
                    <Button color="primary" endContent={<IconChevronRight size={16} />} onPress={() => setStep(1)}>
                      {t("batch.new.uploadStep.continue")}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Step 1 — Fields & config */}
        {step === 1 && preview && (
          <div>
            <div className="mb-6">
              <h2 className="text-[28px] font-bold tracking-[-0.025em] m-0 mb-1 text-jb-ink">
                {t("batch.new.fieldsStep.headingPrefix")} <span className="italic text-jb-accent">{t("batch.new.fieldsStep.headingAccent")}</span>
              </h2>
              <p className="text-jb-ink3 text-sm m-0">
                {t("batch.new.fieldsStep.description")}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
              {/* Left — field picker */}
              <Card>
                <CardHead>
                  <span className="font-semibold text-[15px]">{t("batch.new.fieldsStep.fieldsFromRow")}</span>
                  <span className="text-xs text-jb-ink3">
                    {t("batch.new.fieldsStep.selectedOf", { selected: selectedFields.length, total: preview.fields.length })}
                  </span>
                  <div className="ml-auto flex gap-1.5">
                    {([[t("batch.new.fieldsStep.all"), preview.fields], [t("batch.new.fieldsStep.none"), []]] as [string, string[]][]).map(([lbl, val]) => (
                      <button key={lbl} type="button" onClick={() => setSelectedFields(val)}
                        className="py-1 px-2.5 rounded-lg border border-jb-line bg-jb-surface2 text-jb-ink2 text-xs">
                        {lbl}
                      </button>
                    ))}
                  </div>
                </CardHead>
                <CardBody>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.fields.map((f) => (
                      <FieldChip key={f} label={f} on={selectedFields.includes(f)} onClick={() => toggleField(f)} />
                    ))}
                  </div>
                </CardBody>
              </Card>

              {/* Right — preview + config (sticky on desktop) */}
              <div className="flex flex-col gap-4 md:sticky md:top-[90px]">
                <Card>
                  <CardHead>
                    <span className="font-semibold text-[15px]">{t("batch.new.fieldsStep.promptPreview")}</span>
                    <span className="text-[11.5px] text-jb-ink3">{t("batch.new.fieldsStep.promptPreviewHint")}</span>
                  </CardHead>
                  <CardBody>
                    {selectedFields.length === 0 ? (
                      <div className="py-6 text-center text-jb-ink4 text-[13px]">
                        {t("batch.new.fieldsStep.selectAtLeastOne")}
                      </div>
                    ) : (
                      <pre className="bg-jb-dark text-jb-dark-text2 rounded-xl px-3.5 py-3 font-mono text-[11.5px] leading-[1.6] max-h-[280px] overflow-auto m-0 whitespace-pre-wrap break-words">
                        {previewText}
                      </pre>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHead><span className="font-semibold text-[15px]">{t("batch.new.fieldsStep.recordLimit")}</span></CardHead>
                  <CardBody>
                    <div className="flex flex-wrap gap-1.5 mb-3.5">
                      {LIMIT_OPTIONS.map((opt) => (
                        <FieldChip
                          key={String(opt.value)}
                          label={opt.value === null ? t("batch.new.fieldsStep.all") : opt.label}
                          on={limit === opt.value}
                          onClick={() => setLimit(opt.value)}
                        />
                      ))}
                      <FieldChip label={t("batch.new.fieldsStep.custom")} on={limit === -1} onClick={() => setLimit(-1)} />
                      {limit === -1 && (
                        <Input size="sm" type="number" min={1} placeholder={t("batch.new.fieldsStep.customPlaceholder")} className="w-28"
                          value={customLimit} onValueChange={setCustomLimit} />
                      )}
                    </div>
                    <p className="text-[12.5px] text-jb-ink3 m-0">
                      {t("batch.new.fieldsStep.willProcessPrefix")}{" "}
                      <strong className="text-jb-ink">
                        {(effectiveLimit == null
                          ? preview.total
                          : Math.min(effectiveLimit, preview.total)
                        ).toLocaleString()}
                      </strong>{" "}
                      {t("batch.new.fieldsStep.willProcessSuffix", { min: Math.round(((effectiveLimit ?? preview.total) * 4) / 60) })}
                    </p>
                  </CardBody>
                </Card>

                <Card>
                  <CardHead><span className="font-semibold text-[15px]">{t("batch.new.fieldsStep.parallelWorkers")}</span></CardHead>
                  <CardBody>
                    <div className="flex items-center gap-3 mb-3">
                      <button type="button" onClick={() => setWorkers((w) => Math.max(1, w - 1))}
                        className="w-8 h-8 rounded-lg bg-jb-surface2 text-jb-ink2 text-base font-bold flex items-center justify-center border border-jb-line">−</button>
                      <span className="text-[22px] font-bold text-jb-ink tabular-nums w-8 text-center">{workers}</span>
                      <button type="button" onClick={() => setWorkers((w) => Math.min(20, w + 1))}
                        className="w-8 h-8 rounded-lg bg-jb-surface2 text-jb-ink2 text-base font-bold flex items-center justify-center border border-jb-line">+</button>
                      <span className="text-xs text-jb-ink3 ml-1">{t("batch.new.fieldsStep.concurrentCalls")}</span>
                    </div>
                    <p className="text-[12px] text-jb-ink3 m-0">
                      {t("batch.new.fieldsStep.workersHint")}
                    </p>
                  </CardBody>
                </Card>

                {error && <p className="text-jb-danger text-[13px]">{error}</p>}

                <div className="flex gap-2 justify-end">
                  <button type="button" onClick={() => setStep(0)}
                    className="py-[9px] px-3.5 rounded-xl border border-jb-line bg-jb-surface2 text-jb-ink2 text-[13px] font-semibold">
                    {t("batch.new.fieldsStep.back")}
                  </button>
                  <Button
                    color="primary"
                    isLoading={starting}
                    isDisabled={selectedFields.length === 0}
                    startContent={!starting && <IconSparkles size={16} />}
                    onPress={handleStart}
                  >
                    {starting ? t("batch.new.fieldsStep.starting") : t("batch.new.fieldsStep.run", { count: (effectiveLimit ?? preview.total).toLocaleString() })}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
