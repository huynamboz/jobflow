import { Menu, Bell } from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Button } from "@heroui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@heroui/popover";
import { IconArrowDownLeft, IconAlertTriangle, IconBellOff, IconX } from "@tabler/icons-react";

import { useAuthStore } from "@/stores/auth.store";
import { mailService, type AppNotification } from "@/services/mail.service";
import { LanguageSwitcher } from "@/components/language-switcher";

export interface AdminHeaderProps {
  onMenuClick?: () => void;
}

// NODE · Economy V1 notification palette (warm neutral surfaces + vivid accents).
const N = {
  c1: "#fcfcfc", c2: "#f8f7f7", c3: "#f1f1f1", line: "#ececec",
  ink: "#121212", inkSoft: "#323232", muted: "#7b7b7b",
  blue: "#3582ff", red: "#fe5938", green: "#49ba61",
};

function relTime(iso: string, t: TFunction): string {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return t("relTime.justNow");
  if (m < 60) return t("relTime.minutesAgo", { count: m });
  const h = Math.round(m / 60);
  if (h < 24) return t("relTime.hoursAgo", { count: h });
  return t("relTime.daysAgo", { count: Math.round(h / 24) });
}

function NotificationRow({ n, onSelect }: { n: AppNotification; onSelect: (n: AppNotification) => void }) {
  const { t } = useTranslation("mail");
  const bounce = n.type === "mail_bounce";
  const unread = !n.read_at;
  const [hover, setHover] = useState(false);
  const bg = hover ? N.c3 : unread ? N.c2 : "transparent";
  return (
    <div
      role="button"
      onClick={() => onSelect(n)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="relative flex cursor-pointer items-start gap-3"
      style={{ padding: "10px 12px", borderRadius: 10, background: bg, transition: "background 120ms" }}
    >
      <span
        className="grid shrink-0 place-items-center rounded-full"
        style={{ width: 32, height: 32, background: N.c3, boxShadow: `0 0 0 1px ${N.line}`,
                 color: bounce ? N.red : N.green }}
      >
        {bounce ? <IconAlertTriangle size={16} strokeWidth={1.75} /> : <IconArrowDownLeft size={16} strokeWidth={1.75} />}
      </span>
      <div className="min-w-0 flex-1" style={{ paddingRight: unread ? 12 : 0 }}>
        <div className="flex items-baseline gap-2">
          <span className="truncate" style={{ fontSize: 12.5, fontWeight: 600, color: N.ink, letterSpacing: "-0.01em" }}>
            {n.title}
          </span>
          <span className="ml-auto shrink-0" style={{ fontSize: 10, color: N.muted }}>{relTime(n.created_at, t)}</span>
        </div>
        <div
          style={{ fontSize: 12, color: N.inkSoft, lineHeight: 1.4, marginTop: 2,
                   display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
        >
          {n.body_preview}
        </div>
      </div>
      {unread && (
        <span aria-hidden className="absolute rounded-full"
          style={{ top: 12, right: 12, width: 6, height: 6, background: N.blue }} />
      )}
    </div>
  );
}

function NotificationBell() {
  const { t } = useTranslation("mail");
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(() => {
    mailService.unreadCount().then(setUnread).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60000);
    return () => clearInterval(t);
  }, [refresh]);

  const loadList = useCallback(
    () => mailService.notifications(1).then((d) => setItems(d.results)).catch(() => {}),
    [],
  );

  // open → load list, lock body scroll, ESC to close
  useEffect(() => {
    if (!open) return;
    void loadList();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, loadList]);

  // click a row → mark read (persisted, just clears the unread dot) + close the
  // panel and deep-link to the related detail page.
  const onItem = async (n: AppNotification) => {
    setOpen(false);
    if (!n.read_at) { await mailService.markRead(n.id).catch(() => {}); refresh(); }
    if (n.link_url) navigate(n.link_url.replace(/^\/admin/, "/admin"));
  };

  const markAll = async () => {
    const un = items.filter((i) => !i.read_at);
    if (!un.length) return;
    await Promise.all(un.map((i) => mailService.markRead(i.id).catch(() => {})));
    await loadList();
    refresh();
  };

  const panelUnread = items.filter((i) => !i.read_at).length;

  return (
    <>
      <style>{`
        @keyframes nodeFadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes nodeSlideRight { from { transform: translateX(16px); opacity: .6 } to { transform: translateX(0); opacity: 1 } }
      `}</style>

      {/* bell trigger */}
      <button
        type="button"
        aria-label={t("notifications.title")}
        onClick={() => setOpen(true)}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-[10px] border-0 bg-transparent transition-colors"
        style={{ color: N.inkSoft }}
        onMouseEnter={(e) => { e.currentTarget.style.background = N.c3; e.currentTarget.style.color = N.ink; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = N.inkSoft; }}
      >
        <Bell className="size-[18px]" strokeWidth={1.5} />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute right-1 top-1 inline-flex h-[14px] min-w-[14px] items-center justify-center rounded-full px-1 text-white"
            style={{ background: N.red, fontSize: 9, fontWeight: 700 }}
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && createPortal(
        <div className="fixed inset-0" style={{ zIndex: 70 }}>
          {/* backdrop */}
          <div
            onClick={() => setOpen(false)}
            className="absolute inset-0"
            style={{ background: "rgba(18,18,18,.45)", backdropFilter: "blur(2px)", animation: "nodeFadeIn 160ms ease" }}
          />
          {/* right slide-in panel */}
          <div
            className="absolute flex flex-col"
            style={{
              top: 12, bottom: 12, right: 12, width: 380,
              background: N.c1, border: `1px solid ${N.line}`, borderRadius: 20,
              boxShadow: "0 24px 60px -12px rgba(18,18,18,.28)", overflow: "hidden",
              animation: "nodeSlideRight 220ms cubic-bezier(.4,.1,.2,1)",
            }}
          >
            {/* header */}
            <div className="flex shrink-0 items-center justify-between" style={{ padding: "14px 14px 12px 18px", borderBottom: `1px solid ${N.line}` }}>
              <div className="flex items-center gap-2">
                <span style={{ fontSize: 14, fontWeight: 600, color: N.ink, letterSpacing: "-0.015em" }}>{t("notifications.title")}</span>
                {panelUnread > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full px-1.5"
                    style={{ height: 16, background: N.c3, color: N.inkSoft, fontSize: 10, fontWeight: 600 }}>
                    {t("notifications.new", { count: panelUnread })}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {panelUnread > 0 && (
                  <button type="button" onClick={() => void markAll()}
                    className="cursor-pointer border-0 bg-transparent transition-colors"
                    style={{ fontSize: 11.5, color: N.inkSoft, padding: "4px 8px", borderRadius: 6 }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = N.ink; e.currentTarget.style.background = N.c3; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = N.inkSoft; e.currentTarget.style.background = "transparent"; }}>
                    {t("notifications.markAllRead")}
                  </button>
                )}
                <button type="button" aria-label={t("notifications.close")} onClick={() => setOpen(false)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] border-0 bg-transparent transition-colors"
                  style={{ color: N.inkSoft }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = N.c3; e.currentTarget.style.color = N.ink; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = N.inkSoft; }}>
                  <IconX size={15} />
                </button>
              </div>
            </div>

            {/* body */}
            <div className="min-h-0 flex-1 overflow-y-auto" style={{ padding: 8 }}>
              {items.length === 0 ? (
                <div className="flex flex-col items-center gap-2" style={{ padding: "44px 16px", textAlign: "center" }}>
                  <span className="grid place-items-center rounded-full" style={{ width: 44, height: 44, background: N.c3, color: N.muted }}>
                    <IconBellOff size={22} strokeWidth={1.5} />
                  </span>
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: N.inkSoft }}>{t("notifications.allCaughtUp")}</div>
                  <p style={{ fontSize: 11.5, color: N.muted }}>{t("notifications.emptyHint")}</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {items.map((n) => <NotificationRow key={n.id} n={n} onSelect={onItem} />)}
                </div>
              )}
            </div>

            {/* footer */}
            <div className="flex shrink-0 items-center justify-center" style={{ padding: "10px 12px", borderTop: `1px solid ${N.line}`, background: N.c2 }}>
              <button type="button" onClick={() => { setOpen(false); navigate("/admin/mail"); }}
                className="cursor-pointer border-0 bg-transparent" style={{ fontSize: 12, color: N.blue, fontWeight: 500, padding: "4px 8px" }}>
                {t("notifications.viewAllMail")}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export function AdminHeader({ onMenuClick }: AdminHeaderProps) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  return (
    <header className="flex h-16 items-center justify-between gap-4 border-b border-default-200 bg-white px-4 dark:border-default-100 dark:bg-default-50 md:px-6">
      {/* Left */}
      <div className="flex items-center gap-3">
        <Button
          isIconOnly
          aria-label="Toggle sidebar"
          className="lg:hidden"
          radius="sm"
          size="sm"
          variant="light"
          onPress={onMenuClick}
        >
          <Menu className="size-5 text-default-600" />
        </Button>
      </div>

      {/* Right */}
      <div className="flex items-center gap-1">
        <LanguageSwitcher />
        <NotificationBell />

        {user && (
          <Popover placement="bottom-end">
            <PopoverTrigger>
              <button className="ml-2 outline-none" type="button">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground cursor-pointer">
                  {(user.username || user.email || "A").charAt(0).toUpperCase()}
                </div>
              </button>
            </PopoverTrigger>
            <PopoverContent>
              <div className="px-1 py-2 w-48">
                <div className="px-2 py-1 mb-2">
                  <p className="text-sm font-semibold text-default-900 truncate">{user.username}</p>
                  <p className="text-xs text-default-500 truncate">{user.email}</p>
                  <p className="text-xs text-primary mt-0.5 capitalize">{user.role}</p>
                </div>
                <div className="border-t border-default-200 pt-2">
                  <Button
                    className="w-full justify-start text-danger"
                    color="danger"
                    size="sm"
                    variant="light"
                    onPress={logout}
                  >
                    Logout
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </header>
  );
}
