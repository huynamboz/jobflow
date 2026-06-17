import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import { Eye, EyeOff, Lock, User } from "lucide-react";

import { useAuthStore } from "@/stores/auth.store";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation("auth");
  const login = useAuthStore((state) => state.login);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/admin";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) { setError(t("login.errorRequired")); return; }

    setIsLoading(true);
    setError("");
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.errorInvalid"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f8f9fa] dark:bg-default-100 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500">
            <span className="text-xl font-bold text-white">J</span>
          </div>
          <h1 className="text-2xl font-bold text-default-900">{t("login.title")}</h1>
          <p className="mt-1 text-sm text-default-500">{t("login.subtitle")}</p>
        </div>

        {/* Form */}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Input
            label={t("login.username")}
            placeholder={t("login.usernamePlaceholder")}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            startContent={<User className="size-4 text-default-400" />}
            autoComplete="username"
          />
          <Input
            label={t("login.password")}
            placeholder={t("login.passwordPlaceholder")}
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            startContent={<Lock className="size-4 text-default-400" />}
            endContent={
              <button type="button" onClick={() => setShowPassword((v) => !v)}>
                {showPassword
                  ? <EyeOff className="size-4 text-default-400" />
                  : <Eye className="size-4 text-default-400" />}
              </button>
            }
            autoComplete="current-password"
          />

          {error && (
            <p className="text-sm text-danger text-center">{error}</p>
          )}

          <Button
            type="submit"
            color="primary"
            className="w-full"
            isLoading={isLoading}
          >
            {t("login.submit")}
          </Button>
        </form>
      </div>
    </div>
  );
}
