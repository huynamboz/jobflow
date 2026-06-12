import { Menu, Bell } from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@heroui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@heroui/popover";

import { useAuthStore } from "@/stores/auth.store";
import { mailService, type AppNotification } from "@/services/mail.service";

export interface AdminHeaderProps {
  onMenuClick?: () => void;
}

function NotificationBell() {
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

  const loadList = () => mailService.notifications(1).then((d) => setItems(d.results)).catch(() => {});

  const onItem = async (n: AppNotification) => {
    setOpen(false);
    if (!n.read_at) { await mailService.markRead(n.id).catch(() => {}); refresh(); }
    if (n.link_url) navigate(n.link_url.replace(/^\/admin/, "/admin"));
  };

  return (
    <Popover placement="bottom-end" isOpen={open} onOpenChange={(o) => { setOpen(o); if (o) loadList(); }}>
      <PopoverTrigger>
        {/* badge sits on a relative wrapper OUTSIDE the Button — HeroUI Button
            clips with overflow-hidden (ripple), which was cutting the badge. */}
        <div className="relative inline-flex">
          <Button isIconOnly aria-label="Notifications" radius="full" size="sm" variant="light">
            <Bell className="size-[18px] text-default-500" />
          </Button>
          {unread > 0 && (
            <span className="pointer-events-none absolute -right-0.5 -top-0.5 z-10 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold leading-none text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </div>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0">
        <div className="border-b border-default-200 px-4 py-2 text-sm font-semibold">Notifications</div>
        <div className="max-h-96 overflow-auto">
          {items.length === 0 && <div className="px-4 py-6 text-center text-sm text-default-400">No notifications</div>}
          {items.map((n) => (
            <button key={n.id} type="button" onClick={() => void onItem(n)}
              className={`block w-full border-b border-default-100 px-4 py-2.5 text-left hover:bg-default-50 ${n.read_at ? "" : "bg-primary-50/40"}`}>
              <div className="text-[13px] font-semibold text-default-700">{n.title}</div>
              <div className="mt-0.5 line-clamp-2 text-xs text-default-500">{n.body_preview}</div>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
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
