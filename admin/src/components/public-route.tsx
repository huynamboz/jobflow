import { useMemo } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthStore } from "@/stores/auth.store";
import { canAccessAdmin } from "@/lib/access";
import { STORAGE_KEYS } from "@/config/api";

export function PublicRoute() {
  const location = useLocation();
  const { isAuthenticated, user } = useAuthStore();

  const hasToken = useMemo(() => {
    return !!user || !!localStorage.getItem(STORAGE_KEYS.accessToken);
  }, [user]);

  // Only redirect into the app when the user is actually allowed there.
  // Redirecting an authenticated-but-unauthorized user (e.g. role "candidate")
  // would ping-pong with AdminRoute's role gate → infinite redirect loop.
  if (hasToken && isAuthenticated && canAccessAdmin(user)) {
    const from = (location.state as { from?: Location })?.from?.pathname || "/admin";
    return <Navigate replace to={from} />;
  }

  return <Outlet />;
}
