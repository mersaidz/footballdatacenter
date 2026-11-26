"""
What players tell us: a morning check-in (sleep, energy, soreness, stress, mood) and
session RPE. Answered by the player on his phone (a personal link, no password) or
entered by staff after a conversation.

Every item is scored 1–5 with 5 = best, so a falling number always means "worse".
Health data: comments are encrypted, and details are visible only to S&C and medical staff.
"""
import hashlib
import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from clubs.models import ClubOwnedModel, Player
from core.crypto import EncryptedTextField
from football.models import TrainingSession

ITEMS = ('sleep_quality', 'energy', 'soreness', 'stress', 'mood')
SORE_AREAS = ('head_neck', 'shoulder', 'chest', 'upper_back', 'lower_back', 'abdomen', 'groin', 'hip', 'quad', 'hamstring',
              'adductor', 'knee', 'calf', 'shin', 'ankle', 'foot', 'achilles')
score = [MinValueValidator(1), MaxValueValidator(5)]


class Source(models.TextChoices):
    PLAYER = 'player', _('Player')
    STAFF = 'staff', _('Staff')
    DEMO = 'demo', _('Demo')


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class PlayerLink(ClubOwnedModel):
    """A player's personal link to the questionnaire. Only the hash is stored; a new link revokes the old one."""
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='wellness_links')
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    _club_check_fields = ('player',)

    @classmethod
    def issue(cls, player, user=None) -> tuple['PlayerLink', str]:
        cls.objects.filter(player=player, revoked_at__isnull=True).update(revoked_at=timezone.now())
        raw = secrets.token_urlsafe(24)
        return cls.objects.create(club=player.club, player=player, token_hash=hash_token(raw), created_by=user), raw

    @classmethod
    def resolve(cls, raw: str) -> 'PlayerLink | None':
        return cls.objects.select_related('player', 'club').filter(token_hash=hash_token(raw or ''), revoked_at__isnull=True).first()


class WellnessCheckin(ClubOwnedModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='checkins')
    date = models.DateField(db_index=True)
    sleep_quality = models.PositiveSmallIntegerField(validators=score)
    sleep_hours = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True,
                                      validators=[MinValueValidator(0), MaxValueValidator(16)])
    energy = models.PositiveSmallIntegerField(validators=score)
    soreness = models.PositiveSmallIntegerField(validators=score, help_text='5 = no soreness')
    stress = models.PositiveSmallIntegerField(validators=score, help_text='5 = no stress')
    mood = models.PositiveSmallIntegerField(validators=score)
    sore_areas = models.JSONField(default=list, blank=True)
    comment = EncryptedTextField(blank=True, default='')
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PLAYER)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    _club_check_fields = ('player',)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['player', 'date'], name='one_checkin_per_day')]
        ordering = ['-date']

    @property
    def total(self) -> int:
        return sum(getattr(self, i) for i in ITEMS)


class RpeEntry(ClubOwnedModel):
    """
    Session RPE (Borg CR-10, Foster): 0 = rest … 10 = maximal. sRPE = RPE × minutes.
    Players answer right after training, often before the GPS sync has created the session,
    so an entry is keyed by day and linked to the session once it exists.
    """
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='rpe_entries')
    date = models.DateField(db_index=True)
    session = models.ForeignKey(TrainingSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='rpe_entries')
    rpe = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)])
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PLAYER)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    _club_check_fields = ('player', 'session')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['player', 'date'], name='one_rpe_per_day')]
        ordering = ['-date']
