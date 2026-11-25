from rest_framework import serializers

from clubs.models import Club, Player, StaffMembership, Team
from football.models import ActivityPeriod, Event, Match, MatchAppearance, PlayerAvailability, PlayerLoad
from providers.models import ExternalIdentity


class MyClubSerializer(serializers.ModelSerializer):
    club_id = serializers.IntegerField(source='club.id')
    club_name = serializers.CharField(source='club.name')
    club_slug = serializers.CharField(source='club.slug')

    class Meta:
        model = StaffMembership
        fields = ('club_id', 'club_name', 'club_slug', 'role')


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ('id', 'name', 'short_name', 'gender', 'country', 'is_own')


class PlayerSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    current_team = TeamSerializer(read_only=True)

    class Meta:
        model = Player
        fields = (
            'id', 'display_name', 'full_name', 'known_name', 'date_of_birth', 'nationality',
            'primary_position', 'preferred_foot', 'shirt_number', 'current_team',
        )


class MatchSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    competition = serializers.CharField(source='season.competition.name', default=None, read_only=True)
    season = serializers.CharField(source='season.name', default=None, read_only=True)

    class Meta:
        model = Match
        fields = (
            'id', 'kickoff', 'status', 'competition', 'season', 'stage', 'venue',
            'home_team', 'away_team', 'home_score', 'away_score', 'duration_minutes',
        )


class AppearanceSerializer(serializers.ModelSerializer):
    player_id = serializers.IntegerField(source='player.id')
    player = serializers.CharField(source='player.display_name')
    team_id = serializers.IntegerField(source='team.id')

    class Meta:
        model = MatchAppearance
        fields = ('player_id', 'player', 'team_id', 'started', 'position', 'shirt_number',
                  'minute_on', 'minute_off', 'minutes_played')


class EventSerializer(serializers.ModelSerializer):
    player = serializers.CharField(source='player.display_name', default=None)

    class Meta:
        model = Event
        fields = (
            'id', 'sequence', 'period', 'minute', 'second', 'event_type', 'outcome',
            'team_id', 'player_id', 'player', 'x', 'y', 'end_x', 'end_y', 'xg',
            'under_pressure', 'possession', 'attributes',
        )


class PlayerLoadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerLoad
        fields = (
            'id', 'player_id', 'match_id', 'training_session_id', 'provider', 'duration_min',
            'total_distance_m', 'hsr_distance_m', 'sprint_distance_m', 'hsr_threshold_kmh',
            'sprint_threshold_kmh', 'sprint_count', 'accelerations', 'decelerations', 'max_speed_kmh',
            'player_load', 'rpe', 'participation', 'load_basis', 'quality_flags', 'extra_metrics',
        )


class AvailabilityStatusSerializer(serializers.ModelSerializer):
    """What coaches see: can the player train / play, and roughly when he's back."""
    player_name = serializers.CharField(source='player.display_name', read_only=True)

    class Meta:
        model = PlayerAvailability
        fields = ('id', 'player', 'player_name', 'status', 'reason', 'start_date',
                  'expected_return', 'actual_return')
        read_only_fields = fields


class AvailabilityMedicalSerializer(AvailabilityStatusSerializer):
    """Medical staff only: includes encrypted clinical fields."""

    class Meta(AvailabilityStatusSerializer.Meta):
        fields = AvailabilityStatusSerializer.Meta.fields + ('diagnosis', 'clinical_notes')
        read_only_fields = ('id', 'player_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        club = self.context.get('club')
        if club is not None:
            # Other clubs' players are simply "does not exist" — no cross-tenant probing.
            self.fields['player'].queryset = Player.objects.filter(club=club)

    def validate_player(self, player):
        if player.club_id != self.context['club'].id:
            raise serializers.ValidationError('Unknown player.')  # same message as "doesn't exist"
        return player

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        ret = attrs.get('actual_return', getattr(self.instance, 'actual_return', None))
        if start and ret and ret < start:
            raise serializers.ValidationError({'actual_return': 'Return date is before start date.'})
        return attrs


class ExternalIdentitySerializer(serializers.ModelSerializer):
    target_type = serializers.CharField(source='content_type.model', read_only=True)
    target_id = serializers.IntegerField(source='object_id', read_only=True)
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = ExternalIdentity
        fields = ('id', 'provider', 'entity_type', 'external_id', 'external_name', 'external_meta',
                  'target_type', 'target_id', 'target_name', 'status', 'method', 'confidence',
                  'reviewed_at')

    def get_target_name(self, obj):
        target = obj.target
        return str(target) if target is not None else None


class ActivityPeriodSerializer(serializers.ModelSerializer):
    duration_min = serializers.FloatField(read_only=True)
    session_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityPeriod
        fields = ('id', 'name', 'role', 'role_source', 'role_confidence', 'start', 'end', 'duration_min',
                  'match_id', 'training_session_id', 'session_name')

    def get_session_name(self, obj):
        if obj.training_session_id:
            return obj.training_session.name
        return str(obj.match) if obj.match_id else None


class AssignRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[r for r in ActivityPeriod.Role.values if r != 'unknown'])
    remember = serializers.BooleanField(default=True)


