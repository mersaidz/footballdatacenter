from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from clubs.models import Player, Team
from core.models import AuditLog
from football.models import ActivityPeriod, PeriodLoad, PeriodRoleMapping, PlayerLoad, TrainingSession

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def match_session(club):
    """A recorded match whose halves were named "A" and "B" — nobody could classify them."""
    team = Team.objects.create(club=club, name='First Team', is_own=True)
    s = TrainingSession.objects.create(club=club, team=team, start=T0, session_type='match', md_code='MD',
                                       name='J02')
    player = Player.objects.create(club=club, full_name='Player One')
    periods = {}
    for i, (name, start, length, dist) in enumerate([('Warm Up', 0, 15, 1500), ('A', 20, 47, 4800),
                                                     ('B', 82, 48, 4500)]):
        per = ActivityPeriod.objects.create(
            club=club, training_session=s, provider='catapult_openfield', external_id=f'x{i}', name=name,
            normalized_name=name.lower(), start=T0 + timedelta(minutes=start),
            end=T0 + timedelta(minutes=start + length), role='warm_up' if i == 0 else 'unknown',
            role_source='dictionary' if i == 0 else 'none')
        PeriodLoad.objects.create(club=club, player=player, period=per, provider='catapult_openfield',
                                  total_distance_m=dist, duration_min=Decimal(length))
        periods[name] = per
    PlayerLoad.objects.create(club=club, player=player, training_session=s, provider='catapult_openfield',
                              total_distance_m=10800, duration_min=Decimal('110'),
                              extra_metrics={'activity_total': {'total_distance_m': 10800, 'duration_min': 110.0}})
    return s, periods, player


def test_review_queue_lists_unknown(make_member, club, match_session):
    _, c = make_member(club, 'sports_scientist')
    rows = c.get(f'/api/clubs/{club.pk}/periods/?needs_review=true').data['results']
    assert [r['name'] for r in rows] == ['A', 'B']


def test_coach_can_read_but_not_assign(make_member, club, match_session):
    _, periods, _ = match_session
    _, c = make_member(club, 'head_coach')
    assert c.get(f'/api/clubs/{club.pk}/periods/').status_code == 200
    r = c.post(f'/api/clubs/{club.pk}/periods/{periods["A"].pk}/assign_role/', {'role': 'first_half'})
    assert r.status_code == 403


def test_assign_roles_recomputes_match_load(make_member, club, match_session):
    s, periods, player = match_session
    _, c = make_member(club, 'analyst')
    url = f'/api/clubs/{club.pk}/periods/'
    assert c.post(url + f'{periods["A"].pk}/assign_role/', {'role': 'first_half'}).status_code == 200
    r = c.post(url + f'{periods["B"].pk}/assign_role/', {'role': 'second_half'})
    assert r.status_code == 200 and r.data['loads_recomputed'] == 1
    load = PlayerLoad.objects.get(player=player, training_session=s)
    assert load.load_basis == 'match_periods' and load.total_distance_m == 9300 and load.duration_min == 95
    assert PeriodRoleMapping.objects.filter(club=club, normalized_name='a', role='first_half').exists()
    assert AuditLog.objects.filter(action=AuditLog.Action.PERIOD_ROLE_CHANGED).count() == 2


def test_remember_teaches_other_periods_with_same_name(make_member, club, match_session):
    s, periods, _ = match_session
    twin = ActivityPeriod.objects.create(
        club=club, training_session=s, provider='catapult_openfield', external_id='twin', name='A',
        normalized_name='a', start=T0 + timedelta(hours=5), end=T0 + timedelta(hours=6))
    _, c = make_member(club, 'analyst')
    r = c.post(f'/api/clubs/{club.pk}/periods/{periods["A"].pk}/assign_role/', {'role': 'first_half'})
    assert r.data['periods_updated'] == 2
    twin.refresh_from_db()
    assert (twin.role, twin.role_source) == ('first_half', 'club')


def test_unknown_is_not_an_assignable_role(make_member, club, match_session):
    _, periods, _ = match_session
    _, c = make_member(club, 'analyst')
    r = c.post(f'/api/clubs/{club.pk}/periods/{periods["A"].pk}/assign_role/', {'role': 'unknown'})
    assert r.status_code == 400


def test_other_club_cannot_see_periods(make_member, club, other_club, match_session):
    _, c = make_member(other_club, 'analyst')
    assert c.get(f'/api/clubs/{club.pk}/periods/').status_code == 404
