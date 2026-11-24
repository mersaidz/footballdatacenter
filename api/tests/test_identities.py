import pytest

from clubs.models import Player
from core.models import AuditLog
from football.models import Event
from providers.connectors.base import NormalizedPlayer
from providers.models import ExternalIdentity
from providers.services.identity import resolve_player

pytestmark = pytest.mark.django_db


@pytest.fixture
def suggested(ingested, club):
    """OpenField sends 'Marin Tomassov' (typo, no DOB) → fuzzy-linked to Marin Tomasov, flagged."""
    resolve_player(club, 'catapult_openfield', NormalizedPlayer(external_id='of-77', full_name='Marin Tomassov'))
    return ExternalIdentity.objects.get(provider='catapult_openfield')


def test_review_queue(make_member, club, suggested):
    _, c = make_member(club, 'analyst')
    rows = c.get(f'/api/clubs/{club.pk}/identities/?status=suggested').data['results']
    assert [r['external_name'] for r in rows] == ['Marin Tomassov']
    assert rows[0]['target_name'] == 'Marin Tomasov'


def test_coach_cannot_manage_identities(make_member, club, suggested):
    _, c = make_member(club, 'head_coach')
    assert c.get(f'/api/clubs/{club.pk}/identities/').status_code == 403
    assert c.post(f'/api/clubs/{club.pk}/identities/{suggested.pk}/confirm/').status_code == 403


def test_confirm(make_member, club, suggested):
    user, c = make_member(club, 'analyst')
    resp = c.post(f'/api/clubs/{club.pk}/identities/{suggested.pk}/confirm/')
    assert resp.status_code == 200 and resp.data['status'] == 'confirmed'
    suggested.refresh_from_db()
    assert suggested.reviewed_by == user
    assert AuditLog.objects.filter(action=AuditLog.Action.IDENTITY_CONFIRMED).exists()


def test_reject_creates_new_player_and_moves_provider_rows(make_member, club, ingested):
    # A wrong StatsBomb-side link: pretend the StatsBomb identity of Tomasov was a fuzzy suggestion.
    ident = ExternalIdentity.objects.get(provider='statsbomb_open', entity_type='player', external_id='1001')
    old_player = ident.target
    _, c = make_member(club, 'analyst')
    resp = c.post(f'/api/clubs/{club.pk}/identities/{ident.pk}/reject/')
    assert resp.status_code == 200
    ident.refresh_from_db()
    assert ident.object_id != old_player.pk
    new_player = Player.objects.get(pk=ident.object_id)
    assert Event.objects.get(event_type='shot').player == new_player
    assert new_player.appearances.count() == 1 and old_player.appearances.count() == 0
