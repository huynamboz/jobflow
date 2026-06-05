import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@heroui/button";
import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, useDisclosure } from "@heroui/modal";
import { IconBrain, IconLoader2, IconPlus } from "@tabler/icons-react";

import { cvAdminService } from "@/services/cv-admin.service";
import type { CVBatch } from "@/types/cv-admin.types";

const T = {
  accent:   "oklch(0.55 0.20 240)", accent50: "oklch(0.97 0.03 240)",
  success:  "oklch(0.62 0.17 155)", success50: "oklch(0.96 0.04 155)",
  danger:   "oklch(0.60 0.22 25)",  danger50: "oklch(0.96 0.03 25)",
  warning:  "oklch(0.76 0.16 70)",  warning50: "oklch(0.97 0.04 75)",
  ink:      "oklch(0.18 0.02 265)", ink2: "oklch(0.38 0.015 265)",
  ink3:     "oklch(0.56 0.012 265)", ink4: "oklch(0.72 0.008 265)",
  surface:  "#ffffff", surface2: "oklch(0.97 0.005 85)", surface3: "oklch(0.945 0.006 85)",
  line:     "oklch(0.92 0.006 85)",
};

const POLL_INTERVAL = 2500;

const SOURCE_CATEGORIES = ["AI", "Devops", "Software Engineer", "Tester", "UX_UI", "Business Analyst"];

const BADGE: Record<string, { bg: string; color: string }> = {
  pending:   { bg: T.surface3, color: T.ink3 },
  running:   { bg: "oklch(0.93 0.05 240)", color: "oklch(0.42 0.16 240)" },
  done:      { bg: T.success50, color: T.success },
  error:     { bg: T.danger50, color: T.danger },
  cancelled: { bg: "oklch(0.94 0.03 60)", color: "oklch(0.52 0.12 60)" },
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

function BatchCard({ batch, onClick }: { batch: CVBatch; onClick: () => void }) {
  const processed = batch.done_count + batch.error_count;
  const pct = batch.total > 0 ? (processed / batch.total) * 100 : 0;
  const bs = BADGE[batch.status] ?? BADGE.pending;
  const pulse = batch.status === "running";

  return (
    <div className="jb-card-hover" onClick={onClick} style={{
      background: T.surface, border: `1px solid ${T.line}`,
      borderRadius: 20, padding: 18, cursor: "pointer",
      transition: "transform 0.14s, box-shadow 0.14s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          padding: "3px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600,
          background: bs.bg, color: bs.color,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", flexShrink: 0, animation: pulse ? "jb-pulse 1.4s ease-in-out infinite" : undefined }} />
          {batch.status}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: T.ink4 }}>{fmtDate(batch.created_at)}</span>
      </div>

      <div style={{ fontWeight: 700, fontSize: 15 }}>CV Batch #{batch.id}</div>
      <div style={{ fontSize: 12, color: T.ink3, marginTop: 2 }}>
        {batch.filter_source_categories.length > 0
          ? batch.filter_source_categories.join(", ")
          : "All CVs"}
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={{ height: 8, borderRadius: 999, background: T.surface3, overflow: "hidden" }}>
          <span style={{
            display: "block", height: "100%", borderRadius: 999,
            background: batch.status === "done" ? T.success : T.accent,
            width: `${pct}%`, transition: "width 0.4s",
            position: "relative", overflow: "hidden",
          }}>
            {pulse && <span style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg,transparent,rgba(255,255,255,0.45),transparent)", animation: "jb-shimmer 1.6s linear infinite" }} />}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginTop: 6 }}>
          <span style={{ color: T.ink3 }}>{batch.done_count} / {batch.total} CVs</span>
          <span style={{ fontWeight: 600 }}>{pct.toFixed(0)}%</span>
        </div>
      </div>

      <div style={{ height: 1, background: T.line, margin: "12px 0" }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11.5 }}>
        <div>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>Errors</div>
          <div style={{ marginTop: 2, color: batch.error_count > 0 ? T.danger : T.ink2, fontWeight: 600 }}>{batch.error_count}</div>
        </div>
        <div>
          <div style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, fontSize: 10, color: T.ink4 }}>Categories</div>
          <div style={{ marginTop: 2, color: T.ink2 }}>{batch.filter_source_categories.length || "all"}</div>
        </div>
      </div>
    </div>
  );
}

