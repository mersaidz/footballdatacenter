import os

from cryptography.fernet import Fernet

# Deterministic test environment — real secrets never needed to run the suite.
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-only-secret-key-not-for-production')
os.environ.setdefault('FERNET_KEY', Fernet.generate_key().decode())

import pytest  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework_simplejwt.tokens import RefreshToken  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'providers', 'tests', 'fixtures', 'statsbomb')


@pytest.fixture
def club(db):
    from clubs.models import Club
    return Club.objects.create(name='FC Astana', slug='astana')


@pytest.fixture
def other_club(db):
    from clubs.models import Club
    return Club.objects.create(name='Kairat', slug='kairat')


@pytest.fixture
def make_member(db):
    """make_member(club, role) → (user, authenticated APIClient)"""
    from accounts.models import User
    from clubs.models import StaffMembership
    counter = {'n': 0}

    def _make(club, role):
        counter['n'] += 1
        user = User.objects.create_user(email=f'{role}{counter["n"]}@example.com', password='x-strong-pass-123')
        StaffMembership.objects.create(user=user, club=club, role=role)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return user, client

    return _make


@pytest.fixture
def sb_connector():
    from providers.connectors.statsbomb import StatsBombOpenConnector
    return StatsBombOpenConnector(data_dir=FIXTURE_DIR)


@pytest.fixture
def ingested(club, sb_connector):
    """Fixture season ingested into `club`. Returns the IngestSummary."""
    from providers.services.ingest import ingest_season
    return ingest_season(club, sb_connector, '1', '2', own_team_name='FC Astana')