# --- metrics ---------------------------------------------------------------------------------

from metrics.models import MetricDefinition, MetricRequest, MetricSet, ProviderMetric  # noqa: E402


class CatalogueEntrySerializer(serializers.ModelSerializer):
    tracked_as = serializers.SerializerMethodField()

    class Meta:
        model = ProviderMetric
        fields = ('id', 'provider', 'slug', 'name', 'unit_type', 'tracked_as', 'requested')

    requested = serializers.SerializerMethodField()

    def get_tracked_as(self, obj):
        return self.context.get('tracked', {}).get((obj.provider, obj.slug))

    def get_requested(self, obj):
        return (obj.provider, obj.slug) in self.context.get('requested', set())


class MetricDefinitionSerializer(serializers.ModelSerializer):
    is_core = serializers.BooleanField(read_only=True)

    class Meta:
        model = MetricDefinition
        fields = ('id', 'key', 'label', 'short_label', 'unit', 'category', 'aggregation', 'higher_is_better',
                  'decimals', 'multiplier', 'zero_is_missing', 'description', 'provider', 'provider_slug', 'is_core',
                  'enabled')
        read_only_fields = ('id', 'key', 'provider', 'provider_slug', 'is_core')


class EnableMetricSerializer(serializers.Serializer):
    provider_slug = serializers.CharField(max_length=150)
    provider = serializers.CharField(max_length=40, default='catapult_openfield')
    label = serializers.CharField(max_length=120, required=False)
    short_label = serializers.CharField(max_length=24, required=False)
    category = serializers.CharField(max_length=20, required=False)
    aggregation = serializers.CharField(max_length=16, required=False)
    unit = serializers.CharField(max_length=20, required=False)


class MetricSetSerializer(serializers.ModelSerializer):
    scope = serializers.ChoiceField(choices=['club', 'personal'], write_only=True, default='personal')
    is_club = serializers.SerializerMethodField()
    metrics = serializers.SerializerMethodField()

    class Meta:
        model = MetricSet
        fields = ('id', 'name', 'metric_keys', 'display', 'is_default', 'is_club', 'scope', 'metrics')

    def get_is_club(self, obj):
        return obj.owner_id is None

    def get_metrics(self, obj):
        defs = {d.key: d for d in MetricDefinition.objects.filter(club_id=obj.club_id, key__in=obj.metric_keys)}
        return [{'key': k, 'label': defs[k].label, 'short_label': defs[k].short_label or defs[k].label,
                 'unit': defs[k].unit, 'category': defs[k].category} for k in obj.metric_keys if k in defs]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        candidate = MetricSet(club=self.context['club'], name=attrs.get('name', getattr(self.instance, 'name', '')),
                              metric_keys=attrs.get('metric_keys', getattr(self.instance, 'metric_keys', [])))
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class MetricRequestCreateSerializer(serializers.Serializer):
    provider_slug = serializers.CharField(max_length=150)
    provider = serializers.CharField(max_length=40, default='catapult_openfield')
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class MetricRequestSerializer(serializers.ModelSerializer):
    requested_by = serializers.SerializerMethodField()
    metric_key = serializers.CharField(source='metric.key', default=None, read_only=True)

    class Meta:
        model = MetricRequest
        fields = ('id', 'provider', 'provider_slug', 'provider_name', 'note', 'status', 'requested_by',
                  'created_at', 'decided_at', 'metric_key')

    def get_requested_by(self, obj):
        u = obj.requested_by
        return (u.full_name or u.email) if u else None
