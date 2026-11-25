"""
OpenField connector + physical ingest. HTTP is mocked with `responses`;
payload shapes mirror what scripts/openfield_probe.py recorded on a live account.
"""
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import responses

from clubs.models import Player, Team
from core.models import AuditLog
from football.models import ActivityPeriod, Match, PeriodLoad, PeriodRoleMapping, PlayerLoad, TrainingSession
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

def tsm(y, m, d, h, mi):
    return int(datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp())


def period(pid, act, name, start, end, tags=None):
    return {'id': pid, 'activity_id': act, 'name': name, 'start_time': start, 'start_centiseconds': 0,
            'end_time': end, 'end_centiseconds': 0, 'is_deleted': 0, 'tag_list': [], 'tags': tags or []}


# J01 recorded like the real account: warm-up, then two halves with a break.
MATCH_PERIODS = [
    period('p-wu', 'act-md', 'Warm Up', tsm(2026, 11, 14, 14, 40), tsm(2026, 11, 14, 14, 57)),
    period('p-h1', 'act-md', '1st Half', tsm(2026, 11, 14, 15, 0), tsm(2026, 11, 14, 15, 47)),
    period('p-h2', 'act-md', '2nd Half', tsm(2026, 11, 14, 16, 2), tsm(2026, 11, 14, 16, 50)),
]
TRAINING_PERIODS = [
    period('t-wu', 'act-md1', 'Warm Up', tsm(2026, 11, 13, 10, 0), tsm(2026, 11, 13, 10, 10)),
    period('t-ro', 'act-md1', 'Rondo_19v3_centercircle', tsm(2026, 11, 13, 10, 10), tsm(2026, 11, 13, 10, 25)),
    period('t-rtp', 'act-md1', 'Return to Play session', tsm(2026, 11, 13, 10, 5), tsm(2026, 11, 13, 10, 35)),
]
DETAIL_PERIODS = {'act-md': MATCH_PERIODS, 'act-md1': TRAINING_PERIODS, 'act-untagged': []}
ACTIVITY_ATHLETES = {
    'act-md': [{'id': 'ath-1', 'tags': [tag('Participation', 'Full')]},
               {'id': 'ath-2', 'tags': [tag('Participation', 'Part')]}],
    'act-md1': [{'id': 'ath-1', 'tags': [tag('Participation', 'Full')]},
                {'id': 'ath-2', 'tags': [tag('Participation', 'Alternate')]}],
    'act-untagged': [{'id': 'ath-1', 'tags': []}],
}

ACTIVITIES = [
    {'id': 'act-md', 'name': '26_27_J01_Rebordosa', 'start_time': ts(2026, 11, 14, 14), 'end_time': ts(2026, 11, 14, 17),
     'tag_list': [tag('DayCode', 'MD'), tag('Device', 'GPS')], 'tags': ['MD', 'GPS'], 'athlete_count': 2,
     'periods': MATCH_PERIODS},
    {'id': 'act-md1', 'name': '26_27_UT015', 'start_time': ts(2026, 11, 13), 'end_time': ts(2026, 11, 13, 11),
     'tag_list': [tag('DayCode', 'MD-1')], 'tags': ['MD-1'], 'athlete_count': 2, 'periods': TRAINING_PERIODS},
    {'id': 'act-untagged', 'name': 'Activity 202611169223', 'start_time': ts(2026, 11, 16), 'end_time': None,
     'tag_list': [tag('Device', 'GPS')], 'tags': ['GPS'], 'athlete_count': 1},
]

PARAMETERS = [{'slug': s, 'name': s} for s in (
    'total_distance', 'total_duration', 'field_time', 'total_player_load', 'max_vel', 'high_speed_distance',
    'velocity_band5_total_distance', 'velocity_band6_total_distance', 'velocity_band7_total_distance',
    'velocity_band8_total_distance', 'gen2_acceleration_band7plus_total_effort_count',
    'gen2_acceleration_band2plus_total_effort_count', 'player_load_per_minute',
    'rhie_total_bouts', 'total_multidirectional_load',
)]


def stat_row(activity, athlete, **metrics):
    row = {'athlete_id': athlete, 'activity_id': activity, 'athlete_name': 'X', 'date': '14/11/2026',
           'start_time': 0, 'end_time': 0, 'field_time': 5400.0, 'total_duration': 5600,
           'total_distance': 10450, 'total_player_load': 980.4, 'max_vel': 8.75,
           'velocity_band5_total_distance': 520, 'velocity_band6_total_distance': 180,
           'velocity_band7_total_distance': 40, 'velocity_band8_total_distance': 0,
           'gen2_acceleration_band7plus_total_effort_count': 31,
           'gen2_acceleration_band2plus_total_effort_count': 37, 'high_speed_distance': 700,
           'player_load_per_minute': 10.9, 'rhie_total_bouts': 6, 'total_multidirectional_load': 300.0}
    row.update(metrics)
    return row


