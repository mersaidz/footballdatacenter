"""
Provider-agnostic football domain model.

Nothing here knows about StatsBomb, IMPECT or OpenField. Connectors translate
provider payloads into these tables; links back to provider IDs live in
providers.ExternalIdentity.

Pitch coordinate convention (all providers are converted to it):
    metres on a 105 x 68 pitch, from the acting team's perspective,
    x = 0 at own goal line, x = 105 at opponent goal line,
    y = 0 at the acting team's left touchline.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from clubs.models import ClubOwnedModel, Player, Team
from core.crypto import EncryptedTextField

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


class Competition(ClubOwnedModel):
    name = models.CharField(max_length=150)
    country = models.CharField(max_length=80, blank=True)
    gender = models.CharField(max_length=10, choices=Team.Gender.choices, default=Team.Gender.MALE)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Season(ClubOwnedModel):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='seasons')
    name = models.CharField(max_length=40, help_text='e.g. "2024/2025" or "2022"')

    _club_check_fields = ('competition',)

    class Meta:
        ordering = ['-name']
        constraints = [
            models.UniqueConstraint(fields=['competition', 'name'], name='unique_season_per_competition'),
        ]

    def __str__(self):
        return f'{self.competition} {self.name}'


class Match(ClubOwnedModel):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        PLAYED = 'played', 'Played'
        POSTPONED = 'postponed', 'Postponed'
        CANCELLED = 'cancelled', 'Cancelled'

    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='matches', null=True, blank=True)
    home_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='away_matches')
    kickoff = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    stage = models.CharField(max_length=60, blank=True, help_text='e.g. "Regular Season", "Final"')
    venue = models.CharField(max_length=150, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Actual length incl. stoppage time, derived from events.',
    )

    _club_check_fields = ('season', 'home_team', 'away_team')

    class Meta:
        ordering = ['-kickoff']
        indexes = [models.Index(fields=['club', '-kickoff'])]
        constraints = [
            models.CheckConstraint(condition=~Q(home_team=models.F('away_team')), name='match_teams_differ'),
        ]

    def __str__(self):
        return f'{self.home_team} vs {self.away_team} ({self.kickoff:%Y-%m-%d})'


class MatchAppearance(ClubOwnedModel):
    """A player's participation in a match (lineup + minutes)."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='appearances')
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='appearances')
    started = models.BooleanField(default=False)
    position = models.CharField(max_length=40, blank=True, help_text='Provider position label at kick-off/entry.')
    shirt_number = models.PositiveSmallIntegerField(null=True, blank=True)
    minute_on = models.PositiveSmallIntegerField(null=True, blank=True)
    minute_off = models.PositiveSmallIntegerField(null=True, blank=True)
    minutes_played = models.PositiveSmallIntegerField(default=0)

    _club_check_fields = ('match', 'team', 'player')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['match', 'player'], name='one_appearance_per_player_match'),
        ]


