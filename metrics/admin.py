from django.contrib import admin

from .models import MetricDefinition, MetricSet, ProviderMetric


@admin.register(ProviderMetric)
class ProviderMetricAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'unit_type', 'provider', 'club')
    list_filter = ('provider', 'unit_type')
    search_fields = ('name', 'slug')


@admin.register(MetricDefinition)
class MetricDefinitionAdmin(admin.ModelAdmin):
    list_display = ('label', 'key', 'category', 'aggregation', 'unit', 'provider_slug', 'core_field', 'enabled')
    list_filter = ('category', 'aggregation', 'enabled')
    search_fields = ('label', 'key', 'provider_slug')


@admin.register(MetricSet)
class MetricSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'club', 'owner', 'display', 'is_default')
