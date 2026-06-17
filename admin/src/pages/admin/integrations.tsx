import { useEffect, useRef, useState } from "react";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Chip } from "@heroui/chip";
import { Spinner } from "@heroui/spinner";
import { addToast } from "@heroui/toast";
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
} from "@heroui/modal";
import {
  IconBrandDiscord,
  IconBrandGmail,
  IconBrandSlack,
  IconBrandTelegram,
  IconBrandWhatsapp,
  IconCheck,
  IconMailFast,
  IconMessageCircle2,
  IconQrcode,
  IconSend,
  type Icon as TablerIcon,
} from "@tabler/icons-react";

import { Card } from "@/components/ui/card";
import {
  integrationService,
  type IntegrationState,
  type ZaloQrStatus,
} from "@/services/integration.service";

/* ------------------------------------------------------------------ *
 * Platform display registry (FE) — labels, logos, brand colors, and
 * the connect-form field specs. The backend owns validation + which
 * fields are secret; this drives the UI only.
 * ------------------------------------------------------------------ */

type FieldType = "text" | "password" | "number";

interface ConnectField {
  key: string;
  label: string;
  placeholder?: string;
  type?: FieldType;
  required?: boolean;
  /** Secret fields are write-only — never returned by the API. */
  secret?: boolean;
  help?: string;
}

interface Platform {
  id: string;
  name: string;
  blurb: string;
  logo: string;
  icon: TablerIcon;
  color: string;
  guide: string;
  fields: ConnectField[];
}

const SI = (slug: string) => `https://cdn.simpleicons.org/${slug}`;
const FAVICON = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

const PLATFORMS: Platform[] = [
  {
    id: "slack",
    name: "Slack",
    blurb: "Post the morning digest to a Slack channel.",
    logo: FAVICON("slack.com"),
    icon: IconBrandSlack,
    color: "#4A154B",
    guide:
      "Create an Incoming Webhook in your Slack workspace and paste the URL below. The digest is delivered to that channel each morning.",
    fields: [
      {
        key: "webhook_url",
        label: "Incoming webhook URL",
        placeholder: "https://hooks.slack.com/services/T000/B000/XXXX",
        required: true,
        secret: true,
        help: "Slack → Apps → Incoming Webhooks → Add to channel.",
      },
      { key: "channel", label: "Channel (optional)", placeholder: "#staffing-digest" },
    ],
  },
  {
    id: "telegram",
    name: "Telegram",
    blurb: "Send a daily message via a Telegram bot.",
    logo: SI("telegram"),
    icon: IconBrandTelegram,
    color: "#229ED9",
    guide:
      "Talk to @BotFather to create a bot and grab its token, then add the bot to your group/channel and provide the chat ID.",
    fields: [
      {
        key: "bot_token",
        label: "Bot token",
        placeholder: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        type: "password",
        required: true,
        secret: true,
      },
      {
        key: "chat_id",
        label: "Chat ID",
        placeholder: "-1001234567890",
        required: true,
        help: "Numeric ID of the user, group, or channel to message.",
      },
    ],
  },
  {
    id: "discord",
    name: "Discord",
    blurb: "Drop the digest into a Discord channel.",
    logo: SI("discord"),
    icon: IconBrandDiscord,
    color: "#5865F2",
    guide:
      "In your Discord server: Channel settings → Integrations → Webhooks → New Webhook, then copy the webhook URL.",
    fields: [
      {
        key: "webhook_url",
        label: "Webhook URL",
        placeholder: "https://discord.com/api/webhooks/000/XXXX",
        required: true,
        secret: true,
      },
    ],
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    blurb: "Deliver the digest over WhatsApp Business.",
    logo: SI("whatsapp"),
    icon: IconBrandWhatsapp,
    color: "#25D366",
    guide:
      "Use a WhatsApp Business Cloud API number. Provide your phone number ID and a permanent access token.",
    fields: [
      {
        key: "phone_number_id",
        label: "Phone number ID",
        placeholder: "100000000000000",
        required: true,
      },
      {
        key: "access_token",
        label: "Access token",
        placeholder: "EAAG...",
        type: "password",
        required: true,
        secret: true,
      },
      {
        key: "recipient",
        label: "Recipient number",
        placeholder: "+84901234567",
        required: true,
        help: "Number that receives the morning digest (E.164 format).",
      },
    ],
  },
  {
    id: "zalo",
    name: "Zalo",
    blurb: "Notify a Zalo user/group via the zca-js sidecar.",
    logo: SI("zalo"),
    icon: IconMessageCircle2,
    color: "#0068FF",
    guide:
      "Zalo gửi qua tài khoản cá nhân (zca-js sidecar). Bấm “Đăng nhập QR” bên dưới rồi quét mã bằng app Zalo của tài khoản gửi — không cần chạy lệnh nào. Sau đó nhập threadId người/nhóm nhận. (Cần sidecar backend/zalo_sidecar đang chạy: npm install → npm start.)",
    fields: [
      {
        key: "recipient",
        label: "Recipient threadId",
        placeholder: "Zalo user/group threadId",
        required: true,
        help: "ID của user (sender có thể nhắn) hoặc nhóm — xem zalo_sidecar/README.md.",
      },
      {
        key: "thread_type",
        label: "Thread type",
        placeholder: "user hoặc group (mặc định: user)",
        help: "Để 'user' nếu gửi cho một người, 'group' nếu gửi vào nhóm.",
      },
    ],
  },
  {
    id: "gmail",
    name: "Gmail",
    blurb: "Email the digest from a Gmail account.",
    logo: SI("gmail"),
    icon: IconBrandGmail,
    color: "#EA4335",
    guide:
      "Enable 2-Step Verification on the Google account and create an App Password (16 characters). Use it instead of your normal password.",
    fields: [
      {
        key: "email",
        label: "Gmail address",
        placeholder: "you@gmail.com",
        required: true,
      },
      {
        key: "app_password",
        label: "App password",
        placeholder: "xxxx xxxx xxxx xxxx",
        type: "password",
        required: true,
        secret: true,
        help: "16-char Google App Password — never your real password.",
      },
    ],
  },
  {
    id: "email",
    name: "Email (SMTP)",
    blurb: "Send via any custom SMTP server.",
    logo: SI("maildotru"),
    icon: IconMailFast,
    color: "#0F766E",
    guide:
      "Connect any SMTP provider (SendGrid, Mailgun, your own server) by entering the host, port, and credentials.",
    fields: [
      { key: "host", label: "SMTP host", placeholder: "smtp.example.com", required: true },
      { key: "port", label: "Port", placeholder: "587", type: "number", required: true },
      { key: "username", label: "Username", placeholder: "apikey or user", required: true },
      { key: "password", label: "Password", placeholder: "••••••••", type: "password", required: true, secret: true },
      { key: "from_address", label: "From address", placeholder: "digest@example.com", required: true },
    ],
  },
];