class TrainingSession(ClubOwnedModel):
    """
    A training session of one of the club's own teams.

    `md_code` is the match-day relative code used by performance staff
    worldwide: MD-1 is the day before a match, MD+1 the day after.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='training_sessions')
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(null=True, blank=True)
    md_code = models.CharField(max_length=12, blank=True, help_text='e.g. MD-4, MD-1, MD+1, MD+1/-2')
    session_type = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('training', 'Team training'), ('recovery', 'Recovery'),
            ('rehab', 'Rehab / individual'), ('gym', 'Gym'),
            # A match recorded by the tracking system that has no event-data Match to attach to yet.
            ('match', 'Match (no event data linked)'),
        ],
    )
    name = models.CharField(max_length=150, blank=True, help_text='Name in the source system.')
    notes = models.TextField(blank=True)

    _club_check_fields = ('team',)

    class Meta:
        ordering = ['-start']

    def clean(self):
        super().clean()
        if self.end and self.end <= self.start:
            raise ValidationError({'end': 'Session must end after it starts.'})

    def __str__(self):
        return f'{self.team} {self.md_code or "session"} {self.start:%Y-%m-%d}'


class Event(ClubOwnedModel):
    """On-ball (and pressure) events, normalised from event-data providers."""

    class Type(models.TextChoices):
        PASS = 'pass', 'Pass'
        SHOT = 'shot', 'Shot'
        CARRY = 'carry', 'Carry'
        DRIBBLE = 'dribble', 'Dribble'
        BALL_RECEIPT = 'ball_receipt', 'Ball receipt'
        PRESSURE = 'pressure', 'Pressure'
        DUEL = 'duel', 'Duel'
        INTERCEPTION = 'interception', 'Interception'
        BALL_RECOVERY = 'ball_recovery', 'Ball recovery'
        CLEARANCE = 'clearance', 'Clearance'
        BLOCK = 'block', 'Block'
        FOUL_COMMITTED = 'foul_committed', 'Foul committed'
        FOUL_WON = 'foul_won', 'Foul won'
        GOALKEEPER = 'goalkeeper', 'Goalkeeper action'
        MISCONTROL = 'miscontrol', 'Miscontrol'
        DISPOSSESSED = 'dispossessed', 'Dispossessed'
        OTHER = 'other', 'Other'

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='events')
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    player = models.ForeignKey(Player, on_delete=models.PROTECT, null=True, blank=True, related_name='events')

    provider = models.CharField(max_length=40)
    external_id = models.CharField(max_length=64)
    sequence = models.PositiveIntegerField(help_text='Order of the event within the match.')

    period = models.PositiveSmallIntegerField()
    minute = models.PositiveSmallIntegerField()
    second = models.PositiveSmallIntegerField()
    period_ms = models.PositiveIntegerField(help_text='Milliseconds since the start of the period.')

    event_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    outcome = models.CharField(max_length=40, blank=True)
    possession = models.PositiveIntegerField(null=True, blank=True)
    under_pressure = models.BooleanField(default=False)

    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    end_x = models.FloatField(null=True, blank=True)
    end_y = models.FloatField(null=True, blank=True)
    xg = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1)])

    attributes = models.JSONField(default=dict, blank=True, help_text='Provider-specific extras.')

    _club_check_fields = ('match', 'team', 'player')

    class Meta:
        ordering = ['match', 'sequence']
        indexes = [
            models.Index(fields=['match', 'sequence']),
            models.Index(fields=['club', 'player', 'event_type']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['match', 'provider', 'external_id'], name='unique_event_per_provider'),
        ]


class LoadMetrics(ClubOwnedModel):
    """
    Physical metrics shared by whole-session loads and per-period loads.

    Speed thresholds differ between clubs (19.8/25.2 km/h in English
    literature, 21/24 km/h common in Iberian football), so every row stores
    the thresholds its HSR / sprint distances were computed with. A number is
    only comparable to another number measured the same way.

    `quality_flags` marks values that are stored but should not drive reports,
    e.g. "max_speed_outlier" for a GPS spike above the player's realistic max.
    """

    class Flag:
        MAX_SPEED_OUTLIER = 'max_speed_outlier'

    provider = models.CharField(max_length=40)

    duration_min = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    total_distance_m = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(25000)])
    hsr_distance_m = models.PositiveIntegerField(null=True, blank=True, help_text='Above hsr_threshold_kmh')
    sprint_distance_m = models.PositiveIntegerField(null=True, blank=True, help_text='Above sprint_threshold_kmh')
    hsr_threshold_kmh = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    sprint_threshold_kmh = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    sprint_count = models.PositiveSmallIntegerField(null=True, blank=True)
    accelerations = models.PositiveSmallIntegerField(null=True, blank=True)
    decelerations = models.PositiveSmallIntegerField(null=True, blank=True)
    # No upper validator: raw provider values are stored as received and flagged instead.
    max_speed_kmh = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    player_load = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True, help_text='Catapult PlayerLoad™ (AU)',
    )
    extra_metrics = models.JSONField(default=dict, blank=True)
    quality_flags = models.JSONField(default=list, blank=True)

    class Meta:
        abstract = True

    @property
    def max_speed_for_reports(self):
        """Max speed, or None when it's a flagged GPS spike."""
        return None if self.Flag.MAX_SPEED_OUTLIER in (self.quality_flags or []) else self.max_speed_kmh


class PlayerLoad(LoadMetrics):
    """
    Physical output of one player in one match OR one training session.

    `load_basis` says what the numbers cover: the whole recorded activity, or
    for matches only the playing periods (halves, extra time) — warm-up and
    anything else recorded around the game excluded.
    `participation` is the provider's tag for how the player took part:
    only "full" rows feed team averages and match-day norms.
    """

    class Participation(models.TextChoices):
        FULL = 'full', 'Full'
        PARTIAL = 'partial', 'Partial'
        ALTERNATE = 'alternate', 'Alternate (individual / RTP)'
        OTHER = 'other', 'Other'

    class Basis(models.TextChoices):
        ACTIVITY = 'activity', 'Whole activity'
        MATCH_PERIODS = 'match_periods', 'Match playing periods only'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='loads')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, null=True, blank=True, related_name='loads')
    training_session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, null=True, blank=True, related_name='loads',
    )
    rpe = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text='Session RPE (CR-10) collected from the player',
    )
    participation = models.CharField(max_length=12, choices=Participation.choices, blank=True, db_index=True)
    load_basis = models.CharField(max_length=16, choices=Basis.choices, default=Basis.ACTIVITY)

    _club_check_fields = ('player', 'match', 'training_session')

    class Meta:
        constraints = [
            # Exactly one context: a load row belongs to a match XOR a session.
            models.CheckConstraint(
                condition=(
                    Q(match__isnull=False, training_session__isnull=True)
                    | Q(match__isnull=True, training_session__isnull=False)
                ),
                name='load_has_exactly_one_context',
            ),
            models.UniqueConstraint(
                fields=['player', 'match', 'provider'], condition=Q(match__isnull=False),
                name='unique_match_load_per_provider',
            ),
            models.UniqueConstraint(
                fields=['player', 'training_session', 'provider'], condition=Q(training_session__isnull=False),
                name='unique_session_load_per_provider',
            ),
        ]


