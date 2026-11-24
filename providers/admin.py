from django.contrib import admin

from .models import ExternalIdentity, ProviderAccount, RawPayload


@admin.register(ProviderAccount)
class ProviderAccountAdmin(admin.ModelAdmin):
    list_display = ('club', 'provider', 'is_active', 'last_synced_at')
    exclude = ('api_key', 'api_secret')  # secrets are set via shell/API, never displayed


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = ('provider', 'entity_type', 'external_id', 'external_name', 'status', 'method', 'confidence')
    list_filter = ('club', 'provider', 'entity_type', 'status', 'method')
    search_fields = ('external_id', 'external_name')


@admin.register(RawPayload)
class RawPayloadAdmin(admin.ModelAdmin):
    list_display = ('provider', 'resource_type', 'external_id', 'schema_version', 'created_at')
    list_filter = ('club', 'provider', 'resource_type')
    exclude = ('payload',)
