import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
  /** i18n key suffix under platforms.<id>.fields — the camelCase field name. */
  i18nKey: string;
  placeholder?: string;
  /** i18n key for a translated placeholder (overrides `placeholder` when set). */
  placeholderKey?: string;
  type?: FieldType;
  required?: boolean;
  /** Secret fields are write-only — never returned by the API. */
  secret?: boolean;
  hasHelp?: boolean;
}

interface Platform {
  id: string;
  name: string;
  logo: string;
  icon: TablerIcon;
  color: string;
  fields: ConnectField[];
}

const SI = (slug: string) => `https://cdn.simpleicons.org/${slug}`;
const FAVICON = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

const PLATFORMS: Platform[] = [
  {
    id: "slack",
    name: "Slack",
    logo: FAVICON("slack.com"),
    icon: IconBrandSlack,
    color: "#4A154B",
    fields: [
      {
        key: "webhook_url",
        i18nKey: "webhookUrl",
        placeholder: "https://hooks.slack.com/services/T000/B000/XXXX",
        required: true,
        secret: true,
        hasHelp: true,
      },
      { key: "channel", i18nKey: "channel", placeholder: "#staffing-digest" },
    ],
  },
  {
    id: "telegram",
    name: "Telegram",
    logo: SI("telegram"),
    icon: IconBrandTelegram,
    color: "#229ED9",
    fields: [
      {
        key: "bot_token",
        i18nKey: "botToken",
        placeholder: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        type: "password",
        required: true,
        secret: true,
      },
      {
        key: "chat_id",
        i18nKey: "chatId",
        placeholder: "-1001234567890",
        required: true,
        hasHelp: true,
      },
    ],
  },
  {
    id: "discord",
    name: "Discord",
    logo: SI("discord"),
    icon: IconBrandDiscord,
    color: "#5865F2",
    fields: [
      {
        key: "webhook_url",
        i18nKey: "webhookUrl",
        placeholder: "https://discord.com/api/webhooks/000/XXXX",
        required: true,
        secret: true,
      },
    ],
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    logo: SI("whatsapp"),
    icon: IconBrandWhatsapp,
    color: "#25D366",
    fields: [
      {
        key: "phone_number_id",
        i18nKey: "phoneNumberId",
        placeholder: "100000000000000",
        required: true,
      },
      {
        key: "access_token",
        i18nKey: "accessToken",
        placeholder: "EAAG...",
        type: "password",
        required: true,
        secret: true,
      },
      {
        key: "recipient",
        i18nKey: "recipient",
        placeholder: "+84901234567",
        required: true,
        hasHelp: true,
      },
    ],
  },
  {
    id: "zalo",
    name: "Zalo",
    logo: SI("zalo"),
    icon: IconMessageCircle2,
    color: "#0068FF",
    fields: [
      {
        key: "recipient",
        i18nKey: "recipient",
        placeholder: "Zalo user/group threadId",
        required: true,
        hasHelp: true,
      },
      {
        key: "thread_type",
        i18nKey: "threadType",
        placeholderKey: "platforms.zalo.fields.threadType.placeholder",
        hasHelp: true,
      },
    ],
  },
  {
    id: "gmail",
    name: "Gmail",
    logo: SI("gmail"),
    icon: IconBrandGmail,
    color: "#EA4335",
    fields: [
      {
        key: "email",
        i18nKey: "email",
        placeholder: "you@gmail.com",
        required: true,
      },
      {
        key: "app_password",
        i18nKey: "appPassword",
        placeholder: "xxxx xxxx xxxx xxxx",
        type: "password",
        required: true,
        secret: true,
        hasHelp: true,
      },
    ],
  },
  {
    id: "email",
    name: "Email (SMTP)",
    logo: SI("maildotru"),
    icon: IconMailFast,
    color: "#0F766E",
    fields: [
      { key: "host", i18nKey: "host", placeholder: "smtp.example.com", required: true },
      { key: "port", i18nKey: "port", placeholder: "587", type: "number", required: true },
      { key: "username", i18nKey: "username", placeholder: "apikey or user", required: true },
      { key: "password", i18nKey: "password", placeholder: "••••••••", type: "password", required: true, secret: true },
      { key: "from_address", i18nKey: "fromAddress", placeholder: "digest@example.com", required: true },
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
  const { t } = useTranslation("integrations");
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
          alt={t("logoAlt", { name: platform.name })}
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
  const { t } = useTranslation("integrations");
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
          if (s.loggedIn) addToast({ title: t("zaloLogin.loggedInToast"), color: "success" });
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
      addToast({ title: t("zaloLogin.startErrorTitle"), description: errMessage(e, t("zaloLogin.startErrorDesc")), color: "danger" });
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
          <span className="text-small font-medium">{t("zaloLogin.sessionTitle")}</span>
        </div>
        {loggedIn ? (
          <Chip size="sm" color="success" variant="flat" startContent={<IconCheck size={13} />}>
            {t("zaloLogin.loggedIn")}
          </Chip>
        ) : (
          <Button size="sm" radius="full" variant="flat" isLoading={busy} onPress={start}>
            {st && ["waiting_scan", "scanned", "starting"].includes(st)
              ? t("zaloLogin.waiting")
              : t("zaloLogin.loginQr")}
          </Button>
        )}
      </div>

      {!loggedIn && showQr && (
        <div className="mt-3 flex flex-col items-center gap-2">
          <img
            alt={t("zaloLogin.qrAlt")}
            src={`data:image/png;base64,${status!.image}`}
            width={180}
            height={180}
            style={{ width: 180, height: 180, borderRadius: 12 }}
          />
          <span className="text-tiny text-default-500">{t("zaloLogin.scanHint")}</span>
        </div>
      )}
      {!loggedIn && st === "scanned" && (
        <p className="mt-2 text-tiny text-default-500">
          {status?.user?.name
            ? t("zaloLogin.scannedNamed", { name: status.user.name })
            : t("zaloLogin.scanned")}
        </p>
      )}
      {!loggedIn && st === "expired" && (
        <p className="mt-2 text-tiny text-warning">{t("zaloLogin.expired")}</p>
      )}
      {!loggedIn && st === "declined" && (
        <p className="mt-2 text-tiny text-warning">{t("zaloLogin.declined")}</p>
      )}
      {!loggedIn && st === "error" && status?.error && (
        <p className="mt-2 text-tiny text-danger">{status.error}</p>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  const { t } = useTranslation("integrations");
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
          {t("page.title")}
        </h1>
        <p className="text-default-500 text-small">
          {t("page.subtitle")}
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
                          {t("card.connected")}
                        </Chip>
                      )}
                      {isError && (
                        <Chip size="sm" color="danger" variant="flat">
                          {t("card.error")}
                        </Chip>
                      )}
                    </div>
                    <p className="truncate text-small text-default-400">
                      {t(`platforms.${p.id}.blurb`)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    radius="full"
                    variant={isConnected ? "bordered" : "shadow"}
                    color={isConnected ? "default" : "primary"}
                    onPress={() => setActive(p)}
                  >
                    {isConnected ? t("card.manage") : t("card.connect")}
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
  const { t } = useTranslation("integrations");
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
        title: isConnected
          ? t("toast.updatedTitle", { name: platform.name })
          : t("toast.connectedTitle", { name: platform.name }),
        description: t("toast.savedDesc"),
        color: "success",
      });
      onCloseAfterSave();
    } catch (e) {
      addToast({ title: t("toast.saveFailedTitle"), description: errMessage(e, t("toast.saveFailedDesc")), color: "danger" });
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
        title: t("toast.testSentTitle"),
        description: t("toast.testSentDesc", { name: platform.name }),
        color: "success",
      });
    } catch (e) {
      await onChanged();
      addToast({ title: t("toast.testFailedTitle"), description: errMessage(e, t("toast.testFailedDesc")), color: "danger" });
    } finally {
      setTesting(false);
    }
  };

  const handleDisconnect = async () => {
    setRemoving(true);
    try {
      await integrationService.disconnect(platform.id);
      await onChanged();
      addToast({ title: t("toast.disconnectedTitle", { name: platform.name }), color: "default" });
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
            <span className="text-base font-semibold">
              {t("modal.connectTitle", { name: platform.name })}
            </span>
            <span className="text-tiny font-normal text-default-400">
              {t("modal.subtitle")}
            </span>
          </div>
        </ModalHeader>

        <ModalBody className="gap-4">
          <p className="rounded-xl bg-default-100 p-3 text-small text-default-600">
            {t(`platforms.${platform.id}.guide`)}
          </p>

          {platform.id === "zalo" && <ZaloLogin />}

          <div className="flex flex-col gap-3">
            {platform.fields.map((f) => {
              const saved = f.secret && secretsSet.includes(f.key);
              const fieldPlaceholder = f.placeholderKey
                ? t(f.placeholderKey)
                : f.placeholder;
              return (
                <Input
                  key={f.key}
                  label={t(`platforms.${platform.id}.fields.${f.i18nKey}.label`)}
                  labelPlacement="outside"
                  placeholder={saved ? t("modal.savedPlaceholder") : fieldPlaceholder}
                  type={f.type ?? "text"}
                  isRequired={f.required && !saved}
                  description={
                    f.hasHelp
                      ? t(`platforms.${platform.id}.fields.${f.i18nKey}.help`)
                      : undefined
                  }
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
              {t("modal.disconnect")}
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
                {t("modal.test")}
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
              {isConnected ? t("modal.update") : t("modal.connect")}
            </Button>
          </div>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