class ActivityPeriod(ClubOwnedModel):
    """
    A period inside a recorded activity: "1st Half", "Warm Up", "Rondo 19v3"…
    Staff name periods however they like, so the `role` is resolved by
    football.services.period_roles and `role_source` records how sure we are.
    """

    class Role(models.TextChoices):
        WARM_UP = 'warm_up', 'Warm-up'
        FIRST_HALF = 'first_half', '1st half'
        SECOND_HALF = 'second_half', '2nd half'
        EXTRA_TIME_1 = 'extra_time_1', 'Extra time 1'
        EXTRA_TIME_2 = 'extra_time_2', 'Extra time 2'
        PENALTIES = 'penalties', 'Penalty shoot-out'
        SEGMENT = 'segment', 'Segment inside another period'
        TOP_UP = 'top_up', 'Top-up / compensatory'
        RECOVERY = 'recovery', 'Recovery'
        REHAB = 'rehab', 'Rehab / return to play'
        DRILL = 'drill', 'Drill'
        UNKNOWN = 'unknown', 'Needs review'

    class Source(models.TextChoices):
        TAG = 'tag', 'Provider tag'
        CLUB = 'club', 'Club mapping'
        DICTIONARY = 'dictionary', 'Name dictionary'
        STRUCTURE = 'structure', 'Match structure'
        DEFAULT = 'default', 'Default for training'
        MANUAL = 'manual', 'Set by staff'
        NONE = 'none', 'Not resolved'

    PLAYING_ROLES = (Role.FIRST_HALF, Role.SECOND_HALF, Role.EXTRA_TIME_1, Role.EXTRA_TIME_2)

    match = models.ForeignKey(Match, on_delete=models.CASCADE, null=True, blank=True, related_name='periods')
    training_session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, null=True, blank=True, related_name='periods',
    )
    provider = models.CharField(max_length=40)
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    normalized_name = models.CharField(max_length=150, db_index=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    sequence = models.PositiveSmallIntegerField(default=0)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.UNKNOWN, db_index=True)
    role_source = models.CharField(max_length=12, choices=Source.choices, default=Source.NONE)
    role_confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    _club_check_fields = ('match', 'training_session')

    class Meta:
        ordering = ['start']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(match__isnull=False, training_session__isnull=True)
                    | Q(match__isnull=True, training_session__isnull=False)
                ),
                name='period_has_exactly_one_context',
            ),
            models.UniqueConstraint(fields=['club', 'provider', 'external_id'], name='unique_period_per_provider'),
        ]

    @property
    def duration_min(self) -> float:
        return round((self.end - self.start).total_seconds() / 60, 1)

    def __str__(self):
        return f'{self.name} ({self.get_role_display()})'


class PeriodLoad(LoadMetrics):
    """One player's output inside one period (half, drill, warm-up…)."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='period_loads')
    period = models.ForeignKey(ActivityPeriod, on_delete=models.CASCADE, related_name='loads')

    _club_check_fields = ('player', 'period')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['player', 'period', 'provider'], name='unique_period_load_per_provider'),
        ]


class PeriodRoleMapping(ClubOwnedModel):
    """A club's own vocabulary: "1 тайм" → first_half. Learned from staff decisions."""

    normalized_name = models.CharField(max_length=150)
    role = models.CharField(max_length=16, choices=ActivityPeriod.Role.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['club', 'normalized_name'], name='one_role_per_period_name'),
        ]

    def __str__(self):
        return f'{self.normalized_name} → {self.role}'


class PlayerAvailability(ClubOwnedModel):
    """
    Availability episode. Status is visible to coaching staff; diagnosis and
    clinical notes are encrypted at rest and visible to medical staff only.
    """

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        MODIFIED = 'modified', 'Modified training'
        UNAVAILABLE = 'unavailable', 'Unavailable'

    class Reason(models.TextChoices):
        INJURY = 'injury', 'Injury'
        ILLNESS = 'illness', 'Illness'
        LOAD_MANAGEMENT = 'load_management', 'Load management'
        PERSONAL = 'personal', 'Personal'
        SUSPENSION = 'suspension', 'Suspension'
        INTERNATIONAL = 'international', 'International duty'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='availability')
    status = models.CharField(max_length=12, choices=Status.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices, blank=True)
    start_date = models.DateField()
    expected_return = models.DateField(null=True, blank=True)
    actual_return = models.DateField(null=True, blank=True)

    diagnosis = EncryptedTextField(blank=True, default='')
    clinical_notes = EncryptedTextField(blank=True, default='')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    _club_check_fields = ('player',)

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(actual_return__isnull=True) | Q(actual_return__gte=models.F('start_date')),
                name='availability_return_after_start',
            ),
        ]
