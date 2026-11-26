"""Web-app read views: squad status, session history and detail, microcycle, player load history."""
from datetime import datetime, timedelta, timezone

import pytest

from clubs.models import Player, Team
from football.models import ActivityPeriod, PeriodLoad, PlayerLoad, TrainingSession

pytestmark = pytest.mark.django_db
DAY0 = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)


@pytest.fixture
def season(club):
    team = Team.objects.create(club=club, name='First Team', is_own=True)
    gk = Player.objects.create(club=club, full_name='Gil Keeper', current_team=team, primary_position='GK', shirt_number=1)
    steady = Player.objects.create(club=club, full_name='Steady Eddie', current_team=team, shirt_number=8)
    spike = Player.objects.create(club=club, full_name='Spiky Sam', current_team=team, shirt_number=9)
    sessions = []
    for day in range(35):
        is_match = day % 7 == 6
        s = TrainingSession.objects.create(
            club=club, team=team, start=DAY0 + timedelta(days=day), end=DAY0 + timedelta(days=day, hours=1, minutes=30),
            session_type='match' if is_match else 'training', md_code='MD' if is_match else f'MD-{6 - day % 7}',
            name=f'S{day}')
        sessions.append(s)
        for p in (gk, steady, spike):
            mins = 95 if is_match else 75
            dist = 9500 if is_match else 5000
            if p is spike and day >= 28:
                dist *= 2.4                                   # last week: big jump
            if p is gk:
                dist = 4000
            PlayerLoad.objects.create(club=club, player=p, training_session=s, provider='catapult_openfield',
                                      duration_min=mins, total_distance_m=dist, hsr_distance_m=0 if p is gk else dist * 0.05,
                                      sprint_distance_m=dist * 0.01, accelerations=20, decelerations=20, player_load=500,
                                      participation='full')
    period = ActivityPeriod.objects.create(club=club, training_session=sessions[-1], provider='catapult_openfield',
                                           external_id='p1', name='1half', role='first_half',
                                           start=sessions[-1].start, end=sessions[-1].start + timedelta(minutes=47))
    PeriodLoad.objects.create(club=club, player=steady, period=period, provider='catapult_openfield',
                              duration_min=47, total_distance_m=4800)
    return team, sessions, (gk, steady, spike)


def u(club, path):
    return f'/api/clubs/{club.pk}/{path}'


def test_squad_status_flags_the_spike_and_skips_hsr_for_keepers(make_member, club, season):
    _, coach = make_member(club, 'head_coach')
    d = coach.get(u(club, 'squad-status/')).data
    assert d['as_of'] == '2026-08-05' and d['last_match']['name'] == 'S34' and d['days_since_match'] == 1
    by = {p['name']: p for p in d['players']}
    assert by['Spiky Sam']['level'] == 'modify' and by['Spiky Sam']['reasons'][0]['code'] == 'acwr_dist_high'
    assert by['Steady Eddie']['level'] == 'ready' and by['Steady Eddie']['reasons'] == []
    assert by['Gil Keeper']['acwr_hsr'] is None and by['Gil Keeper']['last_match_minutes'] == 95
    assert d['players'][0]['name'] == 'Spiky Sam'                               # worst first
    old = coach.get(u(club, 'squad-status/?date=2026-07-10')).data
    assert old['as_of'] == '2026-07-10'
    assert coach.get(u(club, 'squad-status/?date=10-07-2026')).status_code == 400


def test_session_history_and_detail(make_member, club, season):
    _, sessions, (gk, steady, spike) = season
    _, coach = make_member(club, 'head_coach')
    hist = coach.get(u(club, 'sessions/?type=match')).data
    assert [s['name'] for s in hist] == ['S34', 'S27', 'S20', 'S13', 'S6'] and hist[0]['distance'] > 9500
    assert len(coach.get(u(club, 'sessions/?from=2026-07-01&to=2026-07-07&type=training')).data) == 6
    d = coach.get(u(club, f'sessions/{sessions[-1].pk}/')).data
    assert d['session']['type'] == 'match' and d['session']['previous_id'] == sessions[-2].pk and d['session']['next_id'] is None
    assert d['periods'][0]['role'] == 'first_half' and d['periods'][0]['counts_as_play'] is True
    keys = [m['key'] for m in d['metric_set']['metrics']]
    assert 'total_distance' in keys
    row = next(r for r in d['rows'] if r['name'] == 'Steady Eddie')
    assert row['values']['total_distance'] == 9500
    assert row['periods'][d['periods'][0]['id']]['total_distance'] == 4800      # JSON: keyed by period id
    p90 = coach.get(u(club, f'sessions/{sessions[-1].pk}/?display=per_90')).data
    assert next(r for r in p90['rows'] if r['name'] == 'Steady Eddie')['values']['total_distance'] == 9000.0


def test_microcycle_and_player_history(make_member, club, season):
    _, sessions, (gk, steady, spike) = season
    _, coach = make_member(club, 'head_coach')
    m = coach.get(u(club, 'microcycle/')).data
    assert m['match']['name'] == 'S34' and len(m['days']) == 7 and m['days'][-1]['md'] == 'MD'
    assert [g['name'] for g in m['grid']] == ['Steady Eddie', 'Spiky Sam']           # keepers out of the grid
    assert len(m['matches']) == 5
    earlier = coach.get(u(club, f'microcycle/?match={sessions[13].pk}')).data
    assert earlier['match']['name'] == 'S13'
    h = coach.get(u(club, f'players/{steady.pk}/load-history/')).data
    assert h['player']['name'] == 'Steady Eddie' and len(h['days']) == 35 and len(h['match_log']) == 5
    assert h['reference']['dist'] == 9000 and h['totals']['matches'] == 5
    assert abs(h['acwr_distance'][-1] - 1.0) < 0.1


def test_scout_cannot_see_loads(make_member, club, season):
    _, scout = make_member(club, 'scout')
    assert scout.get(u(club, 'squad-status/')).status_code == 403
    assert scout.get(u(club, 'sessions/')).status_code == 403
