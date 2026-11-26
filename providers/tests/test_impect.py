"""
IMPECT connector + ingest. Fixtures are hand-written in IMPECT's JSON shape (the open
data may not be redistributed, so none of it is copied here).
"""
from datetime import date, datetime, timezone

import pytest
import responses
from django.core.management import call_command

from clubs.models import Player, Team
from football.models import Event, Match, MatchAppearance, PlayerLoad, PlayerMatchKpis, TrainingSession
from metrics.models import ProviderMetric
from providers.connectors.impect import (
    ImpectApiSource, ImpectConnector, ImpectError, ImpectOpenData, parse_clock, to_pitch,
)
from providers.models import ExternalIdentity
from providers.services.impect_ingest import ingest_impect

pytestmark = pytest.mark.django_db

KPIS = [{'id': 0, 'name': 'BYPASSED_OPPONENTS', 'details': {'label': 'Bypassed Opponents', 'definition': 'Packing.'}},
        {'id': 1, 'name': 'GOALS', 'details': {'label': 'Goals'}},
        {'id': 2, 'name': 'SHOT_XG', 'details': {'label': 'Shot xG'}},
        {'id': 3, 'name': 'OWNGOALS', 'details': {'label': 'Own goals'}}]
PLAYERS = [  # squad 41 "Werkself", squad 37 "Bullen"
    {'id': 1, 'firstname': 'Ana', 'lastname': 'Keeper', 'commonname': 'A. Keeper', 'birthdate': '1990-01-01', 'leg': 'RIGHT'},
    {'id': 2, 'firstname': 'Bo', 'lastname': 'Winger', 'commonname': 'B. Winger', 'birthdate': '1999-02-02', 'leg': 'LEFT'},
    {'id': 3, 'firstname': 'Cy', 'lastname': 'Striker', 'commonname': 'C. Striker', 'birthdate': '1997-03-03', 'leg': 'RIGHT'},
    {'id': 9, 'firstname': 'Dan', 'lastname': 'Opponent', 'commonname': 'D. Opponent', 'birthdate': '1995-04-04', 'leg': 'RIGHT'},
]


WERKSELF_LINEUP = {'id': 41, 'players': [{'id': 1, 'shirtNumber': 1}, {'id': 2, 'shirtNumber': 10}, {'id': 3, 'shirtNumber': 9}],
                   'startingPositions': [{'playerId': 1, 'position': 'GOALKEEPER'}, {'playerId': 2, 'position': 'LEFT_WINGER'}]}
BULLEN_LINEUP = {'id': 37, 'players': [{'id': 9, 'shirtNumber': 5}],
                 'startingPositions': [{'playerId': 9, 'position': 'CENTRAL_DEFENDER'}]}
WERKSELF_KPIS = {'id': 41, 'players': [
    {'id': 1, 'position': 'GOALKEEPER', 'playDuration': 5700, 'kpis': [{'kpiId': 0, 'value': 1.0}]},
    {'id': 2, 'position': 'LEFT_WINGER', 'playDuration': 5700, 'kpis': [{'kpiId': 0, 'value': 40.0}, {'kpiId': 1, 'value': 1.0}]},
    {'id': 3, 'position': 'CENTER_FORWARD', 'playDuration': 1200, 'kpis': [{'kpiId': 2, 'value': 0.4}]}]}
BULLEN_KPIS = {'id': 37, 'players': [
    {'id': 9, 'position': 'CENTRAL_DEFENDER', 'playDuration': 5700, 'kpis': [{'kpiId': 3, 'value': 1.0}]}]}


def lineup(mid, werkself_home):
    a, b = (WERKSELF_LINEUP, BULLEN_LINEUP) if werkself_home else (BULLEN_LINEUP, WERKSELF_LINEUP)
    return {'id': mid, 'squadHome': a, 'squadAway': b}


def pkpis(mid, werkself_home):
    a, b = (WERKSELF_KPIS, BULLEN_KPIS) if werkself_home else (BULLEN_KPIS, WERKSELF_KPIS)
    return {'matchId': mid, 'squadHome': a, 'squadAway': b}


