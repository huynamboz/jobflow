from django.contrib import admin

from apps.employees.models import Employee, EmployeeJobMatch


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "email", "position", "seniority", "created_at")
    list_filter = ("seniority", "is_parse_failed")
    search_fields = ("full_name", "email", "position")
    readonly_fields = ("parsed_at", "is_parse_failed", "created_at", "updated_at")


@admin.register(EmployeeJobMatch)
class EmployeeJobMatchAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "job", "status", "match_score", "updated_at")
    list_filter = ("status",)
    search_fields = ("employee__full_name", "job__title")
    raw_id_fields = ("employee", "job", "assigned_to")
    readonly_fields = ("applied_at", "won_at", "lost_at", "created_at", "updated_at")