function NewBatchModal({ isOpen, onClose, onCreated }: {
  isOpen: boolean; onClose: () => void; onCreated: (id: number) => void;
}) {
  const [selected, setSelected] = useState<string[]>(["AI", "Devops", "Software Engineer", "Tester", "UX_UI"]);
  const [loading, setLoading] = useState(false);

  const toggle = (cat: string) =>
    setSelected((prev) => prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]);

  const handleStart = async () => {
    setLoading(true);
    try {
      const batch = await cvAdminService.createCVBatch({
        source: "linkedin_dataset",
        source_categories: selected,
      });
      onCreated(batch.id);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <ModalContent>
        <ModalHeader style={{ fontWeight: 700, fontSize: 17 }}>
          New CV Extraction Batch
        </ModalHeader>

        <ModalBody>
          <p style={{ fontSize: 13, color: T.ink3, margin: "0 0 16px" }}>
            The LLM re-extracts <strong style={{ color: T.ink }}>role_category</strong>, <strong style={{ color: T.ink }}>seniority</strong>, and <strong style={{ color: T.ink }}>skills</strong> from each CV's raw text and updates the record directly.
          </p>

          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: T.ink3, marginBottom: 8 }}>
            Source categories
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {SOURCE_CATEGORIES.map((cat) => {
              const on = selected.includes(cat);
              return (
                <button key={cat} type="button" onClick={() => toggle(cat)} style={{
                  padding: "6px 12px", borderRadius: 999, fontSize: 12.5, fontWeight: 500, cursor: "pointer",
                  background: on ? T.ink : T.surface2, color: on ? "#fff" : T.ink2,
                  border: `1px solid ${on ? T.ink : "transparent"}`,
                  transition: "all 0.12s",
                }}>
                  {cat}
                </button>
              );
            })}
          </div>

          <p style={{ fontSize: 12, color: T.ink3, margin: 0 }}>
            <strong style={{ color: T.ink }}>{selected.length}</strong> categories selected — uploaded CVs are always included.
          </p>
        </ModalBody>

        <ModalFooter>
          <Button variant="flat" onPress={onClose}>Cancel</Button>
          <Button
            color="primary" isLoading={loading} isDisabled={selected.length === 0}
            onPress={handleStart}
          >
            Start extraction
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

export default function CVBatchOverview() {
  const navigate = useNavigate();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [batches, setBatches] = useState<CVBatch[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setBatches(await cvAdminService.listCVBatches()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const hasRunning = batches.some((b) => b.status === "running");
    if (!hasRunning) return;
    const id = setInterval(load, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [batches, load]);

  const totalDone = batches.reduce((s, b) => s + b.done_count, 0);
  const totalCVs  = batches.reduce((s, b) => s + b.total, 0);
  const running   = batches.filter((b) => b.status === "running").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <style>{`
        @keyframes jb-shimmer { 0%{transform:translateX(-100%)} 100%{transform:translateX(100%)} }
        @keyframes jb-pulse   { 0%,100%{opacity:1} 50%{opacity:0.5} }
        @keyframes jb-slide   { from{transform:translateX(32px);opacity:0} to{transform:translateX(0);opacity:1} }
        .jb-card-hover:hover { transform:translateY(-2px); box-shadow:0 2px 4px rgba(20,18,30,.04),0 8px 24px rgba(20,18,30,.06); }
      `}</style>

      <NewBatchModal
        isOpen={isOpen}
        onClose={onClose}
        onCreated={(id) => { onClose(); navigate(String(id)); }}
      />

      <div style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.025em", margin: 0, color: T.ink }}>
            CV Batch <span style={{ fontStyle: "italic", color: T.accent, fontWeight: 400 }}>Extraction</span>
          </h1>
          <p style={{ margin: "4px 0 0", color: T.ink3, fontSize: 14 }}>
            Re-extract role_category, seniority, and skills from CV raw text using LLM.
          </p>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <Button color="primary" startContent={<IconPlus size={14} />} onPress={onOpen}>
            New batch
          </Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
        {[
          { label: "Active now",   value: running,                       unit: "running",   accent: running > 0 },
          { label: "Total batches", value: batches.length,               unit: "all-time" },
          { label: "CVs extracted", value: totalDone.toLocaleString(),   unit: `/ ${totalCVs.toLocaleString()}` },
          { label: "Last batch",   value: batches[0] ? `#${batches[0].id}` : "—" },
        ].map(({ label, value, unit, accent }) => (
          <div key={label} style={{
            background: accent ? T.accent : T.surface, border: `1px solid ${accent ? T.accent : T.line}`,
            borderRadius: 16, padding: "14px 16px", color: accent ? "#fff" : T.ink,
          }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: accent ? "rgba(255,255,255,0.75)" : T.ink3 }}>{label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.02em", marginTop: 4, display: "flex", alignItems: "baseline", gap: 6 }}>
              {value}
              {unit && <span style={{ fontSize: 13, fontWeight: 500, color: accent ? "rgba(255,255,255,0.7)" : T.ink3 }}>{unit}</span>}
            </div>
          </div>
        ))}
      </div>

      {loading ? (
        <div style={{ display: "grid", placeItems: "center", height: 160, color: T.ink3 }}>
          <IconLoader2 size={20} style={{ animation: "jb-spin 0.7s linear infinite" }} />
        </div>
      ) : batches.length === 0 ? (
        <div style={{ display: "grid", placeItems: "center", height: 240, color: T.ink3 }}>
          <div style={{ textAlign: "center" }}>
            <IconBrain size={32} style={{ margin: "0 auto 12px", color: T.ink4 }} />
            <div style={{ fontWeight: 600, marginBottom: 4 }}>No batches yet</div>
            <div style={{ fontSize: 13 }}>Start a batch to re-extract CV data with LLM.</div>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))", gap: 14 }}>
          {batches.map((b) => (
            <BatchCard key={b.id} batch={b} onClick={() => navigate(String(b.id))} />
          ))}
        </div>
      )}
    </div>
  );
}
