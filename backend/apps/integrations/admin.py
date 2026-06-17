from django.contrib import admin

from apps.integrations.models import Integration


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ("platform", "status", "last_sent_at", "updated_at")
    list_filter = ("status", "platform")
    readonly_fields = ("config_encrypted", "created_at", "updated_at", "last_sent_at")
    # config_encrypted is shown read-only ciphertext; never edit secrets in admin.