/** Pull a server-side error message out of an axios error, with a fallback. */
function errMessage(e: unknown, fallback: string): string {
  const data = (e as { response?: { data?: { error?: { message?: string } } } })?.response?.data;
  return data?.error?.message || fallback;
}

/** Brand logo on a tinted tile, falling back to the Tabler icon on load error. */
function BrandLogo({ platform, size }: { platform: Platform; size: number }) {
  const [failed, setFailed] = useState(false);
  const Icon = platform.icon;
  const tile = Math.round(size * 1.85);
  return (
    <div
      style={{
        width: tile,
        height: tile,
        borderRadius: Math.round(tile * 0.28),
        background: `${platform.color}14`,
        border: `1px solid ${platform.color}22`,
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
      }}
    >
      {failed ? (
        <Icon size={size} style={{ color: platform.color }} />
      ) : (
        <img
          alt={`${platform.name} logo`}
          src={platform.logo}
          width={size}
          height={size}
          style={{ width: size, height: size, objectFit: "contain" }}
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}

/** Zalo QR-login panel — drives the zca-js sidecar session from the UI so HR
 * never has to run the backend CLI. Polls the sidecar status while a QR is live. */
function ZaloLogin() {
  const [status, setStatus] = useState<ZaloQrStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  // Show the current session state on open; keep polling if a login is mid-flight.
  useEffect(() => {
    let alive = true;
    integrationService
      .zaloLoginStatus()
      .then((s) => {
        if (!alive) return;
        setStatus(s);
        if (!s.loggedIn && ["waiting_scan", "scanned", "starting"].includes(s.state)) poll();
      })
      .catch(() => {});
    return () => {
      alive = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const poll = () => {
    stopPolling();
    timer.current = setInterval(async () => {
      try {
        const s = await integrationService.zaloLoginStatus();
        setStatus(s);
        if (s.loggedIn || ["logged_in", "expired", "declined", "error"].includes(s.state)) {
          stopPolling();
          if (s.loggedIn) addToast({ title: "Zalo đã đăng nhập", color: "success" });
        }
      } catch {
        stopPolling();
      }
    }, 2000);
  };

  const start = async () => {
    setBusy(true);
    try {
      const s = await integrationService.zaloLoginStart();
      setStatus(s);
      if (!s.loggedIn) poll();
    } catch (e) {
      addToast({ title: "Không bắt đầu được đăng nhập Zalo", description: errMessage(e, "Sidecar chưa chạy?"), color: "danger" });
    } finally {
      setBusy(false);
    }
  };

  const loggedIn = status?.loggedIn;
  const st = status?.state;
  const showQr = st === "waiting_scan" && status?.image;

  return (
    <div className="rounded-xl border border-default-200 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <IconQrcode size={18} />
          <span className="text-small font-medium">Phiên Zalo (tài khoản gửi)</span>
        </div>
        {loggedIn ? (
          <Chip size="sm" color="success" variant="flat" startContent={<IconCheck size={13} />}>
            Đã đăng nhập
          </Chip>
        ) : (
          <Button size="sm" radius="full" variant="flat" isLoading={busy} onPress={start}>
            {st && ["waiting_scan", "scanned", "starting"].includes(st) ? "Đang chờ…" : "Đăng nhập QR"}
          </Button>
        )}
      </div>

      {!loggedIn && showQr && (
        <div className="mt-3 flex flex-col items-center gap-2">
          <img
            alt="Zalo QR"
            src={`data:image/png;base64,${status!.image}`}
            width={180}
            height={180}
            style={{ width: 180, height: 180, borderRadius: 12 }}
          />
          <span className="text-tiny text-default-500">Mở Zalo trên điện thoại tài khoản gửi → quét mã.</span>
        </div>
      )}
      {!loggedIn && st === "scanned" && (
        <p className="mt-2 text-tiny text-default-500">
          Đã quét{status?.user?.name ? ` (${status.user.name})` : ""} — đang hoàn tất đăng nhập…
        </p>
      )}
      {!loggedIn && st === "expired" && (
        <p className="mt-2 text-tiny text-warning">Mã QR đã hết hạn — bấm “Đăng nhập QR” để tạo mã mới.</p>
      )}
      {!loggedIn && st === "declined" && (
        <p className="mt-2 text-tiny text-warning">Đăng nhập bị từ chối trên điện thoại — thử lại.</p>
      )}
      {!loggedIn && st === "error" && status?.error && (
        <p className="mt-2 text-tiny text-danger">{status.error}</p>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  const [states, setStates] = useState<Record<string, IntegrationState>>({});
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<Platform | null>(null);

  const loadStates = async () => {
    const list = await integrationService.list();
    const map: Record<string, IntegrationState> = {};
    for (const s of list) map[s.platform] = s;
    setStates(map);
  };

  useEffect(() => {
    loadStates().finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <header style={{ marginBottom: 24 }}>
        <h1
          style={{
            font: "600 24px/1.1 var(--font-node-sans)",
            letterSpacing: "-0.025em",
            color: "var(--ink)",
            margin: "0 0 6px",
          }}
        >
          Integrations
        </h1>
        <p className="text-default-500 text-small">
          Connect a platform to receive the morning staffing digest each day.
        </p>
      </header>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {PLATFORMS.map((p) => {
            const state = states[p.id];
            const isConnected = !!state?.connected;
            const isError = state?.status === "error";
            return (
              <Card key={p.id} hoverable padding={16} onClick={() => setActive(p)}>
                <div className="flex items-center gap-3">
                  <BrandLogo platform={p} size={24} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">{p.name}</span>
                      {isConnected && !isError && (
                        <Chip
                          size="sm"
                          color="success"
                          variant="flat"
                          startContent={<IconCheck size={13} />}
                        >
                          Connected
                        </Chip>
                      )}
                      {isError && (
                        <Chip size="sm" color="danger" variant="flat">
                          Error
                        </Chip>
                      )}
                    </div>
                    <p className="truncate text-small text-default-400">{p.blurb}</p>
                  </div>
                  <Button
                    size="sm"
                    radius="full"
                    variant={isConnected ? "bordered" : "shadow"}
                    color={isConnected ? "default" : "primary"}
                    onPress={() => setActive(p)}
                  >
                    {isConnected ? "Manage" : "Connect"}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <ConnectModal
        platform={active}
        state={active ? states[active.id] : undefined}
        onClose={() => setActive(null)}
        onChanged={async () => {
          await loadStates();
        }}
        onCloseAfterSave={() => setActive(null)}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

interface ConnectModalProps {
  platform: Platform | null;
  state?: IntegrationState;
  onClose: () => void;
  onChanged: () => Promise<void>;
  onCloseAfterSave: () => void;
}

function ConnectModal({
  platform,
  state,
  onClose,
  onChanged,
  onCloseAfterSave,
}: ConnectModalProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [removing, setRemoving] = useState(false);

  const isConnected = !!state?.connected;
  const secretsSet = state?.secrets_set ?? [];

  // Prefill non-secret values from the saved config each time the modal opens.
  const formKey = platform?.id ?? "none";
  useEffect(() => {
    setValues({ ...(state?.config ?? {}) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formKey]);

  if (!platform) return null;

  const isSatisfied = (f: ConnectField) => {
    if (values[f.key]?.trim()) return true;
    // A required secret already saved counts as filled (blank = keep existing).
    return !!f.secret && secretsSet.includes(f.key);
  };
  const canSubmit = platform.fields.filter((f) => f.required).every(isSatisfied);

  const handleSave = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      // Only send fields the user actually typed (blank secrets stay untouched).
      const payload: Record<string, string> = {};
      for (const f of platform.fields) {
        const v = values[f.key];
        if (v !== undefined && (v.trim() !== "" || !f.secret)) payload[f.key] = v;
      }
      await integrationService.save(platform.id, payload);
      await onChanged();
      addToast({
        title: `${platform.name} ${isConnected ? "updated" : "connected"}`,
        description: "The morning digest will be delivered to this channel.",
        color: "success",
      });
      onCloseAfterSave();
    } catch (e) {
      addToast({ title: "Could not save", description: errMessage(e, "Please try again."), color: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await integrationService.test(platform.id);
      await onChanged();
      addToast({
        title: "Test message sent",
        description: `Check your ${platform.name} channel.`,
        color: "success",
      });
    } catch (e) {
      await onChanged();
      addToast({ title: "Test failed", description: errMessage(e, "Delivery failed."), color: "danger" });
    } finally {
      setTesting(false);
    }
  };

  const handleDisconnect = async () => {
    setRemoving(true);
    try {
      await integrationService.disconnect(platform.id);
      await onChanged();
      addToast({ title: `${platform.name} disconnected`, color: "default" });
      onCloseAfterSave();
    } finally {
      setRemoving(false);
    }
  };

  return (
    <Modal isOpen={!!platform} size="lg" scrollBehavior="inside" onClose={onClose}>
      <ModalContent>
        <ModalHeader className="flex items-center gap-3">
          <BrandLogo platform={platform} size={20} />
          <div className="flex flex-col">
            <span className="text-base font-semibold">Connect {platform.name}</span>
            <span className="text-tiny font-normal text-default-400">
              Morning digest delivery
            </span>
          </div>
        </ModalHeader>

        <ModalBody className="gap-4">
          <p className="rounded-xl bg-default-100 p-3 text-small text-default-600">
            {platform.guide}
          </p>

          {platform.id === "zalo" && <ZaloLogin />}

          <div className="flex flex-col gap-3">
            {platform.fields.map((f) => {
              const saved = f.secret && secretsSet.includes(f.key);
              return (
                <Input
                  key={f.key}
                  label={f.label}
                  labelPlacement="outside"
                  placeholder={saved ? "•••••••• (đã lưu — để trống nếu giữ nguyên)" : f.placeholder}
                  type={f.type ?? "text"}
                  isRequired={f.required && !saved}
                  description={f.help}
                  value={values[f.key] ?? ""}
                  onValueChange={(v) =>
                    setValues((prev) => ({ ...prev, [f.key]: v }))
                  }
                />
              );
            })}
          </div>

          {state?.status === "error" && state.last_error && (
            <p className="rounded-xl bg-danger-50 p-3 text-small text-danger">
              {state.last_error}
            </p>
          )}
        </ModalBody>

        <ModalFooter className="flex items-center justify-between">
          {isConnected ? (
            <Button
              color="danger"
              variant="light"
              radius="full"
              isLoading={removing}
              onPress={handleDisconnect}
            >
              Disconnect
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            {isConnected && (
              <Button
                variant="flat"
                radius="full"
                startContent={<IconSend size={16} />}
                isLoading={testing}
                onPress={handleTest}
              >
                Test
              </Button>
            )}
            <Button
              color="primary"
              radius="full"
              variant="shadow"
              isDisabled={!canSubmit}
              isLoading={saving}
              onPress={handleSave}
            >
              {isConnected ? "Update" : "Connect"}
            </Button>
          </div>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
