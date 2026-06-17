import { useCallback, useEffect, useState } from "react";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Chip } from "@heroui/chip";
import { addToast } from "@heroui/toast";
import { IconMail, IconMailCheck, IconMailExclamation, IconShieldLock } from "@tabler/icons-react";
import { Trans, useTranslation } from "react-i18next";

import { Card } from "@/components/ui/card";
import { mailService, type CredentialStatus } from "@/services/mail.service";

/** 026: link / unlink an employee's Gmail (app password). Shared by the
 *  employee info page (and previously the detail header). */
export default function EmailAccountCard({ employeeId }: { employeeId: number }) {
  const { t } = useTranslation("employees");
  const [cred, setCred] = useState<CredentialStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [addr, setAddr] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    mailService.credentialStatus(employeeId).then(setCred).catch(() => setCred({ linked: false }));
  }, [employeeId]);
  useEffect(() => { load(); }, [load]);

  const doLink = async () => {
    setBusy(true);
    try {
      await mailService.link(employeeId, addr.trim(), pw);
      addToast({ title: t("emailAccount.linkedToast"), color: "success" });
      setOpen(false); setPw(""); load();
    } catch (e: any) {
      addToast({ title: t("emailAccount.linkFailed"), description: e?.response?.data?.error?.message || t("emailAccount.linkFailedDesc"), color: "danger" });
    } finally { setBusy(false); }
  };
  const doUnlink = async () => {
    setBusy(true);
    try { await mailService.unlink(employeeId); addToast({ title: t("emailAccount.unlinkedToast"), color: "default" }); load(); }
    finally { setBusy(false); }
  };

  const linked = cred?.linked && cred?.status === "active";
  const error = cred?.status === "error";

  return (
    <Card padding={16} className={error ? "border-l-2 border-l-danger/60" : ""}>
      <div className="flex items-center gap-3">
        <span className={`shrink-0 ${linked ? "text-success" : error ? "text-danger" : "text-default-400"}`}>
          {linked ? <IconMailCheck size={22} stroke={1.75} /> : error ? <IconMailExclamation size={22} stroke={1.75} /> : <IconMail size={22} stroke={1.75} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {linked ? t("emailAccount.linked") : error ? t("emailAccount.errorTitle") : t("emailAccount.noEmail")}
            </span>
            {linked && <Chip size="sm" variant="flat" color="success">{t("emailAccount.active")}</Chip>}
            {error && <Chip size="sm" variant="flat" color="danger">{t("emailAccount.error")}</Chip>}
          </div>
          <div className="mt-0.5 truncate text-xs text-default-500">
            {cred?.gmail_address || t("emailAccount.linkHint")}
          </div>
          {error && cred?.last_error && <div className="mt-1 truncate text-xs text-danger">{cred.last_error.slice(0, 80)}</div>}
        </div>
        <div className="shrink-0">
          {linked || error
            ? <Button size="sm" variant="flat" color="danger" isLoading={busy} onPress={doUnlink}>{t("emailAccount.unlink")}</Button>
            : <Button size="sm" variant="flat" color="primary" onPress={() => setOpen((o) => !o)}>{open ? t("common:actions.cancel") : t("emailAccount.linkGmail")}</Button>}
        </div>
      </div>

      {open && !linked && (
        <div className="mt-4 flex flex-col gap-3 border-t border-default-100 pt-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input size="sm" label={t("emailAccount.gmailAddress")} value={addr} onValueChange={setAddr} type="email" placeholder="employee@gmail.com" autoComplete="off" />
            <Input size="sm" label={t("emailAccount.appPassword")} value={pw} onValueChange={setPw} type="password" placeholder={t("emailAccount.appPasswordPlaceholder")} autoComplete="off" />
          </div>
          <div className="flex items-start gap-2 rounded-xl bg-default-50 p-3 text-xs leading-relaxed text-default-500">
            <IconShieldLock size={26} stroke={1.5} className="shrink-0 text-default-400" />
            <span>
              <Trans i18nKey="emailAccount.appPasswordHelp" t={t}>
                Create an App Password at <span className="font-medium text-default-600">Google Account → Security → 2-Step Verification → App passwords</span> (2FA required).
              </Trans>
            </span>
          </div>
          <Button size="sm" color="primary" className="self-start" isLoading={busy} isDisabled={!addr || !pw} onPress={doLink}>
            {t("emailAccount.verifyAndLink")}
          </Button>
        </div>
      )}
    </Card>
  );
}
