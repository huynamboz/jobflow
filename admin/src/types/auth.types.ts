export type UserRole = "candidate" | "recruiter" | "admin";

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_staff: boolean;
  notify_daily_digest?: boolean;
}

// Django simplejwt response
export interface LoginResponse {
  access: string;
  refresh: string;
}

export interface MeResponse {
  success: boolean;
  data: User;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}
