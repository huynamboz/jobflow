import type { User } from "@/types/auth.types";

/**
 * Single source of truth for "may this user enter the /admin area".
 * AdminRoute (the gate) and PublicRoute (the redirect-away guard) MUST agree on
 * this predicate — otherwise an authenticated-but-unauthorized user ping-pongs
 * between /login and /admin forever (Maximum update depth exceeded).
 */
export function canAccessAdmin(user: User | null): boolean {
  return user?.role === "admin" || user?.role === "recruiter";
}
