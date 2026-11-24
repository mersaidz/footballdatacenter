"""
Tenancy: every piece of football data belongs to exactly one Club.

Why tenant-scope even "public" things like competitions and opponent teams?
Because data arrives under the club's own provider licence (its OpenField /
IMPECT / Wyscout keys). Club A's licence must never leak data into Club B.
The cost is some duplication of reference rows; the benefit is that
isolation is a single `club_id` filter everywhere, enforced by one mixin.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Club(TimeStampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    country = models.CharField(max_length=80, blank=True)
    timezone = models.CharField(max_length=64, default='UTC')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ClubOwnedModel(TimeStampedModel):
    """
    Abstract base for all tenant data (port of Aurora's UserOwnedMixin).

    `_club_check_fields` lists FKs whose target must belong to the same club.
    Prevents e.g. a Match in Club A pointing at a Team owned by Club B.
    """

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='+')

    _club_check_fields: tuple[str, ...] = ()

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.club_id is None:
            return
        errors = {}
        for field_name in self._club_check_fields:
            related = getattr(self, field_name, None)
            if related is None:
                continue
            related_club = getattr(related, 'club_id', None)
            if related_club is not None and related_club != self.club_id:
                errors[field_name] = (
                    f'Tenant mismatch: {field_name} belongs to club {related_club}, '
                    f'this record belongs to club {self.club_id}.'
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Cross-tenant links are checked on every save, not only in forms —
        # ingestion code calls .save()/.create() directly.
        self._check_tenant_links()
        super().save(*args, **kwargs)

    def _check_tenant_links(self):
        for field_name in self._club_check_fields:
            related = getattr(self, field_name, None)
            if related is not None and getattr(related, 'club_id', None) not in (None, self.club_id):
                raise ValidationError({field_name: 'Cross-club reference is not allowed.'})


class Team(ClubOwnedModel):
    """
    Any team that appears in the data. `is_own` marks the club's own squads
    (first team, U21, academy); everything else is an opponent / scouting target.
    """

    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=40, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE)
    country = models.CharField(max_length=80, blank=True)
    is_own = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['club', 'is_own'])]

    def __str__(self):
        return self.name


class Player(ClubOwnedModel):
    class Foot(models.TextChoices):
        LEFT = 'left', 'Left'
        RIGHT = 'right', 'Right'
        BOTH = 'both', 'Both'

    class Position(models.TextChoices):
        GK = 'GK', 'Goalkeeper'
        CB = 'CB', 'Centre-back'
        FB = 'FB', 'Full-back / Wing-back'
        DM = 'DM', 'Defensive midfielder'
        CM = 'CM', 'Central midfielder'
        AM = 'AM', 'Attacking midfielder'
        W = 'W', 'Winger'
        CF = 'CF', 'Centre-forward'

    full_name = models.CharField(max_length=200)
    known_name = models.CharField(max_length=120, blank=True, help_text='Name used on shirts / by media.')
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    primary_position = models.CharField(max_length=3, choices=Position.choices, blank=True)
    preferred_foot = models.CharField(max_length=5, choices=Foot.choices, blank=True)
    current_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='players',
    )
    shirt_number = models.PositiveSmallIntegerField(null=True, blank=True)

    _club_check_fields = ('current_team',)

    class Meta:
        ordering = ['full_name']
        indexes = [models.Index(fields=['club', 'full_name'])]

    @property
    def display_name(self) -> str:
        return self.known_name or self.full_name

    def __str__(self):
        return self.display_name


class StaffMembership(TimeStampedModel):
    """A user's role inside one club. Roles drive capabilities (clubs.permissions)."""

    class Role(models.TextChoices):
        CLUB_ADMIN = 'club_admin', 'Club admin'
        SPORTING_DIRECTOR = 'sporting_director', 'Sporting director'
        HEAD_COACH = 'head_coach', 'Head coach'
        ASSISTANT_COACH = 'assistant_coach', 'Assistant coach'
        ANALYST = 'analyst', 'Performance / data analyst'
        SPORTS_SCIENTIST = 'sports_scientist', 'Sports scientist / S&C'
        PHYSIO = 'physio', 'Physiotherapist'
        DOCTOR = 'doctor', 'Club doctor'
        SCOUT = 'scout', 'Scout'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=30, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'club'], condition=Q(is_active=True), name='one_active_membership_per_club',
            ),
        ]

    def __str__(self):
        return f'{self.user} @ {self.club} ({self.role})'
