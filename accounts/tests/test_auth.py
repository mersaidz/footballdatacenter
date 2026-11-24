import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_login_returns_tokens(make_member, club):
    user, _ = make_member(club, 'analyst')
    resp = APIClient().post('/api/auth/token/', {'email': user.email, 'password': 'x-strong-pass-123'})
    assert resp.status_code == 200 and 'access' in resp.data


def test_soft_deleted_user_token_rejected_immediately(make_member, club):
    user, client = make_member(club, 'analyst')
    assert client.get('/api/clubs/').status_code == 200
    user.soft_delete()
    assert client.get('/api/clubs/').status_code == 401


def test_anonymous_is_401(club):
    assert APIClient().get(f'/api/clubs/{club.pk}/players/').status_code == 401


def test_user_str_masks_email(make_member, club):
    user, _ = make_member(club, 'scout')
    assert str(user).startswith('s***@')
