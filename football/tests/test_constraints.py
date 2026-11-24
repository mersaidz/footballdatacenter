from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from clubs.models import Player, Team
from football.models import Match, PlayerAvailability, PlayerLoad, TrainingSession

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(club):
    home = Team.objects.create(club=club, name='Astana', is_own=True)
    away = Team.objects.create(club=club, name='Tobol')
    match = Match.objects.create(club=club, home_team=home, away_team=away, kickoff=timezone.now())
    session = TrainingSession.objects.create(club=club, team=home, start=timezone.now(), md_code='MD-1')
    player = Player.objects.create(club=club, full_name='Player One', current_team=home)
    return home, away, match, session, player


def test_match_teams_must_differ(club, setup):
    home = setup[0]
    with pytest.raises(IntegrityError):
        Match.objects.create(club=club, home_team=home, away_team=home, kickoff=timezone.now())


@pytest.mark.parametrize('ctx', ['both', 'none'])
def test_load_needs_exactly_one_context(club, setup, ctx):
    _, _, match, session, player = setup
    kwargs = {'both': dict(match=match, training_session=session), 'none': {}}[ctx]
    with pytest.raises(IntegrityError):
        PlayerLoad.objects.create(club=club, player=player, provider='catapult_openfield', **kwargs)


def test_one_load_per_player_match_provider(club, setup):
    _, _, match, _, player = setup
    PlayerLoad.objects.create(club=club, player=player, match=match, provider='catapult_openfield')
    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerLoad.objects.create(club=club, player=player, match=match, provider='catapult_openfield')
    # A second provider for the same match is fine (e.g. OpenField + SkillCorner).
    PlayerLoad.objects.create(club=club, player=player, match=match, provider='skillcorner')


def test_return_not_before_start(club, setup):
    player = setup[4]
    with pytest.raises(IntegrityError):
        PlayerAvailability.objects.create(
            club=club, player=player, status='unavailable', start_date=date(2024, 5, 10),
            actual_return=date(2024, 5, 10) - timedelta(days=1),
        )


def test_diagnosis_encrypted_at_rest(club, setup):
    from django.db import connection
    player = setup[4]
    a = PlayerAvailability.objects.create(club=club, player=player, status='unavailable',
                                          start_date=date(2024, 5, 10), diagnosis='Hamstring grade 2')
    with connection.cursor() as cur:
        cur.execute('SELECT diagnosis FROM football_playeravailability WHERE id=%s', [a.pk])
        assert 'Hamstring' not in cur.fetchone()[0]
