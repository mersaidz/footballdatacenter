from rest_framework import serializers

from clubs.models import Club, Player, StaffMembership, Team
from football.models import Event, Match, MatchAppearance, PlayerAvailability, PlayerLoad
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
            'player_load', 'rpe', 'quality_flags', 'extra_metrics',
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
