import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Switch } from "@heroui/switch";
import { Button } from "@heroui/button";
import { Divider } from "@heroui/divider";
import { Bell, User, Shield } from "lucide-react";

import { useAuthStore } from "@/stores/auth.store";
import { apiClient } from "@/lib/api-client";

export default function SettingsPage() {
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
        Settings
      </h1>

      <Card className="mb-4">
        <CardHeader className="flex gap-3">
          <User size={20} />
          <span className="font-semibold">Account information</span>
        </CardHeader>
        <Divider />
        <CardBody className="gap-3">
          <div className="flex justify-between">
            <span className="text-default-500">Username</span>
            <span className="font-medium">{user?.username}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-500">Email</span>
            <span className="font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-500">Role</span>
            <span className="font-medium capitalize">{user?.role}</span>
          </div>
        </CardBody>
      </Card>

      <Card className="mb-4">
        <CardHeader className="flex gap-3">
          <Bell size={20} />
          <span className="font-semibold">Notifications</span>
        </CardHeader>
        <Divider />
        <CardBody className="gap-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Daily email digest</p>
              <p className="text-small text-default-400">
                Receive a daily summary email of high-scoring employee–job matches
                every morning at 8:00
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
          <span className="font-semibold">Security</span>
        </CardHeader>
        <Divider />
        <CardBody>
          <p className="text-small text-default-400">
            To change your password, use the password-change function via the API.
          </p>
        </CardBody>
      </Card>

      <div className="flex justify-end mt-4 gap-2">
        {saved && (
          <span className="text-success self-center text-small">
            Saved successfully
          </span>
        )}
        <Button
          color="primary"
          isLoading={saving}
          onPress={handleSave}
        >
          Save changes
        </Button>
      </div>
    </div>
  );
}
