from decimal import Decimal

import pytest
from django.utils import timezone

from clubs.models import Player, Team
from football.models import PlayerLoad, TrainingSession
from metrics.models import MetricDefinition, MetricSet
from metrics.services import sync_catalogue

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogue(club):
    sync_catalogue(club, 'catapult_openfield', [
        {'slug': 'total_multidirectional_load', 'name': 'Multidirectional Load', 'unit_type': ''},
        {'slug': 'rhie_total_bouts', 'name': 'RHIE Total Bouts', 'unit_type': 'count'},
        {'slug': 'metabolic_power_average', 'name': 'Average Metabolic Power', 'unit_type': ''}])


def u(club, path):
    return f'/api/clubs/{club.pk}/{path}'


def test_catalogue_search(make_member, club, catalogue):
    _, c = make_member(club, 'head_coach')
    rows = c.get(u(club, 'metrics/catalogue/?search=multidirectional')).data['results']
    assert [r['slug'] for r in rows] == ['total_multidirectional_load'] and rows[0]['tracked_as'] is None


def test_scout_cannot_browse_catalogue(make_member, club, catalogue):
    _, c = make_member(club, 'scout')
    assert c.get(u(club, 'metrics/catalogue/')).status_code == 403


def test_enable_metric_requires_manage_metrics(make_member, club, catalogue):
    _, coach = make_member(club, 'head_coach')
    body = {'provider_slug': 'rhie_total_bouts', 'short_label': 'RHIE'}
    assert coach.post(u(club, 'metrics/definitions/'), body).status_code == 403
    _, sc = make_member(club, 'sports_scientist')
    r = sc.post(u(club, 'metrics/definitions/'), body)
    assert r.status_code == 201 and r.data['category'] == 'rhie' and r.data['short_label'] == 'RHIE'
    rows = sc.get(u(club, 'metrics/catalogue/?search=rhie')).data['results']
    assert rows[0]['tracked_as'] == 'rhie-total-bouts'


def test_unknown_slug_rejected(make_member, club, catalogue):
    _, sc = make_member(club, 'sports_scientist')
    assert sc.post(u(club, 'metrics/definitions/'), {'provider_slug': 'nope'}).status_code == 400


def test_definitions_list_includes_core(make_member, club):
    _, c = make_member(club, 'head_coach')
    keys = {d['key'] for d in c.get(u(club, 'metrics/definitions/')).data}
    assert {'total_distance', 'hsr_distance', 'max_speed', 'player_load'} <= keys


def test_coach_creates_personal_set_but_not_club_set(make_member, club):
    user, c = make_member(club, 'head_coach')
    c.get(u(club, 'metrics/definitions/'))     # seeds core metrics
    body = {'name': 'My view', 'metric_keys': ['total_distance', 'hsr_distance'], 'display': 'per_90'}
    r = c.post(u(club, 'metric-sets/'), body, format='json')
    assert r.status_code == 201 and r.data['is_club'] is False
    r = c.post(u(club, 'metric-sets/'), {**body, 'scope': 'club'}, format='json')
    assert r.status_code == 403


def test_default_resolution_personal_over_club(make_member, club):
    _, sc = make_member(club, 'sports_scientist')
    sc.get(u(club, 'metrics/definitions/'))
    sc.post(u(club, 'metric-sets/'), {'name': 'S&C Daily', 'metric_keys': ['total_distance', 'hsr_distance'],
                                      'scope': 'club', 'is_default': True}, format='json')
    user, coach = make_member(club, 'head_coach')
    assert coach.get(u(club, 'metric-sets/default/')).data['name'] == 'S&C Daily'
    r = coach.post(u(club, 'metric-sets/'), {'name': 'Mine', 'metric_keys': ['player_load'], 'is_default': True},
                   format='json')
    assert coach.get(u(club, 'metric-sets/default/')).data['name'] == 'Mine'
    # the sports scientist still sees the club default, not the coach's personal one
    assert sc.get(u(club, 'metric-sets/default/')).data['name'] == 'S&C Daily'


def test_coach_cannot_edit_club_set(make_member, club):
    _, sc = make_member(club, 'sports_scientist')
    sc.get(u(club, 'metrics/definitions/'))
    r = sc.post(u(club, 'metric-sets/'), {'name': 'Club', 'metric_keys': ['total_distance'], 'scope': 'club'},
                format='json')
    _, coach = make_member(club, 'head_coach')
    assert coach.patch(u(club, f"metric-sets/{r.data['id']}/"), {'name': 'Hacked'}, format='json').status_code == 403


def test_loads_rendered_through_a_metric_set(make_member, club):
    team = Team.objects.create(club=club, name='First Team', is_own=True)
    s = TrainingSession.objects.create(club=club, team=team, start=timezone.now(), session_type='match')
    p = Player.objects.create(club=club, full_name='P One')
    _, sc = make_member(club, 'sports_scientist')
    sc.get(u(club, 'metrics/definitions/'))
    MetricDefinition.objects.create(club=club, key='mdl', label='Multidirectional Load', short_label='MDL',
                                    provider='catapult_openfield', provider_slug='total_multidirectional_load',
                                    aggregation='sum', category='multidirectional')
    PlayerLoad.objects.create(club=club, player=p, training_session=s, provider='catapult_openfield',
                              total_distance_m=10000, duration_min=Decimal('100'), max_speed_kmh=Decimal('31.0'),
                              metrics={'mdl': 250.0})
    r = sc.post(u(club, 'metric-sets/'), {'name': 'Mechanical', 'metric_keys': ['total_distance', 'mdl', 'max_speed'],
                                          'display': 'per_90'}, format='json')
    data = sc.get(u(club, f"loads/?metric_set={r.data['id']}")).data
    vals = {v['key']: v['value'] for v in data['results'][0]['values']}
    assert vals == {'total_distance': 9000, 'mdl': 225.0, 'max_speed': 31.0}
    assert data['metric_set']['display'] == 'per_90'
    abs_vals = sc.get(u(club, f"loads/?metric_set={r.data['id']}&display=absolute")).data['results'][0]['values']
    assert [v['value'] for v in abs_vals] == [10000, 250.0, 31.0]
