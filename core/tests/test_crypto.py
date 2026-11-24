import pytest
from cryptography.fernet import Fernet, InvalidToken

from core.crypto import decrypt_value, encrypt_value


def test_roundtrip():
    assert decrypt_value(encrypt_value('impect-api-key')) == 'impect-api-key'


def test_ciphertext_is_non_deterministic():
    assert encrypt_value('same') != encrypt_value('same')


def test_empty_values_pass_through():
    assert encrypt_value('') == '' and encrypt_value(None) is None


def test_wrong_key_fails_loud(monkeypatch):
    token = encrypt_value('secret')
    monkeypatch.setenv('FERNET_KEY', Fernet.generate_key().decode())
    with pytest.raises(InvalidToken):
        decrypt_value(token)


@pytest.mark.django_db
def test_provider_key_is_encrypted_at_rest(club):
    from django.db import connection

    from providers.models import ProviderAccount
    acc = ProviderAccount.objects.create(club=club, provider='impect', api_key='plain-key-123')
    with connection.cursor() as cur:
        cur.execute('SELECT api_key FROM providers_provideraccount WHERE id = %s', [acc.pk])
        stored = cur.fetchone()[0]
    assert 'plain-key-123' not in stored
    assert ProviderAccount.objects.get(pk=acc.pk).api_key == 'plain-key-123'
