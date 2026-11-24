import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.models import User
from clubs.models import Player, StaffMembership, Team

pytestmark = pytest.mark.django_db


def test_player_cannot_point_to_other_clubs_team(club, other_club):
    foreign_team = Team.objects.create(club=other_club, name='Kairat')
    with pytest.raises(ValidationError):
        Player.objects.create(club=club, full_name='X', current_team=foreign_team)


def test_full_clean_reports_tenant_mismatch(club, other_club):
    foreign_team = Team.objects.create(club=other_club, name='Kairat')
    p = Player(club=club, full_name='X', current_team=foreign_team)
    with pytest.raises(ValidationError) as exc:
        p.full_clean()
    assert 'current_team' in exc.value.message_dict


def test_one_active_membership_per_club(club):
    u = User.objects.create_user(email='a@b.com', password='pw-123456789')
    StaffMembership.objects.create(user=u, club=club, role='analyst')
    with pytest.raises(IntegrityError):
        StaffMembership.objects.create(user=u, club=club, role='scout')


def test_user_can_work_for_two_clubs(club, other_club):
    u = User.objects.create_user(email='a@b.com', password='pw-123456789')
    StaffMembership.objects.create(user=u, club=club, role='analyst')
    StaffMembership.objects.create(user=u, club=other_club, role='scout')
    assert u.memberships.count() == 2
