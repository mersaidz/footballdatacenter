import pytest

from metrics.models import MetricDefinition, MetricRequest
from metrics.services import search_catalogue, sync_catalogue

pytestmark = pytest.mark.django_db

BAND4 = [
    {'slug': 'velocity_band4_distance_band7_total_effort_count', 'name': 'Velocity Band 4 Distance Band 7 Total # Efforts'},
    {'slug': 'velocity2_band4_total_distance', 'name': 'Velocity Band 4 Total Distance (Set 2)', 'unit_type': 'distance'},
    {'slug': 'velocity_band4_total_distance', 'name': 'Velocity Band 4 Total Distance', 'unit_type': 'distance'},
    {'slug': 'acceleration_band4_total_distance', 'name': 'Acceleration Band 4 Total Distance'},
]


@pytest.fixture
def catalogue(club):
    sync_catalogue(club, 'catapult_openfield', BAND4 + [{'slug': 'tackle_band24_count', 'name': 'Tackle Band 24 Count'}])


def u(club, path):
    return f'/api/clubs/{club.pk}/{path}'


@pytest.mark.parametrize('query', ['velocity band 4 total distance', 'Velocity Band4 Total Distance', 'velocity_band4'])
def test_search_ranks_the_exact_name_first(club, catalogue, query):
    slugs = [pm.slug for pm in search_catalogue(club, query)]
    assert slugs[0] == 'velocity_band4_total_distance' and 'acceleration_band4_total_distance' not in slugs


def test_numbers_match_whole(club, catalogue):
    assert 'tackle_band24_count' not in [pm.slug for pm in search_catalogue(club, 'band 4')]
    assert [pm.slug for pm in search_catalogue(club, 'band 24')] == ['tackle_band24_count']


def test_coach_asks_sc_approves_and_tracking_starts(make_member, club, catalogue):
    coach_user, coach = make_member(club, 'head_coach')
    body = {'provider_slug': 'velocity_band4_total_distance', 'note': 'For my running view'}
    r = coach.post(u(club, 'metrics/requests/'), body)
    assert r.status_code == 201 and r.data['status'] == 'pending'
    assert coach.post(u(club, 'metrics/requests/'), body).status_code == 200     # no duplicate request
    found = coach.get(u(club, 'metrics/catalogue/?search=band 4 total distance')).data['results'][0]
    assert found['slug'] == 'velocity_band4_total_distance' and found['requested'] is True

    assert coach.post(u(club, f"metrics/requests/{r.data['id']}/approve/")).status_code == 403
    _, sc = make_member(club, 'sports_scientist')
    assert len(sc.get(u(club, 'metrics/requests/?status=pending')).data) == 1
    ok = sc.post(u(club, f"metrics/requests/{r.data['id']}/approve/"))
    assert ok.status_code == 200 and ok.data['status'] == 'approved' and ok.data['metric_key']
    md = MetricDefinition.objects.get(club=club, provider_slug='velocity_band4_total_distance')
    assert (md.unit, md.aggregation, md.enabled) == ('m', 'sum', True)
    assert sc.post(u(club, f"metrics/requests/{r.data['id']}/approve/")).status_code == 400
    again = coach.post(u(club, 'metrics/requests/'), body)
    assert again.status_code == 400 and 'Уже отслеживается' in str(again.data)   # Russian by default


def test_requests_are_private_to_their_author_and_declinable(make_member, club, catalogue):
    _, a = make_member(club, 'head_coach')
    _, b = make_member(club, 'assistant_coach')
    rid = a.post(u(club, 'metrics/requests/'), {'provider_slug': 'acceleration_band4_total_distance'}).data['id']
    assert b.get(u(club, 'metrics/requests/')).data == []
    _, sc = make_member(club, 'analyst')
    assert sc.post(u(club, f'metrics/requests/{rid}/decline/')).data['status'] == 'declined'
    assert not MetricDefinition.objects.filter(club=club, provider_slug='acceleration_band4_total_distance').exists()
    assert MetricRequest.objects.get(pk=rid).decided_at is not None


def test_scout_cannot_request(make_member, club, catalogue):
    _, scout = make_member(club, 'scout')
    assert scout.post(u(club, 'metrics/requests/'), {'provider_slug': 'velocity_band4_total_distance'}).status_code == 403
