"""
Everything that connects the platform to external data providers.

- ProviderAccount   — the club's credentials for one provider (encrypted).
- RawPayload        — provider responses exactly as received (Aurora pattern):
                      re-parse history after a parser fix, no re-download needed.
- ExternalIdentity  — the cross-provider ID map. "Player 5503 in StatsBomb",
                      "athlete 9f1c… in OpenField" and "player 1234 in IMPECT"
                      all resolve to one internal Player.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from clubs.models import ClubOwnedModel
from core.crypto import EncryptedTextField


class Provider(models.TextChoices):
    STATSBOMB_OPEN = 'statsbomb_open', _('StatsBomb Open Data')
    STATSBOMB = 'statsbomb', _('StatsBomb (Hudl)')
    CATAPULT_OPENFIELD = 'catapult_openfield', _('Catapult OpenField')
    IMPECT = 'impect', _('IMPECT')
    WYSCOUT = 'wyscout', _('Wyscout (Hudl)')
    SKILLCORNER = 'skillcorner', _('SkillCorner')
    MANUAL = 'manual', _('Manual entry')


class ProviderAccount(ClubOwnedModel):
    provider = models.CharField(max_length=40, choices=Provider.choices)
    is_active = models.BooleanField(default=True)
    base_url = models.URLField(blank=True)
    api_key = EncryptedTextField(blank=True, default='')
    api_secret = EncryptedTextField(blank=True, default='')
    config = models.JSONField(default=dict, blank=True, help_text='Non-secret settings, e.g. region, team IDs.')
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['club', 'provider'], name='one_account_per_provider_per_club'),
        ]

    def __str__(self):
        return f'{self.get_provider_display()} @ club {self.club_id}'


class RawPayload(ClubOwnedModel):
    provider = models.CharField(max_length=40, choices=Provider.choices)
    resource_type = models.CharField(max_length=40, help_text='e.g. match, lineups, events, activity')
    external_id = models.CharField(max_length=128)
    payload = models.JSONField()
    sha256 = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=20, help_text='Our parser version at ingest time.')
    provider_api_version = models.CharField(max_length=20, blank=True)

    class Meta:
        indexes = [models.Index(fields=['club', 'provider', 'resource_type', 'external_id'])]
        constraints = [
            # Same bytes from the same resource are stored once → re-running a sync is free.
            models.UniqueConstraint(
                fields=['club', 'provider', 'resource_type', 'external_id', 'sha256'],
                name='raw_payload_idempotent',
            ),
        ]


class ExternalIdentity(ClubOwnedModel):
    class EntityType(models.TextChoices):
        PLAYER = 'player', _('Player')
        TEAM = 'team', _('Team')
        MATCH = 'match', _('Match')
        COMPETITION = 'competition', _('Competition')
        SEASON = 'season', _('Season')
        TRAINING_SESSION = 'training_session', _('Training session')

    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', _('Confirmed')      # exact or human-verified
        SUGGESTED = 'suggested', _('Needs review')   # fuzzy match, linked but flagged

    class Method(models.TextChoices):
        CREATED = 'created', _('New internal record created')
        EXACT = 'exact', _('Exact attribute match')
        FUZZY = 'fuzzy', _('Fuzzy name match')
        MANUAL = 'manual', _('Linked by a human')
        DEMO = 'demo', _('Demo link (test data, not the same person)')

    provider = models.CharField(max_length=40, choices=Provider.choices)
    entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    external_id = models.CharField(max_length=128)
    external_name = models.CharField(max_length=200, blank=True)
    external_meta = models.JSONField(default=dict, blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    method = models.CharField(max_length=10, choices=Method.choices)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=1)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'external identities'
        indexes = [models.Index(fields=['club', 'content_type', 'object_id'])]
        constraints = [
            models.UniqueConstraint(
                fields=['club', 'provider', 'entity_type', 'external_id'],
                name='one_mapping_per_external_id',
            ),
            # One internal object maps to at most one ID per provider —
            # two StatsBomb IDs pointing at the same Player means a bad merge.
            models.UniqueConstraint(
                fields=['club', 'provider', 'content_type', 'object_id'],
                name='one_external_id_per_provider_per_object',
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1), name='identity_confidence_range',
            ),
        ]

    def __str__(self):
        return f'{self.provider}:{self.entity_type}:{self.external_id} → {self.content_type.model}#{self.object_id}'