STATS = [
    stat_row('act-md', 'ath-1'), stat_row('act-md', 'ath-2', total_distance=11020),
    stat_row('act-md1', 'ath-1', total_distance=4300), stat_row('act-md1', 'ath-2', total_distance=4100),
    stat_row('act-untagged', 'ath-1', total_distance=0, max_vel=0),
]


def pstat(activity, athlete, pid, secs, dist, b5=0, b6=0, b7=0, vmax=6.0, acc=0, dec=0, pl=100.0, rhie=2, mdl=100.0):
    return stat_row(activity, athlete, period_id=pid, field_time=float(secs), total_duration=secs,
                    rhie_total_bouts=rhie, total_multidirectional_load=mdl,
                    total_distance=dist, velocity_band5_total_distance=b5, velocity_band6_total_distance=b6,
                    velocity_band7_total_distance=b7, velocity_band8_total_distance=0, max_vel=vmax,
                    gen2_acceleration_band7plus_total_effort_count=acc,
                    gen2_acceleration_band2plus_total_effort_count=dec, total_player_load=pl)


PERIOD_STATS = [
    # Tomasov: warm-up + both halves.
    pstat('act-md', 'ath-1', 'p-wu', 1020, 1500, pl=150.0),
    pstat('act-md', 'ath-1', 'p-h1', 2820, 4800, b5=200, b6=80, b7=10, vmax=8.75, acc=14, dec=18, pl=420.0),
    pstat('act-md', 'ath-1', 'p-h2', 2880, 4500, b5=200, b6=80, b7=10, vmax=8.5, acc=12, dec=16, pl=400.0),
    # Beysebekov: warm-up, came on for the second half.
    pstat('act-md', 'ath-2', 'p-wu', 1020, 1200, pl=120.0),
    pstat('act-md', 'ath-2', 'p-h2', 1500, 2600, b5=150, b6=40, vmax=8.75, acc=8, dec=9, pl=230.0),
    pstat('act-md1', 'ath-1', 't-wu', 600, 900), pstat('act-md1', 'ath-1', 't-ro', 900, 1700),
    pstat('act-md1', 'ath-2', 't-rtp', 1800, 2400),
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
            source = PERIOD_STATS if 'period' in body['group_by'] else STATS
            return 200, {}, json.dumps([r for r in source if r['activity_id'] in ids])

        def detail_cb(request):
            act, kind = re.search(r'/activities/([^/]+)/(periods|athletes)$', request.url).groups()
            data = DETAIL_PERIODS.get(act, []) if kind == 'periods' else ACTIVITY_ATHLETES.get(act, [])
            return 200, {}, json.dumps(data)

        rsps.add_callback(responses.POST, f'{BASE}/stats', callback=stats_cb, content_type='application/json')
        rsps.add_callback(responses.GET, re.compile(BASE + r'/activities/[^/]+/(periods|athletes)$'),
                          callback=detail_cb, content_type='application/json')
        yield rsps


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr('providers.connectors.openfield.time.sleep', lambda s: None)


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
        assert acts['act-md'].start == datetime(2026, 11, 14, 14, tzinfo=timezone.utc)
        assert [p.name for p in acts['act-md'].periods] == ['Warm Up', '1st Half', '2nd Half']

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
    load = PlayerLoad.objects.get(training_session__name='26_27_UT015', player__full_name='Marin Tomasov')
    assert load.total_distance_m == 4300 and load.hsr_distance_m == 740 and load.sprint_distance_m == 220
    assert float(load.max_speed_kmh) == 31.5 and float(load.duration_min) == 90.0
    assert load.extra_metrics['player_load_per_minute'] == 10.9
    assert load.load_basis == 'activity'   # training keeps the whole session, warm-up included


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



# --- periods & participation ----------------------------------------------------------

def test_match_load_counts_playing_periods_only(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    load = PlayerLoad.objects.get(training_session__name='26_27_J01_Rebordosa', player__full_name='Marin Tomasov')
    assert load.load_basis == 'match_periods'
    assert load.total_distance_m == 4800 + 4500          # warm-up's 1500 m excluded
    assert float(load.duration_min) == 95.0              # 47' + 48', not the 119' of the whole recording
    assert load.hsr_distance_m == 2 * (200 + 80 + 10) and load.sprint_distance_m == 2 * (80 + 10)
    assert float(load.max_speed_kmh) == 31.5 and load.accelerations == 26 and float(load.player_load) == 820.0
    assert load.extra_metrics['activity_total']['total_distance_m'] == 10450   # whole recording kept for audit


def test_substitute_minutes_come_from_his_periods(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    load = PlayerLoad.objects.get(training_session__name='26_27_J01_Rebordosa', player__full_name='Abzal Beysebekov')
    assert float(load.duration_min) == 25.0 and load.total_distance_m == 2600


def test_periods_stored_with_roles(api, connector, club, own_team):
    summary = ingest_physical(club, connector, own_team, *RANGE)
    roles = dict(ActivityPeriod.objects.values_list('external_id', 'role'))
    assert roles == {'p-wu': 'warm_up', 'p-h1': 'first_half', 'p-h2': 'second_half',
                     't-wu': 'warm_up', 't-ro': 'drill', 't-rtp': 'rehab'}
    assert summary.periods == 6 and summary.periods_to_review == 0
    assert PeriodLoad.objects.count() == len(PERIOD_STATS)


def test_participation_stored(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    part = {(l.training_session.name, l.player.full_name): l.participation
            for l in PlayerLoad.objects.select_related('training_session', 'player')}
    assert part[('26_27_J01_Rebordosa', 'Marin Tomasov')] == 'full'
    assert part[('26_27_J01_Rebordosa', 'Abzal Beysebekov')] == 'partial'
    assert part[('26_27_UT015', 'Abzal Beysebekov')] == 'alternate'


def test_unnamed_halves_resolved_by_structure_and_review_queue(api, connector, club, own_team):
    saved = [dict(p) for p in MATCH_PERIODS]
    try:
        MATCH_PERIODS[1]['name'], MATCH_PERIODS[2]['name'] = '1', '2'
        MATCH_PERIODS[0]['name'] = 'Pre'
        ingest_physical(club, connector, own_team, *RANGE)
    finally:
        for p, orig in zip(MATCH_PERIODS, saved):
            p.update(orig)
    roles = {p.external_id: (p.role, p.role_source) for p in ActivityPeriod.objects.filter(external_id__startswith='p-')}
    assert roles['p-h1'] == ('first_half', 'structure') and roles['p-h2'] == ('second_half', 'structure')
    assert roles['p-wu'] == ('warm_up', 'structure')


def test_manual_role_survives_resync(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    ActivityPeriod.objects.filter(external_id='t-ro').update(role='top_up', role_source='manual')
    ingest_physical(club, connector, own_team, *RANGE)
    p = ActivityPeriod.objects.get(external_id='t-ro')
    assert (p.role, p.role_source) == ('top_up', 'manual')


def test_club_mapping_applies_on_next_sync(api, connector, club, own_team):
    PeriodRoleMapping.objects.create(club=club, normalized_name='rondo 19 v 3 centercircle', role='warm_up')
    ingest_physical(club, connector, own_team, *RANGE)
    p = ActivityPeriod.objects.get(external_id='t-ro')
    assert (p.role, p.role_source) == ('warm_up', 'club')


def test_resync_keeps_period_tables_stable(api, connector, club, own_team):
    ingest_physical(club, connector, own_team, *RANGE)
    before = (ActivityPeriod.objects.count(), PeriodLoad.objects.count(), PlayerLoad.objects.count())
    ingest_physical(club, connector, own_team, *RANGE)
    assert before == (ActivityPeriod.objects.count(), PeriodLoad.objects.count(), PlayerLoad.objects.count())



# --- configurable metrics ---------------------------------------------------------------

def test_catalogue_synced_and_chosen_metrics_flow_through(api, connector, club, own_team):
    from metrics.models import ProviderMetric
    from metrics.services import enable_from_catalogue
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.catalogue == len(PARAMETERS) and summary.custom_metrics == 0
    for slug in ('rhie_total_bouts', 'total_multidirectional_load'):
        enable_from_catalogue(club, ProviderMetric.objects.get(club=club, slug=slug))
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.custom_metrics == 2
    match = PlayerLoad.objects.get(training_session__name='26_27_J01_Rebordosa', player__full_name='Marin Tomasov')
    # halves only (2 + 2 bouts, 100 + 100), the warm-up's values are not match load
    assert match.metrics == {'rhie-total-bouts': 4.0, 'total-multidirectional-load': 200.0}
    training = PlayerLoad.objects.get(training_session__name='26_27_UT015', player__full_name='Marin Tomasov')
    assert training.metrics == {'rhie-total-bouts': 6.0, 'total-multidirectional-load': 300.0}
    assert PeriodLoad.objects.filter(period__external_id='p-h1', player__full_name='Marin Tomasov') \
        .get().metrics['rhie-total-bouts'] == 2.0



def test_broken_catalogue_does_not_stop_the_sync(api, connector, club, own_team, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('catalogue exploded')
    monkeypatch.setattr('providers.services.physical_ingest.sync_catalogue', boom)
    summary = ingest_physical(club, connector, own_team, *RANGE)
    assert summary.loads == 5 and any('metric catalogue' in e for e in summary.errors)
