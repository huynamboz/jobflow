import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Drawer, DrawerContent, DrawerHeader, DrawerBody } from "@heroui/drawer";
import {
  IconAlertCircle,
  IconClock,
  IconCopy,
  IconFileText,
  IconLoader2,
  IconSparkles,
} from "@tabler/icons-react";

import { jobService } from "@/services/job.service";
import type { JDBatchRecord } from "@/types/job.types";
import { T } from "./_tokens";
import { Badge, type BadgeStatus } from "./_primitives";

export function RecordDrawer({ batchId, record, fieldsConfig, onClose }: {
  batchId: number;
  record: JDBatchRecord | null;
  fieldsConfig: string[];
  onClose: () => void;
}) {
  const { t } = useTranslation("llm");
  const [detail, setDetail] = useState<JDBatchRecord | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!record) return;
    setDetail(null);
    setLoading(true);
    jobService.getBatchRecord(batchId, record.id)
      .then(setDetail).catch(() => setDetail(record)).finally(() => setLoading(false));
  }, [batchId, record]);

  const r = detail ?? record;
  const res = r?.result;

  return (
    <Drawer
      isOpen={!!record}
      onOpenChange={(open) => !open && onClose()}
      placement="right"
      size="4xl"
    >
      <DrawerContent>
        <DrawerHeader style={{ borderBottom: `1px solid ${T.line}`, padding: "16px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {r && <span style={{ fontFamily: "monospace", fontSize: 12, color: T.ink3 }}>#{String(r.index + 1).padStart(2, "0")}</span>}
                <span style={{ fontWeight: 700, fontSize: 17, letterSpacing: "-0.015em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r?.title || t("batch.record.record")}
                </span>
                {r && <Badge status={r.status as BadgeStatus} />}
              </div>
              {r?.company && <div style={{ fontSize: 12.5, color: T.ink3, marginTop: 2 }}>{r.company}</div>}
            </div>
            {res && (
              <button
                type="button"
                title={t("batch.record.copyJson")}
                onClick={() => navigator.clipboard?.writeText(JSON.stringify(res, null, 2))}
                style={{ width: 34, height: 34, borderRadius: 12, background: T.surface2, border: "none", display: "grid", placeItems: "center", cursor: "pointer", color: T.ink2, flexShrink: 0 }}
              >
                <IconCopy size={15} />
              </button>
            )}
          </div>
        </DrawerHeader>

        <DrawerBody style={{ padding: 0, overflow: "auto" }}>
          {loading ? (
            <div style={{ display: "grid", placeItems: "center", height: 300, color: T.ink3 }}>
              <IconLoader2 size={20} style={{ animation: "jb-spin 0.7s linear infinite" }} />
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: 400 }}>
              {/* Left — raw input */}
              <div style={{ overflow: "auto", padding: "20px 24px", borderRight: `1px solid ${T.line}` }}>
                <PaneLabel icon={<IconFileText size={12} />} right={t("batch.record.fieldsInPrompt", { count: fieldsConfig.length })}>
                  {t("batch.record.rawInput")}
                </PaneLabel>
                {r?.combined_text ? (
                  <pre style={{
                    background: T.surface2, border: `1px solid ${T.line}`, borderRadius: 12,
                    padding: "12px 14px", fontFamily: "'JetBrains Mono',ui-monospace,monospace",
                    fontSize: 12, color: T.ink, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    lineHeight: 1.6, margin: 0,
                  }}>
                    {r.combined_text}
                  </pre>
                ) : (
                  <div style={{ color: T.ink4, fontSize: 13, padding: "24px 0" }}>{t("batch.record.noCombinedText")}</div>
                )}
              </div>

              {/* Right — extracted */}
              <div style={{ overflow: "auto", padding: "20px 24px", background: `color-mix(in oklch,${T.surface2} 70%,white)` }}>
                <PaneLabel icon={<IconSparkles size={12} />}>{t("batch.record.extractedByLlm")}</PaneLabel>

                {r?.status === "error" && r.error_msg && (
                  <div style={{ padding: 16, borderRadius: 12, background: T.danger50, border: `1px solid color-mix(in oklch,${T.danger} 20%,transparent)`, marginBottom: 14 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: T.danger, fontWeight: 700, fontSize: 13 }}>
                      <IconAlertCircle size={14} /> {t("batch.record.extractionFailed")}
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12.5, color: T.ink2 }}>{r.error_msg}</div>
                  </div>
                )}

                {r?.status === "pending" && (
                  <div style={{ padding: "32px 0", textAlign: "center", color: T.ink3 }}>
                    <IconClock size={24} style={{ display: "block", margin: "0 auto 12px" }} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{t("batch.record.queued")}</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>{t("batch.record.waitingForWorker")}</div>
                  </div>
                )}

                {r?.status === "processing" && (
                  <div style={{ padding: "32px 0", textAlign: "center", color: T.accent }}>
                    <IconLoader2 size={22} style={{ display: "block", margin: "0 auto 12px", animation: "jb-spin 0.7s linear infinite" }} />
                    <div style={{ fontWeight: 700, fontSize: 14 }}>{t("batch.record.extracting")}</div>
                  </div>
                )}

                {res && (
                  <div>
                    {Object.entries(res).map(([k, v]) => {
                      const isArray = Array.isArray(v);
                      const isNull = v === null;
                      return (
                        <div key={k} style={{ display: "grid", gridTemplateColumns: "130px 1fr", gap: 10, padding: "8px 0", borderBottom: `1px dashed ${T.line}`, fontSize: 13 }}>
                          <div style={{ color: T.accent, fontWeight: 500, fontSize: 12 }}>{k}</div>
                          <div style={{ color: isNull ? T.ink4 : T.ink, wordBreak: "break-word", fontStyle: isNull ? "italic" : undefined }}>
                            {isNull ? "—" : isArray ? (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                {(v as unknown[]).length === 0
                                  ? <span style={{ color: T.ink4 }}>—</span>
                                  : (v as { name: string }[]).map((x, i) => (
                                    <span key={i} style={{ padding: "2px 8px", borderRadius: 999, background: T.surface2, fontSize: 11.5 }}>
                                      {typeof x === "object" ? x.name ?? JSON.stringify(x) : String(x)}
                                    </span>
                                  ))
                                }
                              </div>
                            ) : String(v)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

function PaneLabel({ icon, children, right }: { icon: React.ReactNode; children: React.ReactNode; right?: string }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: T.ink3, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
      {icon}
      {children}
      {right && <span style={{ marginLeft: "auto", fontWeight: 500, textTransform: "none", letterSpacing: 0, fontSize: 11, color: T.ink4 }}>{right}</span>}
    </div>
  );
}
