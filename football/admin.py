from django.contrib import admin

from .models import (
    ActivityPeriod, Competition, Match, MatchAppearance, PeriodLoad, PeriodRoleMapping, PlayerAvailability, PlayerLoad,
    Season, TrainingSession,
)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'club')


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('competition', 'name', 'club')


class AppearanceInline(admin.TabularInline):
    model = MatchAppearance
    extra = 0
    raw_id_fields = ('player', 'team')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'home_score', 'away_score', 'stage', 'club')
    list_filter = ('club', 'status')
    inlines = [AppearanceInline]


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('team', 'start', 'md_code', 'session_type')


@admin.register(PlayerLoad)
class PlayerLoadAdmin(admin.ModelAdmin):
    list_display = ('player', 'match', 'training_session', 'provider', 'total_distance_m', 'hsr_distance_m')
    raw_id_fields = ('player', 'match', 'training_session')


@admin.register(PlayerAvailability)
class PlayerAvailabilityAdmin(admin.ModelAdmin):
    # Diagnosis / notes intentionally NOT shown in admin lists: medical data goes through the audited API.
    list_display = ('player', 'status', 'reason', 'start_date', 'expected_return', 'actual_return')
    exclude = ('diagnosis', 'clinical_notes')
    raw_id_fields = ('player',)


@admin.register(ActivityPeriod)
class ActivityPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'role_source', 'role_confidence', 'start', 'training_session', 'match')
    list_filter = ('role', 'role_source')
    search_fields = ('name',)


@admin.register(PeriodLoad)
class PeriodLoadAdmin(admin.ModelAdmin):
    list_display = ('player', 'period', 'duration_min', 'total_distance_m', 'hsr_distance_m')
    raw_id_fields = ('player', 'period')


@admin.register(PeriodRoleMapping)
class PeriodRoleMappingAdmin(admin.ModelAdmin):
    list_display = ('normalized_name', 'role', 'club', 'created_by')
