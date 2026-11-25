"""
OpenField connector + physical ingest. HTTP is mocked with `responses`;
payload shapes mirror what scripts/openfield_probe.py recorded on a live account.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import responses

from clubs.models import Player, Team
from core.models import AuditLog
from football.models import Match, PlayerLoad, TrainingSession
from football.services.matchday import md_code_for
from providers.connectors.openfield import OpenFieldClient, OpenFieldConnector, OpenFieldError
from providers.models import ExternalIdentity
from providers.services.physical_ingest import ingest_physical

BASE = 'https://connect-eu.catapultsports.com/api/v6'
TOKEN = 'test-token-abc'


def ts(y, m, d, h=10):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())


def tag(type_name, name):
    return {'id': f'{type_name}-{name}', 'tag_type_id': 'x', 'name': name, 'tag_type_name': type_name, 'tag_name': name}


ATHLETES = [
    {'id': 'ath-1', 'first_name': 'Marin', 'last_name': 'Tomasov', 'nickname': '', 'is_deleted': 0,
     'date_of_birth': ts(1987, 8, 31, 0), 'jersey': '10', 'position_name': 'W', 'current_team_id': 't-1',
     'velocity_max': 8.75},                       # personal best 31.5 km/h
    {'id': 'ath-2', 'first_name': 'Abzal', 'last_name': 'Beysebekov', 'nickname': '', 'is_deleted': 0,
     'date_of_birth': 0, 'jersey': '4', 'velocity_max': 7.5},   # personal best 27.0 km/h
    {'id': 'ath-old', 'first_name': 'Gone', 'last_name': 'Player', 'is_deleted': 1, 'date_of_birth': 0},
]

ACTIVITIES = [
    {'id': 'act-md', 'name': '26_27_J01_Rebordosa', 'start_time': ts(2026, 11, 14, 15), 'end_time': ts(2026, 11, 14, 17),
     'tag_list': [tag('DayCode', 'MD'), tag('Device', 'GPS')], 'tags': ['MD', 'GPS'], 'athlete_count': 2},
    {'id': 'act-md1', 'name': '26_27_UT015', 'start_time': ts(2026, 11, 13), 'end_time': ts(2026, 11, 13, 11),
     'tag_list': [tag('DayCode', 'MD-1')], 'tags': ['MD-1'], 'athlete_count': 2},
    {'id': 'act-untagged', 'name': 'Activity 202611169223', 'start_time': ts(2026, 11, 16), 'end_time': None,
     'tag_list': [tag('Device', 'GPS')], 'tags': ['GPS'], 'athlete_count': 1},
]

PARAMETERS = [{'slug': s, 'name': s} for s in (
    'total_distance', 'total_duration', 'field_time', 'total_player_load', 'max_vel', 'high_speed_distance',
    'velocity_band5_total_distance', 'velocity_band6_total_distance', 'velocity_band7_total_distance',
    'velocity_band8_total_distance', 'gen2_acceleration_band7plus_total_effort_count',
    'gen2_acceleration_band2plus_total_effort_count', 'player_load_per_minute',
)]


def stat_row(activity, athlete, **metrics):
    row = {'athlete_id': athlete, 'activity_id': activity, 'athlete_name': 'X', 'date': '14/11/2026',
           'start_time': 0, 'end_time': 0, 'field_time': 5400.0, 'total_duration': 5600,
           'total_distance': 10450, 'total_player_load': 980.4, 'max_vel': 8.75,
           'velocity_band5_total_distance': 520, 'velocity_band6_total_distance': 180,
           'velocity_band7_total_distance': 40, 'velocity_band8_total_distance': 0,
           'gen2_acceleration_band7plus_total_effort_count': 31,
           'gen2_acceleration_band2plus_total_effort_count': 37, 'high_speed_distance': 700,
           'player_load_per_minute': 10.9}
    row.update(metrics)
    return row


STATS = [
    stat_row('act-md', 'ath-1'), stat_row('act-md', 'ath-2', total_distance=11020),
    stat_row('act-md1', 'ath-1', total_distance=4300), stat_row('act-md1', 'ath-2', total_distance=4100),
    stat_row('act-untagged', 'ath-1', total_distance=0, max_vel=0),
]


@pytest.fixture
def api():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.get(f'{BASE}/athletes', json=ATHLETES)
        rsps.get(f'{BASE}/activities', json=ACTIVITIES)
        rsps.get(f'{BASE}/parameters', json=PARAMETERS)

        def stats_cb(request):
            body = json.loads(request.body)
            ids = set(body['filters'][0]['values'])
            return 200, {}, json.dumps([r for r in STATS if r['activity_id'] in ids])

        rsps.add_callback(responses.POST, f'{BASE}/stats', callback=stats_cb, content_type='application/json')
        yield rsps


@pytest.fixture
def connector():
    return OpenFieldConnector(token=TOKEN, region='eu')


@pytest.fixture
def own_team(club):
    return Team.objects.create(club=club, name='FC Astana', is_own=True)


RANGE = (datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 30, tzinfo=timezone.utc))


# --- client --------------------------------------------------------------------

class TestClient:
    def test_bearer_auth_and_429_retry(self):
        sleeps = []
        with responses.RequestsMock() as rsps:
            rsps.get(f'{BASE}/teams', status=429, headers={'Retry-After': '3'})
            rsps.get(f'{BASE}/teams', json=[{'id': 't'}])
            client = OpenFieldClient(BASE, TOKEN, sleep=sleeps.append)
            assert client.get('/teams') == [{'id': 't'}]
            assert rsps.calls[0].request.headers['Authorization'] == f'Bearer {TOKEN}'
        assert sleeps == [3.0]

    def test_error_message_never_contains_token(self):
        with responses.RequestsMock() as rsps:
            rsps.get(f'{BASE}/athletes', status=401, body=f'invalid token {TOKEN}')
            with pytest.raises(OpenFieldError) as exc:
                OpenFieldClient(BASE, TOKEN).get('/athletes')
        assert TOKEN not in str(exc.value) and '401' in str(exc.value)

    def test_gives_up_after_retries(self):
        with responses.RequestsMock() as rsps:
            for _ in range(4):
                rsps.get(f'{BASE}/athletes', status=503)
            with pytest.raises(OpenFieldError, match='after 4 attempts'):
                OpenFieldClient(BASE, TOKEN, sleep=lambda s: None).get('/athletes')

    def test_missing_token(self, monkeypatch):
        monkeypatch.delenv('OPENFIELD_API_TOKEN', raising=False)
        with pytest.raises(OpenFieldError, match='token is missing'):
            OpenFieldConnector(token='')


# --- normalisation -------------------------------------------------------------

class TestNormalize:
    def test_athletes(self, connector):
        players = {p.external_id: p for p in connector.normalize_athletes(ATHLETES)}
        assert 'ath-old' not in players                              # deleted upstream
        assert players['ath-1'].full_name == 'Marin Tomasov'
        assert players['ath-1'].date_of_birth == date(1987, 8, 31)  # epoch seconds → date
        assert players['ath-2'].date_of_birth is None                # 0 = not set

    def test_activities_day_codes_and_match_flag(self, connector):
        acts = {a.external_id: a for a in connector.normalize_activities(ACTIVITIES)}
        assert acts['act-md'].is_match and acts['act-md'].day_code == 'MD'
        assert not acts['act-md1'].is_match and acts['act-md1'].day_code == 'MD-1'
        assert acts['act-untagged'].day_code == '' and acts['act-untagged'].end is None
        assert acts['act-md'].start == datetime(2026, 11, 14, 15, tzinfo=timezone.utc)

    def test_detail_endpoint_tag_shape(self, connector):
        # /activities/{id} has tag_list = ["MD"] and tags = [objects]
        detail = {**ACTIVITIES[0], 'tag_list': ['MD', 'GPS'], 'tags': [tag('DayCode', 'MD')]}
        assert connector.normalize_activities([detail])[0].day_code == 'MD'

    def test_optional_name_pattern_marks_matches(self):
        c = OpenFieldConnector(token=TOKEN, match_name_pattern=r'_J\d+_|friendly')
        act = {**ACTIVITIES[2], 'name': '26_27_Friendly_PenafielU23'}
        assert c.normalize_activities([act])[0].is_match

    def test_metrics(self, connector):
        load = connector.normalize_stats([STATS[0]])[0]
        assert load.total_distance_m == 10450
        assert load.hsr_distance_m == 520 + 180 + 40 + 0       # bands 5-8
        assert load.sprint_distance_m == 180 + 40 + 0          # bands 6-8
        assert load.accelerations == 31 and load.decelerations == 37
        assert load.duration_min == 90.0                       # field_time 5400 s
        assert load.max_speed_kmh == 31.5                      # 8.75 m/s
        assert load.player_load == pytest.approx(980.4)
        assert load.extra_metrics['high_speed_distance'] == 700

    def test_speed_already_in_kmh_not_converted_twice(self, connector):
        assert connector.normalize_stats([stat_row('a', 'b', max_vel=32.4)])[0].max_speed_kmh == 32.4

    def test_metric_map_override_from_account(self, club):
        from providers.models import ProviderAccount
        acc = ProviderAccount.objects.create(
            club=club, provider='catapult_openfield', api_key=TOKEN,
            config={'metric_map': {'hsr_distance_m': ['high_speed_distance']}},
        )
        load = OpenFieldConnector(acc).normalize_stats([STATS[0]])[0]
        assert load.hsr_distance_m == 700

    def test_only_existing_slugs_requested(self, api, connector):
        slugs = connector.requested_slugs()
        assert 'total_distance' in slugs and 'athlete_id' in slugs
        assert 'ima_band2_accel_count' not in slugs   # not in this account's catalogue


# --- ingest --------------------------------------------------------------------

pytestmark = pytest.mark.django_db


def test_sessions_and_loads_created(api, connector, club, own_team):
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.activities == 3 and not summary.errors
    assert summary.loads == 5
    sessions = {s.name: s for s in TrainingSession.objects.filter(club=club)}
    assert sessions['26_27_J01_Rebordosa'].session_type == 'match'   # no event-data match to attach to
    assert sessions['26_27_UT015'].md_code == 'MD-1'                 # from OpenField tag
    assert sessions['Activity 202611169223'].md_code == 'MD+2'       # computed: 2 days after the match


def test_match_activity_links_to_event_data_match(api, connector, club, own_team):
    opponent = Team.objects.create(club=club, name='Rebordosa')
    match = Match.objects.create(club=club, home_team=own_team, away_team=opponent,
                                 kickoff=datetime(2026, 11, 14, 15, 30, tzinfo=timezone.utc))
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.linked_to_matches == 1
    assert PlayerLoad.objects.filter(match=match).count() == 2
    assert not TrainingSession.objects.filter(session_type='match').exists()


def test_players_resolved_and_matched_by_dob(api, connector, club, own_team):
    existing = Player.objects.create(club=club, full_name='Marin Tomasov', date_of_birth=date(1987, 8, 31))
    ingest_physical(club, connector, own_team, *RANGE)
    ident = ExternalIdentity.objects.get(provider='catapult_openfield', external_id='ath-1')
    assert ident.object_id == existing.pk and ident.method == 'exact' and ident.status == 'confirmed'
    assert Player.objects.filter(club=club).count() == 2   # Tomasov reused, Beysebekov created


def test_resync_is_idempotent(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    counts = (TrainingSession.objects.count(), PlayerLoad.objects.count(), Player.objects.count(),
              ExternalIdentity.objects.count())
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.sessions_created == 0 and summary.sessions_updated == 3
    assert counts == (TrainingSession.objects.count(), PlayerLoad.objects.count(), Player.objects.count(),
                      ExternalIdentity.objects.count())


def test_athlete_removed_upstream_loses_load(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    STATS_BACKUP = STATS[:]
    try:
        STATS.remove(STATS[1])   # ath-2 dropped from the match activity
        ingest_physical(club, connector, own_team, *RANGE)
    finally:
        STATS[:] = STATS_BACKUP
    session = TrainingSession.objects.get(name='26_27_J01_Rebordosa')
    assert session.loads.count() == 1


def test_stored_values(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    load = PlayerLoad.objects.get(training_session__name='26_27_J01_Rebordosa', player__full_name='Marin Tomasov')
    assert load.total_distance_m == 10450 and load.hsr_distance_m == 740 and load.sprint_distance_m == 220
    assert float(load.max_speed_kmh) == 31.5 and float(load.duration_min) == 90.0
    assert load.extra_metrics['player_load_per_minute'] == 10.9


def test_sync_is_audited_without_secrets(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    log = AuditLog.objects.get(action=AuditLog.Action.SYNC_SUCCESS, provider='catapult_openfield')
    assert log.extra_info['loads'] == 5
    assert TOKEN not in json.dumps(log.extra_info)


def test_stats_failure_is_recorded_not_fatal(club, own_team, connector):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.get(f'{BASE}/athletes', json=ATHLETES)
        rsps.get(f'{BASE}/activities', json=ACTIVITIES)
        rsps.get(f'{BASE}/parameters', json=PARAMETERS)
        rsps.post(f'{BASE}/stats', status=400, body='bad filter')
        summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.errors and summary.loads == 0
    assert TrainingSession.objects.count() == 3   # sessions still recorded


# --- match-day codes ---------------------------------------------------------------

@pytest.mark.parametrize('day,expected', [
    (date(2026, 11, 14), 'MD'),
    (date(2026, 11, 15), 'MD+1'),
    (date(2026, 11, 16), 'MD+2'),
    (date(2026, 11, 17), 'MD-4'),   # recovery window over → count down to next match (21st)
    (date(2026, 11, 20), 'MD-1'),
    (date(2026, 10, 1), ''),        # nothing within a week
])
def test_md_codes(day, expected):
    assert md_code_for(day, [date(2026, 11, 14), date(2026, 11, 21)]) == expected


def test_sync_command(api, club, monkeypatch):
    from io import StringIO

    from django.core.management import call_command
    monkeypatch.setenv('OPENFIELD_API_TOKEN', TOKEN)
    out = StringIO()
    call_command('sync_openfield', '--club', club.slug, '--team', 'First Team',
                 '--from', '2026-11-01', '--to', '2026-11-30', stdout=out)
    assert '3 activities' in out.getvalue() and '5 player loads' in out.getvalue()
    assert Team.objects.get(club=club, name='First Team').is_own


def test_sync_command_unknown_club(club):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    with pytest.raises(CommandError, match='not found'):
        call_command('sync_openfield', '--club', 'nope')



# --- thresholds & data quality -----------------------------------------------------

def test_personal_bests_read_from_athletes(connector):
    assert connector.athlete_max_speeds(ATHLETES) == {'ath-1': 31.5, 'ath-2': 27.0}


def test_speed_outliers_flagged(api, connector, club, own_team):
    summary = ingest_physical(club, connector, own_team, *RANGE)
    by_key = {(l.training_session.name, l.player.full_name): l
              for l in PlayerLoad.objects.select_related('training_session', 'player')}
    tomasov = by_key[('26_27_J01_Rebordosa', 'Marin Tomasov')]
    beysebekov = by_key[('26_27_J01_Rebordosa', 'Abzal Beysebekov')]
    assert tomasov.quality_flags == []                      # 31.5 = his personal best, fine
    assert beysebekov.quality_flags == ['max_speed_outlier']  # 31.5 > 27.0 * 1.1
    assert float(beysebekov.max_speed_kmh) == 31.5          # value kept, only flagged
    assert beysebekov.max_speed_for_reports is None
    assert summary.flagged == 2   # Beysebekov in both sessions (all rows run 31.5 km/h)


def test_hard_cap_without_personal_best(club, own_team, connector):
    athletes = [{**ATHLETES[0], 'velocity_max': None}]
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.get(f'{BASE}/athletes', json=athletes)
        rsps.get(f'{BASE}/activities', json=[ACTIVITIES[1]])
        rsps.get(f'{BASE}/parameters', json=PARAMETERS)
        rsps.post(f'{BASE}/stats', json=[stat_row('act-md1', 'ath-1', max_vel=14.7)])   # 52.9 km/h
        ingest_physical(club, connector, own_team, *RANGE)
    assert PlayerLoad.objects.get().quality_flags == ['max_speed_outlier']


def test_thresholds_recorded_on_each_load(api, club, own_team):
    from providers.models import ProviderAccount
    acc = ProviderAccount.objects.create(club=club, provider='catapult_openfield', api_key=TOKEN,
                                         config={'hsr_threshold_kmh': 21, 'sprint_threshold_kmh': 24})
    ingest_physical(club, OpenFieldConnector(acc), own_team, *RANGE)
    assert set(PlayerLoad.objects.values_list('hsr_threshold_kmh', 'sprint_threshold_kmh')) == \
        {(Decimal('21.0'), Decimal('24.0'))}


def test_command_saves_thresholds(api, club, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from providers.models import ProviderAccount
    monkeypatch.setenv('OPENFIELD_API_TOKEN', TOKEN)
    out = StringIO()
    call_command('sync_openfield', '--club', club.slug, '--from', '2026-11-01', '--to', '2026-11-30',
                 '--hsr-threshold', '21', '--sprint-threshold', '24', stdout=out)
    acc = ProviderAccount.objects.get(club=club)
    assert acc.config['hsr_threshold_kmh'] == 21 and acc.config['sprint_threshold_kmh'] == 24
    assert 'HSR > 21.0 km/h' in out.getvalue() and 'outliers flagged' in out.getvalue()


def test_api_can_exclude_flagged_loads(api, connector, club, own_team, make_member):
    ingest_physical(club, connector, own_team, *RANGE)
    _, c = make_member(club, 'sports_scientist')
    all_rows = c.get(f'/api/clubs/{club.pk}/loads/').data['results']
    clean = c.get(f'/api/clubs/{club.pk}/loads/?exclude_flagged=true').data['results']
    assert len(all_rows) == 5 and len(clean) == 3
    assert all(r['quality_flags'] == [] for r in clean)