EVENTS = [
    {'id': 100, 'gameTime': {'gameTime': '00:00.0000', 'gameTimeInSec': 0.0}, 'squadId': 41,
     'player': {'id': 2, 'position': 'LEFT_WINGER'}, 'actionType': 'DRIBBLE', 'action': 'DRIBBLE', 'periodId': 1,
     'start': {'adjCoordinates': {'x': 0.0, 'y': 20.0}}, 'end': {'adjCoordinates': {'x': 15.0, 'y': 18.0}},
     'result': 'SUCCESS', 'pressure': 0.0, 'sequenceIndex': 0},
    {'id': 101, 'gameTime': {'gameTime': '90:00.0000 (+02:10.0000)', 'gameTimeInSec': 12930.0}, 'squadId': 41,
     'player': {'id': 2, 'position': 'LEFT_WINGER'}, 'actionType': 'SHOT', 'action': 'CLOSE_RANGE_SHOT', 'periodId': 2,
     'start': {'adjCoordinates': {'x': 41.5, 'y': -2.0}}, 'end': {'adjCoordinates': {'x': 52.5, 'y': 0.0}},
     'shot': {'distance': 11.2}, 'result': 'SUCCESS', 'pressure': 60.0, 'sequenceIndex': 7},
    {'id': 102, 'gameTime': {'gameTime': '10:00.0000', 'gameTimeInSec': 600.0}, 'squadId': None, 'player': None,
     'actionType': 'NO_VIDEO', 'periodId': 1},
]
EVENT_KPIS = [{'eventId': 101, 'kpiId': 2, 'value': 0.31, 'playerId': 2}, {'eventId': 100, 'kpiId': 0, 'value': 3.0, 'playerId': 2}]


class FakeSource(ImpectOpenData):
    def __init__(self):
        super().__init__(base_url='http://unused')
        self.calls = []

    def _get(self, rel):
        self.calls.append(rel)
        data = {
            'iterations.json': [{'id': 743, 'season': '23/24', 'competition': {'id': 2, 'name': '1. Bundesliga', 'gender': 'MALE'}}],
            'squads/squads_743.json': [{'id': 41, 'name': 'Werkself 04'}, {'id': 37, 'name': 'Bullen'}],
            'players/players_743.json': PLAYERS,
            'matches/matches_743.json': [
                {'id': 1, 'homeSquadId': 41, 'awaySquadId': 37, 'scheduledDate': '2023-08-19T13:30:00Z', 'available': True,
                 'matchDay': {'name': '1. Spieltag'}},
                {'id': 2, 'homeSquadId': 37, 'awaySquadId': 41, 'scheduledDate': '2023-08-26T13:30:00Z', 'available': True},
                {'id': 3, 'homeSquadId': 41, 'awaySquadId': 37, 'scheduledDate': '2024-05-18T13:30:00Z', 'available': False}],
            'kpi_definitions.json': KPIS,
            'lineups/lineups_1.json': lineup(1, True), 'lineups/lineups_2.json': lineup(2, False),
            'player_kpis/player_kpis_1.json': pkpis(1, True), 'player_kpis/player_kpis_2.json': pkpis(2, False),
            'events/events_1.json': EVENTS, 'events/events_2.json': [],
            'events_kpis/events_kpis_1.json': EVENT_KPIS, 'events_kpis/events_kpis_2.json': [],
        }
        return data[rel]


def test_clock_and_pitch_conversion():
    assert parse_clock('45:00.1090') == (45, 0)
    assert parse_clock('90:00.0000 (+05:47.6470)') == (95, 47)
    # centre spot → (52.5, 34); attacking +x, left touchline at +y → y=0
    assert to_pitch({'adjCoordinates': {'x': 0, 'y': 0}}) == (52.5, 34.0)
    assert to_pitch({'adjCoordinates': {'x': 52.5, 'y': 34}}) == (105.0, 0.0)
    assert to_pitch({'coordinates': {'x': 1}}) == (None, None)


