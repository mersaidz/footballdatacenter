from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .sanitize import find_forbidden_keys


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Immutable audit trail (ported from Aurora, extended with club scope).

    Survives deletion of both the user and the club: FKs are SET_NULL and
    identity snapshots are captured at write time.
    """

    class Action(models.TextChoices):
        PROVIDER_CONNECTED = 'provider_connected', 'Provider account connected'
        PROVIDER_UPDATED = 'provider_updated', 'Provider account updated'
        SYNC_SUCCESS = 'sync_success', 'Sync success'
        SYNC_FAILED = 'sync_failed', 'Sync failed'
        IDENTITY_CONFIRMED = 'identity_confirmed', 'External identity confirmed'
        IDENTITY_REJECTED = 'identity_rejected', 'External identity rejected'
        MEDICAL_RECORD_VIEWED = 'medical_record_viewed', 'Medical record viewed'
        MEDICAL_RECORD_CHANGED = 'medical_record_changed', 'Medical record created/changed'
        MEMBERSHIP_CHANGED = 'membership_changed', 'Staff membership changed'
        PERIOD_ROLE_CHANGED = 'period_role_changed', 'Period role set by staff'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    user_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    user_email_snapshot = models.CharField(max_length=254, blank=True)

    club = models.ForeignKey('clubs.Club', on_delete=models.SET_NULL, null=True, blank=True)
    club_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)

    action = models.CharField(max_length=50, choices=Action.choices)
    provider = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    extra_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_id_snapshot', '-created_at']),
            models.Index(fields=['club_id_snapshot', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('AuditLog entries cannot be modified once created.')

        if self.extra_info:
            hits = find_forbidden_keys(self.extra_info)
            if hits:
                raise ValidationError(
                    f'Sensitive keys found in extra_info at paths: {hits}. '
                    'Pass the payload through sanitize_payload() before logging.'
                )

        if self.user_id and self.user_id_snapshot is None:
            self.user_id_snapshot = self.user_id
        if self.user_id and not self.user_email_snapshot:
            try:
                self.user_email_snapshot = (self.user.email or '')[:254]
            except Exception:  # noqa: BLE001 — never block the audit write
                self.user_email_snapshot = ''
        if self.club_id and self.club_id_snapshot is None:
            self.club_id_snapshot = self.club_id

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('AuditLog entries cannot be deleted.')

    def __str__(self):
        return f'AuditLog({self.action}, user={self.user_id_snapshot}, club={self.club_id_snapshot})'
