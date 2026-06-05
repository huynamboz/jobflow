from rest_framework.permissions import BasePermission


class IsHRStaff(BasePermission):
    """Allow only authenticated users with role in (admin, recruiter).

    Recruiter = HR/manager seat. Candidate role explicitly forbidden so
    end-users (if added later for self-service) cannot poke at staffing data.
    """

    message = "HR staff only (admin or recruiter role)."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return getattr(user, "role", None) in ("admin", "recruiter")


class IsAdminUserRole(BasePermission):
    """Stricter than IsHRStaff — admin role only (used for destructive ops)."""

    message = "Admin role required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return getattr(user, "role", None) == "admin" or user.is_superuser
