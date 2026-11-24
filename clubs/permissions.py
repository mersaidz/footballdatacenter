"""
Role → capability matrix. The single place that decides who sees what.

Views never check roles directly; they ask for a capability. Adding a new
role or tightening access is a one-line change here, pinned by a truth-table
test (clubs/tests/test_permissions.py).

Deliberate asymmetries:
- club_admin manages integrations and staff but does NOT see medical details.
  Administrative power != clinical access (GDPR "special category" data).
- Coaches see availability status (can he train / play?) but not diagnoses.
- Scouts work with match/event data only: no load, no medical, no availability.
"""
from __future__ import annotations

from enum import StrEnum

from .models import StaffMembership

Role = StaffMembership.Role


class Cap(StrEnum):
    VIEW_FOOTBALL_DATA = 'view_football_data'      # players, teams, matches, events
    VIEW_PHYSICAL_LOAD = 'view_physical_load'      # GPS / OpenField metrics
    VIEW_AVAILABILITY = 'view_availability'        # status: available / modified / out
    VIEW_MEDICAL_DETAILS = 'view_medical_details'  # diagnosis, clinical notes
    EDIT_MEDICAL = 'edit_medical'
    MANAGE_IDENTITIES = 'manage_identities'        # confirm / reject cross-provider ID links
    MANAGE_INTEGRATIONS = 'manage_integrations'    # provider API keys
    MANAGE_STAFF = 'manage_staff'


_PERFORMANCE_STAFF = {Cap.VIEW_FOOTBALL_DATA, Cap.VIEW_PHYSICAL_LOAD, Cap.VIEW_AVAILABILITY}
_MEDICAL_STAFF = _PERFORMANCE_STAFF | {Cap.VIEW_MEDICAL_DETAILS, Cap.EDIT_MEDICAL}

ROLE_CAPABILITIES: dict[str, frozenset[Cap]] = {
    Role.CLUB_ADMIN: frozenset({
        Cap.VIEW_FOOTBALL_DATA, Cap.MANAGE_INTEGRATIONS, Cap.MANAGE_STAFF, Cap.MANAGE_IDENTITIES,
    }),
    Role.SPORTING_DIRECTOR: frozenset(_PERFORMANCE_STAFF),
    Role.HEAD_COACH: frozenset(_PERFORMANCE_STAFF),
    Role.ASSISTANT_COACH: frozenset(_PERFORMANCE_STAFF),
    Role.ANALYST: frozenset(_PERFORMANCE_STAFF | {Cap.MANAGE_IDENTITIES}),
    Role.SPORTS_SCIENTIST: frozenset(_PERFORMANCE_STAFF),
    Role.PHYSIO: frozenset(_MEDICAL_STAFF),
    Role.DOCTOR: frozenset(_MEDICAL_STAFF),
    Role.SCOUT: frozenset({Cap.VIEW_FOOTBALL_DATA}),
}


def get_membership(user, club_id) -> StaffMembership | None:
    if user is None or not user.is_authenticated:
        return None
    return (
        StaffMembership.objects
        .select_related('club')
        .filter(user=user, club_id=club_id, is_active=True)
        .first()
    )


def capabilities_for_role(role: str | None) -> frozenset[Cap]:
    if not role:
        return frozenset()
    return ROLE_CAPABILITIES.get(role, frozenset())


def has_cap(membership: StaffMembership | None, cap: Cap) -> bool:
    if membership is None or not membership.is_active:
        return False
    return cap in capabilities_for_role(membership.role)
