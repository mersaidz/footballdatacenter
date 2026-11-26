"""Wellness: the player's link, check-ins scored against his own normal, RPE → sRPE, who sees what."""
from datetime import date, datetime, timedelta, timezone as tz

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from clubs.models import Player, Team
from football.models import PlayerLoad, TrainingSession
from football.services.performance import apply_wellness
from wellness import services as svc
from wellness.models import PlayerLink, RpeEntry, WellnessCheckin

pytestmark = pytest.mark.django_db
GOOD = {'sleep_quality': 4, 'energy': 4, 'soreness': 4, 'stress': 4, 'mood': 4}


@pytest.fixture
def squad(club):
    team = Team.objects.create(club=club, name='First Team', is_own=True)
    a = Player.objects.create(club=club, full_name='Arman Sadykov', current_team=team, shirt_number=7)
    b = Player.objects.create(club=club, full_name='Bauyrzhan Ali', current_team=team, shirt_number=10)
    return team, a, b


def history(player, days=10, **vals):
    today = timezone.localdate()
    for k in range(1, days + 1):
        WellnessCheckin.objects.create(club=player.club, player=player, date=today - timedelta(k), **{**GOOD, **vals})


def test_link_is_hashed_and_a_new_one_revokes_the_old(squad):
    _, a, _ = squad
    link, raw = PlayerLink.issue(a)
    assert raw not in link.token_hash and PlayerLink.resolve(raw) == link
    _, raw2 = PlayerLink.issue(a)
    assert PlayerLink.resolve(raw) is None and PlayerLink.resolve(raw2).player == a
    assert APIClient().get(f'/api/p/{raw}/').status_code == 404


def test_player_answers_from_the_phone_and_can_edit(squad):
    _, a, _ = squad
    _, raw = PlayerLink.issue(a)
    c = APIClient()
    home = c.get(f'/api/p/{raw}/').data
    assert home['player']['first_name'] == 'Arman' and home['checkin'] is None
    r = c.post(f'/api/p/{raw}/checkin/', {**GOOD, 'soreness': 2, 'sore_areas': ['hamstring', 'hamstring'], 'sleep_hours': '7.5',
                                         'comment': 'tight left hamstring'}, format='json')
    assert r.status_code == 201
    saved = WellnessCheckin.objects.get(player=a)
    assert saved.sore_areas == ['hamstring'] and saved.comment == 'tight left hamstring' and saved.source == 'player'
    c.post(f'/api/p/{raw}/checkin/', {**GOOD, 'soreness': 5, 'sore_areas': ['calf']}, format='json')
    saved.refresh_from_db()
    assert saved.soreness == 5 and saved.sore_areas == []            # no soreness → no areas
    assert WellnessCheckin.objects.count() == 1
    old = (timezone.localdate() - timedelta(5)).isoformat()
    assert c.post(f'/api/p/{raw}/checkin/', {**GOOD, 'date': old}, format='json').status_code == 400
    assert c.post(f'/api/p/{raw}/checkin/', {**GOOD, 'mood': 6}, format='json').status_code == 400


def test_comment_is_encrypted_at_rest(squad):
    _, a, _ = squad
    WellnessCheckin.objects.create(club=a.club, player=a, date=date(2026, 1, 1), comment='bad night, baby', **GOOD)
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute('SELECT comment FROM wellness_wellnesscheckin')
        assert 'baby' not in cur.fetchone()[0]


def test_low_is_judged_against_his_own_normal(squad):
    _, a, b = squad
    history(a)                                                      # usually 4s → total 20
    today = timezone.localdate()
    dip = WellnessCheckin.objects.create(club=a.club, player=a, date=today, **{**GOOD, 'energy': 3, 'mood': 3, 'sleep_quality': 3})
    res = svc.assess(dip, svc.baseline(a, today))
    assert res['level'] == 'low' and res['normal'] == 20 and res['z'] == -1.5   # 3 points under his steady 20
    worse = WellnessCheckin(player=a, date=today, **{**GOOD, 'energy': 2, 'mood': 3, 'sleep_quality': 3, 'stress': 3})
    assert svc.assess(worse, svc.baseline(a, today))['level'] == 'very_low'   # 5 points under: z −2.5
    history(b, sleep_quality=3)                                     # a 3-sleeper is normal for him
    same = WellnessCheckin.objects.create(club=b.club, player=b, date=today, **{**GOOD, 'sleep_quality': 3})
    assert svc.assess(same, svc.baseline(b, today))['level'] == 'ok'
    first_day = WellnessCheckin(player=b, date=today, **{**GOOD, 'soreness': 2})
    assert svc.assess(first_day, None) == {**svc.assess(first_day, None), 'level': 'low', 'flags': ['soreness']}
    one = WellnessCheckin(player=b, date=today, **{**GOOD, 'stress': 1})
    assert svc.assess(one, None)['level'] == 'very_low'


