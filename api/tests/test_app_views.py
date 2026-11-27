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
    assert by['Spiky Sam']['level'] == 'reduce' and by['Spiky Sam']['reasons'][0]['code'] == 'acwr_dist_high'
    assert by['Steady Eddie']['level'] == 'plan' and by['Steady Eddie']['reasons'] == []
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


@pytest.mark.parametrize('ad,ah,idle,expect', [
    (1.6, 1.0, 0, 'reduce'), (1.0, 1.6, 0, 'reduce'), (1.4, 1.0, 0, 'hold'), (1.0, 1.35, 0, 'hold'),
    (0.7, 1.0, 0, 'build'), (1.0, 0.5, 0, 'build'), (1.0, 1.0, 4, 'build'), (1.0, 1.0, 0, 'plan'),
    (1.6, 0.5, 0, 'reduce'), (1.4, 0.5, 0, 'hold'), (1.0, None, 0, 'plan'),
])
def test_load_action(ad, ah, idle, expect):
    from datetime import date
    from football.services.performance import load_action
    level, reasons = load_action(ad, ah, idle, date(2026, 8, 1), False, date(2026, 7, 1))
    assert level == expect and (reasons == []) == (expect == 'plan')


def test_availability_shapes_the_day(make_member, club, season):
    """Out → not part of today's load calls; modified training → at most 'hold'; just back → said so."""
    from datetime import date
    from football.models import PlayerAvailability
    _, _, (gk, steady, spike) = season
    _, physio = make_member(club, 'physio')
    _, coach = make_member(club, 'head_coach')
    r = physio.post(u(club, 'availability/'), {'player': spike.pk, 'status': 'unavailable', 'reason': 'injury',
                                               'start_date': '2026-08-03', 'expected_return': '2026-08-20',
                                               'diagnosis': 'hamstring strain grade 1'}, format='json')
    assert r.status_code == 201
    assert coach.post(u(club, 'availability/'), {'player': gk.pk, 'status': 'modified', 'start_date': '2026-08-01'},
                      format='json').status_code == 403
    physio.post(u(club, 'availability/'), {'player': steady.pk, 'status': 'modified', 'reason': 'load_management',
                                          'start_date': '2026-08-04'}, format='json')
    d = coach.get(u(club, 'squad-status/')).data
    by = {p['name']: p for p in d['players']}
    assert by['Spiky Sam']['level'] == 'out' and by['Spiky Sam']['reasons'] == [
        {'code': 'unavailable', 'reason': 'injury', 'date': '2026-08-20'}]
    assert 'diagnosis' not in str(by['Spiky Sam'])                       # coaches never see the diagnosis
    assert by['Steady Eddie']['level'] == 'hold' and by['Steady Eddie']['reasons'][0]['code'] == 'modified'
    assert d['players'][-1]['name'] == 'Spiky Sam'                         # out players go to the bottom
    # A new episode closes the open one; once back, "returning" for a week.
    physio.post(u(club, 'availability/'), {'player': spike.pk, 'status': 'modified', 'reason': 'injury',
                                          'start_date': '2026-08-04'}, format='json')
    assert PlayerAvailability.objects.filter(player=spike, actual_return__isnull=True).count() == 1
    ep = PlayerAvailability.objects.get(player=spike, actual_return__isnull=True)
    ep.actual_return = date(2026, 8, 5); ep.save()
    d = coach.get(u(club, 'squad-status/')).data
    spike_row = next(p for p in d['players'] if p['name'] == 'Spiky Sam')
    assert spike_row['level'] != 'out' and spike_row['reasons'][0]['code'] == 'returning'


def test_keepers_are_judged_on_playerload_and_dives(make_member, club, season):
    """A keeper barely runs: his load is PlayerLoad, his 'HSR' is dives (when the club tracks them)."""
    _, _, (gk, _, _) = season
    loads = PlayerLoad.objects.filter(player=gk).select_related('training_session').order_by('training_session__start')
    for i, pl in enumerate(loads):
        pl.extra_metrics = {'total_dive_load': 300 if i >= 28 else 100}   # last week: three times the dive load
        pl.save(update_fields=['extra_metrics'])
    _, coach = make_member(club, 'head_coach')
    row = next(p for p in coach.get(u(club, 'squad-status/')).data['players'] if p['name'] == 'Gil Keeper')
    assert row['is_gk'] and row['acwr_basis'] == 'player_load' and row['acwr_hsr'] is None
    assert 0.8 < row['acwr_distance'] < 1.3                        # PlayerLoad steady
    assert row['acwr_dives'] > 1.5 and row['level'] == 'reduce' and row['reasons'][0]['code'] == 'gk_dives_high'


def test_daily_report_pdf_and_excel(make_member, club, season):
    from io import BytesIO
    from openpyxl import load_workbook
    _, coach = make_member(club, 'head_coach')
    r = coach.get(u(club, 'reports/daily.pdf?lang=kk'))
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf' and r.content[:4] == b'%PDF'
    assert 'attachment; filename="status-2026-08-05.pdf"' == r['Content-Disposition']
    x = coach.get(u(club, 'reports/daily.xlsx?lang=ru'))
    ws = load_workbook(BytesIO(x.content)).active
    names = [ws.cell(row=i, column=3).value for i in range(6, 9)]
    assert set(names) == {'Spiky Sam', 'Steady Eddie', 'Gil Keeper'} and ws.cell(row=6, column=1).value == 'Снизить нагрузку'
    assert coach.get(u(club, 'reports/daily.doc')).status_code == 404
    _, scout = make_member(club, 'scout')
    assert scout.get(u(club, 'reports/daily.pdf')).status_code == 403


def test_accel_decel_spike_counts_even_when_distance_is_steady(make_member, club, season):
    _, _, (_, steady, _) = season
    for pl in PlayerLoad.objects.filter(player=steady).select_related('training_session'):
        if pl.training_session.start >= DAY0 + timedelta(days=28):
            pl.accelerations, pl.decelerations = 60, 60                   # last week: three times the braking work
            pl.save(update_fields=['accelerations', 'decelerations'])
    _, coach = make_member(club, 'head_coach')
    row = next(p for p in coach.get(u(club, 'squad-status/')).data['players'] if p['name'] == 'Steady Eddie')
    assert 0.8 < row['acwr_distance'] < 1.3 and row['acwr_accdec'] > 1.5
    assert row['level'] == 'reduce' and row['reasons'][0]['code'] == 'acwr_accdec_high'
