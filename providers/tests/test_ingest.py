import pytest

from clubs.models import Player, Team
from core.models import AuditLog
from football.models import Event, Match, MatchAppearance
from providers.models import ExternalIdentity, RawPayload
from providers.services.ingest import ingest_season

pytestmark = pytest.mark.django_db


def test_own_team_filter_and_flag(ingested, club):
    # Only match 100 involves FC Astana; match 101 (Kairat vs Tobol) is skipped.
    assert len(ingested.matches) == 1 and not ingested.errors
    assert Match.objects.filter(club=club).count() == 1
    assert Team.objects.get(club=club, name='FC Astana').is_own
    assert not Team.objects.get(club=club, name='Kairat Almaty').is_own


def test_rows_created(ingested, club):
    m = Match.objects.get(club=club)
    assert m.season.name == '2024' and m.season.competition.name == 'Premier League'
    assert m.duration_minutes == 93
    assert Event.objects.filter(match=m).count() == 5
    assert MatchAppearance.objects.filter(match=m).count() == 4
    assert Player.objects.filter(club=club).count() == 4


def test_minutes_played(ingested, club):
    mins = {a.player.full_name: a.minutes_played for a in MatchAppearance.objects.select_related('player')}
    assert mins['Marin Tomasov'] == 70
    assert mins['Stanislav Basmanov'] == 23    # on at 70, match lasted 93
    assert mins['Abzal Beysebekov'] == 93


def test_reingest_is_idempotent(ingested, club, sb_connector):
    before = (Event.objects.count(), MatchAppearance.objects.count(), Player.objects.count(),
              ExternalIdentity.objects.count(), RawPayload.objects.count())
    ingest_season(club, sb_connector, '1', '2', own_team_name='FC Astana')
    after = (Event.objects.count(), MatchAppearance.objects.count(), Player.objects.count(),
             ExternalIdentity.objects.count(), RawPayload.objects.count())
    assert before == after


def test_events_linked_to_players(ingested):
    shot = Event.objects.get(event_type='shot')
    assert shot.player.full_name == 'Marin Tomasov' and shot.team.name == 'FC Astana'


def test_sync_is_audited(ingested, club):
    log = AuditLog.objects.get(action=AuditLog.Action.SYNC_SUCCESS)
    assert log.club_id == club.pk and log.extra_info['events'] == 5


def test_one_bad_match_does_not_stop_season(club, sb_connector, monkeypatch):
    original = sb_connector.fetch_events

    def flaky(match_id):
        if match_id == '101':
            raise ConnectionError('provider timeout')
        return original(match_id)

    monkeypatch.setattr(sb_connector, 'fetch_events', flaky)
    # Match 100 has fixtures; 101 fails on events → recorded as error, 100 still ingested.
    monkeypatch.setattr(sb_connector, 'fetch_lineups',
                        lambda mid: type(sb_connector).fetch_lineups(sb_connector, '100'))
    summary = ingest_season(club, sb_connector, '1', '2')
    assert len(summary.matches) == 1 and len(summary.errors) == 1