@pytest.fixture
def our_team(club):
    team = Team.objects.create(club=club, name='First Team', is_own=True)
    sessions = TrainingSession.objects.create(
        club=club, team=team, start=datetime(2026, 8, 16, 17, tzinfo=timezone.utc),
        end=datetime(2026, 8, 16, 19, tzinfo=timezone.utc), session_type='match')
    for name, hsr, mins in [('Gil Keeper', 5, 95), ('Ivo Runner', 400, 90), ('Rui Sub', 300, 20), ('Tó Bench', 280, 10)]:
        p = Player.objects.create(club=club, full_name=name, current_team=team, date_of_birth=date(2000, 1, 1))
        PlayerLoad.objects.create(club=club, player=p, training_session=sessions, provider='catapult_openfield',
                                  duration_min=mins, hsr_distance_m=hsr, total_distance_m=8000)
    return team


def test_ingest_season_with_demo_link(club, our_team):
    conn = ImpectConnector(FakeSource())
    s = ingest_impect(club, conn, 743, events_squad='werkself', demo_link_to=our_team)
    assert (s.matches, s.matches_with_events, s.errors) == (2, 1, [])     # unavailable match skipped
    # demo links: GK ↔ GK, then most minutes ↔ most minutes; flagged as demo
    links = {o: t for o, t, _, _ in s.demo_links}
    assert links == {'Gil Keeper': 'Ana Keeper', 'Ivo Runner': 'Bo Winger', 'Rui Sub': 'Cy Striker'}
    assert ExternalIdentity.objects.filter(club=club, provider='impect', method='demo').count() == 3
    ivo = Player.objects.get(full_name='Ivo Runner')
    assert (ivo.primary_position, ivo.preferred_foot, ivo.shirt_number) == ('W', 'left', 10)
    assert ivo.current_team == our_team                                     # still our player
    # matches, score (goal + opponent own goal), appearances
    m1 = Match.objects.get(kickoff__date=date(2023, 8, 19))
    assert (m1.home_team.name, m1.away_team.name, m1.home_score, m1.away_score) == ('Werkself 04', 'Bullen', 2, 0)
    assert m1.season.name == '23/24' and m1.season.competition.name == '1. Bundesliga'
    app = MatchAppearance.objects.get(match=m1, player=ivo)
    assert (app.started, app.position, app.shirt_number) == (True, 'W', 10)
    sub = MatchAppearance.objects.get(match=m1, player__full_name='Rui Sub')
    assert not sub.started and sub.minutes_played == 20 and sub.position == 'CF'
    # KPIs per match, keyed by KPI name; all players of the league get rows
    k = PlayerMatchKpis.objects.get(match=m1, player=ivo)
    assert k.kpis == {'BYPASSED_OPPONENTS': 40.0, 'GOALS': 1.0} and k.position == 'LEFT_WINGER' and k.minutes == 95
    assert PlayerMatchKpis.objects.filter(club=club).count() == 8
    assert Player.objects.filter(club=club, full_name='Dan Opponent').exists()
    # events only for the chosen squad's matches; platform pitch convention; xg + packing on events
    evs = list(Event.objects.filter(match=m1).order_by('sequence'))
    assert len(evs) == 2 and Event.objects.exclude(match=m1).count() == 0
    carry, shot = evs
    assert (carry.event_type, carry.x, carry.y, carry.end_x, carry.attributes['bypassed_opponents']) == ('carry', 52.5, 14.0, 67.5, 3.0)
    assert (shot.event_type, shot.minute, shot.second, shot.period, shot.xg, shot.x) == ('shot', 92, 10, 2, 0.31, 94.0)
    assert shot.period_ms == 2930000 and shot.player == ivo
    # IMPECT KPIs join the searchable metric catalogue
    assert ProviderMetric.objects.get(club=club, provider='impect', slug='BYPASSED_OPPONENTS').name == 'Bypassed Opponents'


def test_reingest_is_idempotent(club, our_team):
    for _ in range(2):
        ingest_impect(club, ImpectConnector(FakeSource()), 743, events_squad='werkself', demo_link_to=our_team)
    assert Match.objects.filter(club=club).count() == 2
    assert PlayerMatchKpis.objects.filter(club=club).count() == 8 and Event.objects.count() == 2
    assert ExternalIdentity.objects.filter(club=club, provider='impect', method='demo').count() == 3


