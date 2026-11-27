"""A club's own OpenField token: entered hidden, stored encrypted, never printed."""
import pytest
from django.core.management import call_command
from django.db import connection

from clubs.models import Club
from providers.connectors.openfield import OpenFieldError
from providers.models import Provider, ProviderAccount

pytestmark = pytest.mark.django_db


def test_set_token_is_hidden_and_encrypted(monkeypatch, capsys):
    monkeypatch.setattr('getpass.getpass', lambda prompt='': 'secret-club-token-123')
    # no network in tests: stop right after the token is stored
    monkeypatch.setattr('providers.management.commands.sync_openfield.ingest_physical',
                        lambda *a, **k: (_ for _ in ()).throw(OpenFieldError('stop')))
    with pytest.raises(Exception):
        call_command('sync_openfield', '--club', 'elimai', '--create-club', '--set-token')
    account = ProviderAccount.objects.get(club=Club.objects.get(slug='elimai'), provider=Provider.CATAPULT_OPENFIELD)
    assert account.api_key == 'secret-club-token-123'
    with connection.cursor() as cur:
        cur.execute('SELECT api_key FROM providers_provideraccount WHERE id = %s', [account.pk])
        assert 'secret-club-token' not in cur.fetchone()[0]
    assert 'secret-club-token' not in capsys.readouterr().out
