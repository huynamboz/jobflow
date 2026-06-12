import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { mailService } from "@/services/mail.service";

type Reply = { employee: { id: number; name: string }; title: string; snippet: string; created_at: string; link_url: string };

export default function MailRepliesBlock({ refreshKey }: { refreshKey?: number }) {
  const navigate = useNavigate();
  const [items, setItems] = useState<Reply[]>([]);

  useEffect(() => {
    mailService.recentReplies().then(setItems).catch(() => setItems([]));
  }, [refreshKey]);

  if (items.length === 0) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid var(--line-2)", borderRadius: 14, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Mail className="size-4" strokeWidth={1.75} style={{ color: "var(--accent, #167a7a)" }} />
        <span style={{ font: "600 14px/1 var(--font-node-sans)", color: "var(--ink)" }}>Mail replies</span>
        <span style={{ marginLeft: "auto", font: "600 11px/1 var(--font-node-sans)", color: "var(--muted)" }}>{items.length}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {items.map((r, i) => (
          <button key={i} type="button" onClick={() => navigate(r.link_url.replace(/^\/admin/, "/admin"))}
            style={{ textAlign: "left", padding: "8px 0", borderTop: i ? "1px solid var(--line)" : "none", background: "none", cursor: "pointer" }}>
            <div style={{ font: "600 12.5px/1.3 var(--font-node-sans)", color: "var(--ink)" }}>{r.title}</div>
            <div style={{ font: "400 12px/1.4 var(--font-node-sans)", color: "var(--muted)", marginTop: 2,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.snippet}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
