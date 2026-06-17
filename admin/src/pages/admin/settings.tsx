import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Switch } from "@heroui/switch";
import { Button } from "@heroui/button";
import { Divider } from "@heroui/divider";
import { Bell, User, Shield } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "@/stores/auth.store";
import { apiClient } from "@/lib/api-client";

export default function SettingsPage() {
  const { t } = useTranslation("settings");
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const [digestEnabled, setDigestEnabled] = useState(
    user?.notify_daily_digest ?? true,
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user) setDigestEnabled(user.notify_daily_digest ?? true);
  }, [user]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const { data } = await apiClient.patch("/auth/me/", {
        notify_daily_digest: digestEnabled,
      });
      if (data.success && data.data) {
        setUser(data.data);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <h1
        style={{
          font: "600 24px/1.1 var(--font-node-sans)",
          letterSpacing: "-0.025em",
          color: "var(--ink)",
          margin: "0 0 24px",
        }}
      >
        {t("title")}
      </h1>

      <Card className="mb-4">
        <CardHeader className="flex gap-3">
          <User size={20} />
          <span className="font-semibold">{t("account.title")}</span>
        </CardHeader>
        <Divider />
        <CardBody className="gap-3">
          <div className="flex justify-between">
            <span className="text-default-500">{t("account.username")}</span>
            <span className="font-medium">{user?.username}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-500">{t("account.email")}</span>
            <span className="font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-500">{t("account.role")}</span>
            <span className="font-medium capitalize">{user?.role}</span>
          </div>
        </CardBody>
      </Card>

      <Card className="mb-4">
        <CardHeader className="flex gap-3">
          <Bell size={20} />
          <span className="font-semibold">{t("notifications.title")}</span>
        </CardHeader>
        <Divider />
        <CardBody className="gap-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">
                {t("notifications.dailyDigest.label")}
              </p>
              <p className="text-small text-default-400">
                {t("notifications.dailyDigest.description")}
              </p>
            </div>
            <Switch
              isSelected={digestEnabled}
              onValueChange={setDigestEnabled}
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="flex gap-3">
          <Shield size={20} />
          <span className="font-semibold">{t("security.title")}</span>
        </CardHeader>
        <Divider />
        <CardBody>
          <p className="text-small text-default-400">
            {t("security.passwordHint")}
          </p>
        </CardBody>
      </Card>

      <div className="flex justify-end mt-4 gap-2">
        {saved && (
          <span className="text-success self-center text-small">
            {t("savedSuccessfully")}
          </span>
        )}
        <Button
          color="primary"
          isLoading={saving}
          onPress={handleSave}
        >
          {t("saveChanges")}
        </Button>
      </div>
    </div>
  );
}
