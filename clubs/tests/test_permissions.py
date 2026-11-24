"""Truth table for the role → capability matrix. A change here is a security decision."""
import pytest

from clubs.models import StaffMembership
from clubs.permissions import Cap, ROLE_CAPABILITIES, capabilities_for_role, has_cap

R = StaffMembership.Role

EXPECTED = {
    #                       football load  avail  med-det edit-med ident  integ  staff
    R.CLUB_ADMIN:          (True,  False, False, False,  False,   True,  True,  True),
    R.SPORTING_DIRECTOR:   (True,  True,  True,  False,  False,   False, False, False),
    R.HEAD_COACH:          (True,  True,  True,  False,  False,   False, False, False),
    R.ASSISTANT_COACH:     (True,  True,  True,  False,  False,   False, False, False),
    R.ANALYST:             (True,  True,  True,  False,  False,   True,  False, False),
    R.SPORTS_SCIENTIST:    (True,  True,  True,  False,  False,   False, False, False),
    R.PHYSIO:              (True,  True,  True,  True,   True,    False, False, False),
    R.DOCTOR:              (True,  True,  True,  True,   True,    False, False, False),
    R.SCOUT:               (True,  False, False, False,  False,   False, False, False),
}
CAPS = [Cap.VIEW_FOOTBALL_DATA, Cap.VIEW_PHYSICAL_LOAD, Cap.VIEW_AVAILABILITY, Cap.VIEW_MEDICAL_DETAILS,
        Cap.EDIT_MEDICAL, Cap.MANAGE_IDENTITIES, Cap.MANAGE_INTEGRATIONS, Cap.MANAGE_STAFF]


def test_every_role_is_covered():
    assert set(ROLE_CAPABILITIES) == set(R.values) == set(EXPECTED)


@pytest.mark.parametrize('role', list(EXPECTED))
def test_truth_table(role):
    caps = capabilities_for_role(role)
    assert tuple(c in caps for c in CAPS) == EXPECTED[role]


def test_unknown_or_empty_role_has_nothing():
    assert capabilities_for_role('janitor') == frozenset()
    assert capabilities_for_role(None) == frozenset()


def test_inactive_membership_has_nothing():
    m = StaffMembership(role=R.DOCTOR, is_active=False)
    assert not has_cap(m, Cap.VIEW_MEDICAL_DETAILS)
    assert not has_cap(None, Cap.VIEW_FOOTBALL_DATA)