@pytest.mark.parametrize('load_level,feel,expected', [
    ('plan', 'low', 'hold'), ('build', 'low', 'hold'), ('reduce', 'low', 'reduce'),
    ('plan', 'very_low', 'reduce'), ('hold', 'ok', 'hold'),
])
def test_wellness_only_makes_the_day_more_careful(load_level, feel, expected):
    reasons = []
    assert apply_wellness(load_level, reasons, {'level': feel, 'total': 14, 'normal': 20, 'flags': []}) == expected
    assert (reasons[0]['code'] == f'wellness_{feel}') if feel != 'ok' else reasons == []


@pytest.fixture
def trained(club, squad):
    team, a, b = squad
    day = timezone.localdate()
    s = TrainingSession.objects.create(club=club, team=team, session_type='training', md_code='MD-3', name='Tue',
                                       start=datetime(day.year, day.month, day.day, 9, tzinfo=tz.utc))
    for p in (a, b):
        PlayerLoad.objects.create(club=club, player=p, training_session=s, provider='catapult_openfield', duration_min=80,
                                  total_distance_m=6000, participation='full')
    return s


def test_rpe_becomes_srpe_and_shows_in_the_session(make_member, club, squad, trained):
    _, a, b = squad
    _, raw = PlayerLink.issue(a)
    c = APIClient()
    home = c.get(f'/api/p/{raw}/').data
    assert [s['id'] for s in home['sessions']] == [trained.pk]
    assert c.post(f'/api/p/{raw}/rpe/', {'session_id': trained.pk, 'rpe': 7}, format='json').status_code == 201
    assert c.post(f'/api/p/{raw}/rpe/', {'rpe': 11}, format='json').status_code == 400
    _, coach = make_member(club, 'head_coach')
    d = coach.get(f'/api/clubs/{club.pk}/sessions/{trained.pk}/').data
    by = {r['player_id']: r for r in d['rows']}
    assert by[a.pk]['rpe'] == 7 and by[a.pk]['srpe'] == 560 and by[b.pk]['rpe'] is None
    assert d['rpe'] == {'answered': 1, 'squad': 2, 'mean': 7.0}


def test_rpe_sent_before_the_sync_is_linked_later(club, squad):
    team, a, _ = squad
    e = RpeEntry.objects.create(club=club, player=a, date=timezone.localdate(), rpe=6)
    assert e.session is None
    day = timezone.localdate()
    s = TrainingSession.objects.create(club=club, team=team, session_type='training', name='Late sync',
                                       start=datetime(day.year, day.month, day.day, 17, tzinfo=tz.utc))
    PlayerLoad.objects.create(club=club, player=a, training_session=s, provider='catapult_openfield', duration_min=60)
    assert svc.rpe_for_session(s)[a.pk] == {'rpe': 6, 'srpe': 360, 'source': 'player'}
    svc.link_rpe(e)
    e.refresh_from_db()
    assert e.session == s


def test_coach_sees_how_he_feels_not_what_he_said(make_member, club, squad):
    _, a, b = squad
    history(a)
    WellnessCheckin.objects.create(club=club, player=a, date=timezone.localdate(), comment='family stuff',
                                   **{**GOOD, 'stress': 1})
    _, coach = make_member(club, 'head_coach')
    _, sc = make_member(club, 'sports_scientist')
    url = f'/api/clubs/{club.pk}/wellness/'
    cd = coach.get(url).data
    assert cd['details'] is False and cd['answered'] == 1 and cd['squad'] == 2 and cd['very_low'] == 1
    row = cd['rows'][0]
    assert row['player_id'] == a.pk and set(row['answer']) == {'date', 'total', 'z', 'level', 'normal'}
    sd = sc.get(url).data
    assert sd['rows'][0]['answer']['comment'] == 'family stuff' and sd['rows'][0]['answer']['stress'] == 1
    ph = coach.get(f'/api/clubs/{club.pk}/players/{a.pk}/wellness/').data
    assert 'comment' not in ph['latest'] and len(ph['history']) == 11
    assert 'stress' in sc.get(f'/api/clubs/{club.pk}/players/{a.pk}/wellness/').data['latest']


