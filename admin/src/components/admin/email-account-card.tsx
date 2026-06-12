import { useCallback, useEffect, useState } from "react";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { addToast } from "@heroui/toast";
import { IconMail } from "@tabler/icons-react";

import { mailService, type CredentialStatus } from "@/services/mail.service";

const T = {
  accent: "#167a7a", success: "oklch(0.62 0.17 155)", danger: "oklch(0.60 0.22 25)",
  ink2: "oklch(0.38 0.015 265)", ink4: "oklch(0.72 0.008 265)",
  surface: "#fff", line: "rgba(226,232,240,0.7)",
};

/** 026: link / unlink an employee's Gmail (app password). Shared by the
 *  employee info page (and previously the detail header). */
export default function EmailAccountCard({ employeeId }: { employeeId: number }) {
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
      addToast({ title: "Email linked", color: "success" });
      setOpen(false); setPw(""); load();
    } catch (e: any) {
      addToast({ title: "Link failed", description: e?.response?.data?.error?.message || "Check the app password", color: "danger" });
    } finally { setBusy(false); }
  };
  const doUnlink = async () => {
    setBusy(true);
    try { await mailService.unlink(employeeId); addToast({ title: "Email unlinked", color: "default" }); load(); }
    finally { setBusy(false); }
  };

  const linked = cred?.linked && cred?.status === "active";
  const error = cred?.status === "error";
  return (
    <div style={{ borderRadius: 12, border: `1px solid ${error ? T.danger : T.line}`, background: T.surface, padding: "12px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <IconMail size={16} style={{ color: linked ? T.success : T.ink4 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: T.ink2 }}>
          {linked ? `Email linked · ${cred?.gmail_address}` : error ? `Email error · ${cred?.gmail_address}` : "No email linked"}
        </span>
        {error && <span style={{ fontSize: 11.5, color: T.danger }}>{cred?.last_error?.slice(0, 60)}</span>}
        <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {linked || error
            ? <Button size="sm" variant="light" color="danger" isLoading={busy} onPress={doUnlink}>Unlink</Button>
            : <Button size="sm" variant="flat" color="primary" onPress={() => setOpen((o) => !o)}>{open ? "Cancel" : "Link Gmail"}</Button>}
        </span>
      </div>
      {open && !linked && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          <Input size="sm" label="Gmail address" value={addr} onValueChange={setAddr} type="email" placeholder="employee@gmail.com" />
          <Input size="sm" label="App password" value={pw} onValueChange={setPw} type="password" placeholder="16-char app password" />
          <div style={{ fontSize: 11, color: T.ink4, lineHeight: 1.5 }}>
            Tạo App Password tại Google Account → Security → 2-Step Verification → App passwords (cần bật 2FA).
            Hệ thống sẽ chỉ gửi đơn ứng tuyển từ tài khoản này và đọc các thư trả lời về đơn đó. Mật khẩu được mã hoá, không hiển thị lại.
          </div>
          <Button size="sm" color="primary" isLoading={busy} isDisabled={!addr || !pw} onPress={doLink}>Verify & link</Button>
        </div>
      )}
    </div>
  );
}
