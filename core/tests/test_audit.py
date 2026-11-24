import pytest
from django.core.exceptions import ValidationError

from core.models import AuditLog
from core.sanitize import sanitize_payload
from core.services.audit import log_event

pytestmark = pytest.mark.django_db


def test_audit_is_immutable(club):
    log = log_event(action=AuditLog.Action.SYNC_SUCCESS, club=club)
    log.provider = 'tampered'
    with pytest.raises(PermissionError):
        log.save()
    with pytest.raises(PermissionError):
        log.delete()


def test_forbidden_keys_rejected_on_direct_write(club):
    with pytest.raises(ValidationError):
        AuditLog.objects.create(action=AuditLog.Action.SYNC_SUCCESS, club=club, extra_info={'nested': {'api_key': 'x'}})


def test_log_event_strips_secrets(club):
    log = log_event(action=AuditLog.Action.SYNC_SUCCESS, club=club, extra_info={'ok': 1, 'token': 'x'})
    assert log.extra_info == {'ok': 1}


def test_snapshots_survive_club_deletion(club):
    log = log_event(action=AuditLog.Action.SYNC_SUCCESS, club=club)
    club_id = club.pk
    club.delete()
    log = AuditLog.objects.get(pk=log.pk)
    assert log.club_id is None and log.club_id_snapshot == club_id


def test_training_session_keys_are_not_redacted():
    # Football-specific: "session" means a training session, not an auth cookie.
    data = {'session': {'id': 5, 'md_code': 'MD-1'}, 'session_id': 5, 'session_token': 'x'}
    assert sanitize_payload(data) == {'session': {'id': 5, 'md_code': 'MD-1'}, 'session_id': 5,
                                      'session_token': '[REDACTED]'}
