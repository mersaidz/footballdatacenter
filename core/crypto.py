"""
Field-level encryption (ported from Aurora).

Used for provider API keys/secrets and medical free text. Fernet uses a random
IV, so the same plaintext encrypts to different ciphertext every time — a DB
dump can't be used to correlate identical secrets across clubs.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.db import models

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    key = os.getenv('FERNET_KEY')
    if not key:
        raise ImproperlyConfigured('FERNET_KEY is not set in environment variables')
    try:
        return Fernet(key.encode())
    except Exception as exc:  # noqa: BLE001 — re-raised as config error
        raise ImproperlyConfigured(f'Invalid FERNET_KEY: {exc}') from exc


def encrypt_value(value):
    if value is None or value == '':
        return value
    if not isinstance(value, str):
        value = str(value)
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value):
    if value is None or value == '':
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # Fail loud: silently returning None would hide key rotation / corruption.
        logger.exception('Failed to decrypt EncryptedTextField value')
        raise


class EncryptedTextField(models.TextField):
    """TextField that transparently encrypts on write and decrypts on read."""

    description = 'Symmetrically encrypted text field (Fernet)'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return decrypt_value(value)

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value is None:
            return None
        return encrypt_value(value)

    def value_to_string(self, obj):
        # dumpdata exports ciphertext, never plaintext.
        return self.get_prep_value(self.value_from_object(obj))
