import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import { IconMail, IconArrowDownLeft } from "@tabler/icons-react";
import { Chip } from "@heroui/chip";

import { Card } from "@/components/ui/card";
import { mailService } from "@/services/mail.service";

type Reply = { employee: { id: number; name: string }; title: string; snippet: string; created_at: string; link_url: string };

function relTime(iso: string, t: TFunction): string {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return t("mail.relTime.justNow");
  if (m < 60) return t("mail.relTime.minutesAgo", { count: m });
  const h = Math.round(m / 60);
  if (h < 24) return t("mail.relTime.hoursAgo", { count: h });
  return t("mail.relTime.daysAgo", { count: Math.round(h / 24) });
}

export default function MailRepliesBlock({ refreshKey }: { refreshKey?: number }) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const [items, setItems] = useState<Reply[]>([]);

  useEffect(() => {
    mailService.recentReplies().then(setItems).catch(() => setItems([]));
  }, [refreshKey]);

  if (items.length === 0) return null;

  return (
    <Card padding={20} className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="grid size-9 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600">
          <IconMail size={18} stroke={1.75} />
        </div>
        <h3 className="text-sm font-semibold text-foreground">{t("mail.title")}</h3>
        <Chip size="sm" color="success" variant="flat" className="ml-auto">{items.length}</Chip>
      </div>
      <div className="flex flex-col">
        {items.map((r, i) => (
          <button key={i} type="button" onClick={() => navigate(r.link_url.replace(/^\/admin/, "/admin"))}
            className={`flex items-start gap-3 px-1 py-2.5 text-left transition-colors hover:bg-default-50 ${i ? "border-t border-default-100" : ""}`}>
            <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-emerald-500/10 text-emerald-600">
              <IconArrowDownLeft size={15} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-foreground">{r.title}</span>
              <span className="mt-0.5 block truncate text-xs text-default-500">{r.snippet}</span>
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-default-400">{relTime(r.created_at, t)}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}