def test_staff_entry_and_links_need_wellness_rights(make_member, club, squad):
    _, a, _ = squad
    _, coach = make_member(club, 'head_coach')
    physio_user, physio = make_member(club, 'physio')
    body = {'player_id': a.pk, **GOOD, 'comment': 'talked at breakfast'}
    assert coach.post(f'/api/clubs/{club.pk}/wellness/', body, format='json').status_code == 403
    assert physio.post(f'/api/clubs/{club.pk}/wellness/', body, format='json').status_code == 201
    c = WellnessCheckin.objects.get(player=a)
    assert c.source == 'staff' and c.entered_by == physio_user
    assert physio.post(f'/api/clubs/{club.pk}/rpe/', {'player_id': a.pk, 'rpe': 4}, format='json').status_code == 201
    assert coach.get(f'/api/clubs/{club.pk}/player-links/').status_code == 403
    r = physio.post(f'/api/clubs/{club.pk}/player-links/', {'player_id': a.pk}, format='json')
    assert r.status_code == 201 and r.data['path'] == f"/p/{r.data['token']}"
    links = physio.get(f'/api/clubs/{club.pk}/player-links/').data
    assert {x['player_id']: x['active'] for x in links}[a.pk] is True
    assert 'token' not in links[0]                                   # shown once, never again
    physio.post(f'/api/clubs/{club.pk}/player-links/{a.pk}/revoke/')
    assert APIClient().get(f"/api/p/{r.data['token']}/").status_code == 404


def test_other_club_cannot_touch_our_players(make_member, club, other_club, squad):
    _, a, _ = squad
    _, theirs = make_member(other_club, 'physio')
    assert theirs.post(f'/api/clubs/{other_club.pk}/wellness/', {'player_id': a.pk, **GOOD}, format='json').status_code == 404
    assert theirs.get(f'/api/clubs/{other_club.pk}/players/{a.pk}/wellness/').status_code == 404


def test_squad_status_carries_wellness(make_member, club, squad):
    team, a, b = squad
    day0 = timezone.localdate() - timedelta(30)
    for k in range(30):
        s = TrainingSession.objects.create(club=club, team=team, session_type='training', name=f'S{k}',
                                           start=datetime.combine(day0 + timedelta(k), datetime.min.time(), tz.utc).replace(hour=9))
        for p in (a, b):
            PlayerLoad.objects.create(club=club, player=p, training_session=s, provider='catapult_openfield', duration_min=75,
                                      total_distance_m=5000, hsr_distance_m=250, participation='full')
    history(a)
    WellnessCheckin.objects.create(club=club, player=a, date=timezone.localdate(), **{**GOOD, 'soreness': 1})
    _, coach = make_member(club, 'head_coach')
    d = coach.get(f'/api/clubs/{club.pk}/squad-status/').data
    assert d['as_of'] == timezone.localdate().isoformat() and d['wellness'] == {'answered': 1, 'squad': 2}
    by = {p['player_id']: p for p in d['players']}
    assert by[a.pk]['level'] == 'reduce' and by[a.pk]['reasons'][0]['code'] == 'wellness_very_low'
    assert 'flags' not in by[a.pk]['reasons'][0] and by[b.pk]['wellness'] is None and by[b.pk]['level'] == 'plan'


def test_default_day_is_today_unless_answers_are_old(squad):
    _, a, _ = squad
    today = timezone.localdate()
    assert svc.default_day(a.club, today) == today
    WellnessCheckin.objects.create(club=a.club, player=a, date=today - timedelta(40), **GOOD)
    assert svc.default_day(a.club, today) == today - timedelta(40)
    WellnessCheckin.objects.create(club=a.club, player=a, date=today - timedelta(1), **GOOD)
    assert svc.default_day(a.club, today) == today
