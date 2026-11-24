from datetime import date

import pytest

from clubs.models import Player
from core.models import AuditLog
from football.models import Match, PlayerAvailability, PlayerLoad

pytestmark = pytest.mark.django_db


@pytest.fixture
def injury(ingested, club):
    player = Player.objects.get(club=club, full_name='Marin Tomasov')
    return PlayerAvailability.objects.create(
        club=club, player=player, status='unavailable', reason='injury',
        start_date=date(2024, 5, 13), diagnosis='Hamstring strain grade 2', clinical_notes='MRI 14/05',
    )


def url(club, path):
    return f'/api/clubs/{club.pk}/{path}'


def test_my_clubs(make_member, club):
    _, c = make_member(club, 'head_coach')
    resp = c.get('/api/clubs/')
    assert resp.data == [{'club_id': club.pk, 'club_name': club.name, 'club_slug': club.slug, 'role': 'head_coach'}]


def test_non_member_gets_404_not_403(make_member, club, other_club, ingested):
    _, c = make_member(other_club, 'head_coach')
    assert c.get(url(club, 'players/')).status_code == 404
    player = Player.objects.filter(club=club).first()
    assert c.get(url(club, f'players/{player.pk}/')).status_code == 404


def test_member_sees_only_own_club_rows(make_member, club, other_club, ingested):
    foreign = Player.objects.create(club=other_club, full_name='Foreign Player')
    _, c = make_member(club, 'analyst')
    names = [p['full_name'] for p in c.get(url(club, 'players/')).data['results']]
    assert 'Foreign Player' not in names and len(names) == 4
    assert c.get(url(club, f'players/{foreign.pk}/')).status_code == 404


def test_match_events_and_lineups(make_member, club, ingested):
    _, c = make_member(club, 'scout')
    match = Match.objects.get(club=club)
    shots = c.get(url(club, f'matches/{match.pk}/events/?type=shot')).data['results']
    assert len(shots) == 1 and shots[0]['xg'] == pytest.approx(0.31) and shots[0]['player'] == 'Marin Tomasov'
    lineups = c.get(url(club, f'matches/{match.pk}/lineups/')).data
    assert len(lineups) == 4


def test_scout_cannot_see_physical_load_or_availability(make_member, club, injury):
    _, c = make_member(club, 'scout')
    assert c.get(url(club, 'loads/')).status_code == 403
    assert c.get(url(club, 'availability/')).status_code == 403


def test_sports_scientist_sees_loads(make_member, club, ingested):
    match = Match.objects.get(club=club)
    player = Player.objects.filter(club=club).first()
    PlayerLoad.objects.create(club=club, player=player, match=match, provider='catapult_openfield',
                              total_distance_m=10850, hsr_distance_m=720)
    _, c = make_member(club, 'sports_scientist')
    data = c.get(url(club, f'loads/?match={match.pk}')).data['results']
    assert data[0]['total_distance_m'] == 10850


def test_coach_sees_status_but_not_diagnosis(make_member, club, injury):
    _, c = make_member(club, 'head_coach')
    row = c.get(url(club, 'availability/')).data['results'][0]
    assert row['status'] == 'unavailable'
    assert 'diagnosis' not in row and 'clinical_notes' not in row
    assert not AuditLog.objects.filter(action=AuditLog.Action.MEDICAL_RECORD_VIEWED).exists()


def test_club_admin_has_no_medical_access(make_member, club, injury):
    _, c = make_member(club, 'club_admin')
    assert c.get(url(club, 'availability/')).status_code == 403


def test_physio_sees_diagnosis_and_read_is_audited(make_member, club, injury):
    user, c = make_member(club, 'physio')
    row = c.get(url(club, f'availability/{injury.pk}/')).data
    assert row['diagnosis'] == 'Hamstring strain grade 2'
    log = AuditLog.objects.get(action=AuditLog.Action.MEDICAL_RECORD_VIEWED)
    assert log.user == user and log.extra_info['availability_ids'] == [injury.pk]


def test_only_medical_can_write(make_member, club, ingested):
    player = Player.objects.filter(club=club).first()
    payload = {'player': player.pk, 'status': 'modified', 'reason': 'load_management', 'start_date': '2024-05-14'}
    _, coach = make_member(club, 'head_coach')
    assert coach.post(url(club, 'availability/'), payload).status_code == 403
    doc_user, doctor = make_member(club, 'doctor')
    resp = doctor.post(url(club, 'availability/'), {**payload, 'diagnosis': 'Adductor tightness'})
    assert resp.status_code == 201, resp.data
    rec = PlayerAvailability.objects.get(pk=resp.data['id'])
    assert rec.club == club and rec.created_by == doc_user and rec.diagnosis == 'Adductor tightness'
    assert AuditLog.objects.filter(action=AuditLog.Action.MEDICAL_RECORD_CHANGED).count() == 1


def test_cannot_create_record_for_other_clubs_player(make_member, club, other_club):
    foreign = Player.objects.create(club=other_club, full_name='Foreign')
    _, doctor = make_member(club, 'doctor')
    resp = doctor.post(url(club, 'availability/'),
                       {'player': foreign.pk, 'status': 'unavailable', 'start_date': '2024-05-14'})
    assert resp.status_code == 400 and 'player' in resp.data
