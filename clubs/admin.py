from django.contrib import admin

from .models import Club, Player, StaffMembership, Team


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'country')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'club', 'gender', 'is_own')
    list_filter = ('club', 'is_own', 'gender')
    search_fields = ('name',)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'known_name', 'club', 'current_team', 'primary_position')
    list_filter = ('club', 'primary_position')
    search_fields = ('full_name', 'known_name')
    raw_id_fields = ('current_team',)


@admin.register(StaffMembership)
class StaffMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'club', 'role', 'is_active')
    list_filter = ('club', 'role', 'is_active')