def test_open_data_is_never_stored_raw(club, our_team):
    from providers.models import RawPayload
    ingest_impect(club, ImpectConnector(FakeSource()), 743, events_squad='werkself')
    assert not RawPayload.objects.filter(club=club, provider='impect').exists()


def test_unknown_squad_lists_the_options(club):
    with pytest.raises(ValueError, match='Werkself 04'):
        ingest_impect(club, ImpectConnector(FakeSource()), 743, events_squad='Barcelona')


@responses.activate
def test_api_source_logs_in_refreshes_and_reports_403():
    responses.post('https://login.impect.com/auth/realms/production/protocol/openid-connect/token',
                   json={'access_token': 't1'})
    responses.get('https://api.impect.com/v5/customerapi/iterations/', status=401)
    responses.get('https://api.impect.com/v5/customerapi/iterations/', json={'data': [{'id': 1}]})
    responses.get('https://api.impect.com/v5/customerapi/iterations/9/squads', status=403)
    src = ImpectApiSource('me@club', 'pw', sleep=lambda s: None)
    assert src.iterations() == [{'id': 1}]
    assert len([c for c in responses.calls if 'token' in c.request.url]) == 2      # re-login after 401
    assert 'username=me%40club' in responses.calls[0].request.body
    with pytest.raises(ImpectError, match='not included'):
        src.squads(9)


@responses.activate
def test_api_source_bad_credentials():
    responses.post('https://login.impect.com/auth/realms/production/protocol/openid-connect/token', status=401)
    with pytest.raises(ImpectError, match='IMPECT_USERNAME'):
        ImpectApiSource('x', 'y', sleep=lambda s: None).iterations()


def test_command_open_data(club, our_team, monkeypatch, capsys):
    monkeypatch.setattr('providers.management.commands.ingest_impect.ImpectOpenData', lambda cache_dir=None: FakeSource())
    call_command('ingest_impect', '--club', club.slug, '--open-data', '--iteration', '743', '--squad', 'werkself',
                 '--demo-link', 'First Team')
    out = capsys.readouterr().out
    assert '2 matches' in out and 'Ivo Runner' in out and 'not for redistribution' in out


def test_football_profile_api(club, our_team, make_member):
    from football.services import football_profile as fp
    ingest_impect(club, ImpectConnector(FakeSource()), 743, events_squad='werkself', demo_link_to=our_team)
    ivo = Player.objects.get(full_name='Ivo Runner')
    _, coach = make_member(club, 'head_coach')
    fp.MIN_MINUTES = 0
    try:
        r = coach.get(f'/api/clubs/{club.pk}/players/{ivo.pk}/football/')
    finally:
        fp.MIN_MINUTES = 450
    assert r.status_code == 200
    d = r.data
    assert (d['competition'], d['season'], d['main_position'], d['peers'], d['minutes'], d['matches']) == \
        ('1. Bundesliga', '23/24', 'LEFT_WINGER', 'wingers', 190, 2)
    assert d['demo_link'] == {'source_player': 'Bo Winger', 'squad': 'Werkself 04', 'position': 'LEFT_WINGER'}
    packing = next(k for g in d['groups'] for k in g['kpis'] if k['kpi'] == 'BYPASSED_OPPONENTS')
    assert packing['per90'] == round(80 / 190 * 90, 2) and packing['percentile'] == 50   # only winger: himself
    assert [m['result'] for m in d['match_log']] == ['W', 'W'] and d['match_log'][0]['opponent'] == 'Bullen'
    shot = d['shots'][0]
    assert (shot['x'], shot['y'], shot['xg'], shot['goal'], shot['minute'], shot['kind'], shot['pressure']) == \
        (94.0, 36.0, 0.31, True, 92, 'CLOSE_RANGE_SHOT', 60.0) and len(d['shots']) == 1
    assert d['heat']['cols'] == 12 and sum(map(sum, d['heat']['season'])) == 2      # carry + shot
    assert d['passes'] == []
    assert d['carries'][0]['end_x'] == 67.5 and d['average_position'] is not None
    gk = Player.objects.get(full_name='Tó Bench')                 # no IMPECT data
    assert coach.get(f'/api/clubs/{club.pk}/players/{gk.pk}/football/').status_code == 404
