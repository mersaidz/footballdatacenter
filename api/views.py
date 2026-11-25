from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from clubs.models import Player, StaffMembership, Team
from clubs.permissions import Cap
from core.models import AuditLog
from core.services.audit import log_event
from football.models import ActivityPeriod, Event, Match, PeriodRoleMapping, PlayerAvailability, PlayerLoad
from football.services.loads import is_match_context, recompute_loads
from providers.models import ExternalIdentity

from . import serializers as s
from .permissions import ClubScopedMixin, HasClubCapability


class MyClubsView(generics.ListAPIView):
    """GET /api/clubs/ — the clubs I work for and my role in each."""
    serializer_class = s.MyClubSerializer
    pagination_class = None

    def get_queryset(self):
        return StaffMembership.objects.filter(user=self.request.user, is_active=True).select_related('club')


class ClubReadOnlyViewSet(ClubScopedMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (HasClubCapability,)
    model = None

    def get_queryset(self):
        return self.model.objects.filter(club=self.club)


class TeamViewSet(ClubReadOnlyViewSet):
    model = Team
    serializer_class = s.TeamSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('own') == 'true':
            qs = qs.filter(is_own=True)
        return qs


class PlayerViewSet(ClubReadOnlyViewSet):
    model = Player
    serializer_class = s.PlayerSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related('current_team')
        params = self.request.query_params
        if team := params.get('team'):
            qs = qs.filter(current_team_id=team)
        if q := params.get('search'):
            qs = qs.filter(full_name__icontains=q) | qs.filter(known_name__icontains=q)
        return qs


class MatchViewSet(ClubReadOnlyViewSet):
    model = Match
    serializer_class = s.MatchSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related('home_team', 'away_team', 'season__competition')
        if team := self.request.query_params.get('team'):
            qs = qs.filter(home_team_id=team) | qs.filter(away_team_id=team)
        return qs

    @action(detail=True)
    def lineups(self, request, club_id=None, pk=None):
        match = self.get_object()
        apps = match.appearances.select_related('player').order_by('team_id', '-started', 'minute_on')
        return Response(s.AppearanceSerializer(apps, many=True).data)

    @action(detail=True)
    def events(self, request, club_id=None, pk=None):
        match = self.get_object()
        qs = Event.objects.filter(match=match).select_related('player').order_by('sequence')
        params = request.query_params
        if t := params.get('type'):
            qs = qs.filter(event_type__in=t.split(','))
        if player := params.get('player'):
            qs = qs.filter(player_id=player)
        if team := params.get('team'):
            qs = qs.filter(team_id=team)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(s.EventSerializer(page, many=True).data)


class PlayerLoadViewSet(ClubReadOnlyViewSet):
    model = PlayerLoad
    serializer_class = s.PlayerLoadSerializer
    required_cap = Cap.VIEW_PHYSICAL_LOAD

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for key in ('player', 'match', 'training_session'):
            if val := params.get(key):
                qs = qs.filter(**{f'{key}_id': val})
        if params.get('exclude_flagged') == 'true':
            qs = qs.filter(quality_flags=[])
        if part := params.get('participation'):
            qs = qs.filter(participation__in=part.split(','))
        return qs

    def list(self, request, *args, **kwargs):
        """?metric_set=<id|default> adds `values`: the set's metrics in its display mode (?display= overrides)."""
        response = super().list(request, *args, **kwargs)
        set_param = request.query_params.get('metric_set')
        if not set_param:
            return response
        ms = resolve_metric_set(self.club, request.user, None if set_param == 'default' else set_param)
        ensure_core_metrics(self.club)
        keys = ms.metric_keys if ms else [m['key'] for m in CORE_METRICS]
        display = request.query_params.get('display') or (ms.display if ms else 'absolute')
        defs = {d.key: d for d in MetricDefinition.objects.filter(club=self.club, key__in=keys)}
        ordered = [defs[k] for k in keys if k in defs]
        by_id = {l.pk: l for l in PlayerLoad.objects.filter(pk__in=[r['id'] for r in response.data['results']])}
        for row in response.data['results']:
            load = by_id[row['id']]
            row['values'] = [{'key': d.key, 'label': d.short_label or d.label, 'unit': d.unit,
                              'value': value_of(load, d, display)} for d in ordered]
        response.data['metric_set'] = {'id': ms.pk if ms else None, 'name': ms.name if ms else 'Core',
                                       'display': display}
        return response


class AvailabilityViewSet(ClubScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Coaches: status only. Medical staff: full record (diagnosis, notes),
    and every full-record read is audited.
    """
    permission_classes = (HasClubCapability,)
    required_cap = Cap.VIEW_AVAILABILITY
    write_cap = Cap.EDIT_MEDICAL

    def get_queryset(self):
        qs = PlayerAvailability.objects.filter(club=self.club).select_related('player')
        if player := self.request.query_params.get('player'):
            qs = qs.filter(player_id=player)
        if self.request.query_params.get('current') == 'true':
            qs = qs.filter(actual_return__isnull=True)
        return qs

    def get_serializer_class(self):
        if self.has_cap(Cap.VIEW_MEDICAL_DETAILS):
            return s.AvailabilityMedicalSerializer
        return s.AvailabilityStatusSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.membership is not None:
            ctx['club'] = self.club
        return ctx

    def _audit_medical_read(self, ids):
        if self.has_cap(Cap.VIEW_MEDICAL_DETAILS) and ids:
            log_event(action=AuditLog.Action.MEDICAL_RECORD_VIEWED, request=self.request, club=self.club,
                      extra_info={'availability_ids': list(ids)[:200]})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        results = response.data['results'] if isinstance(response.data, dict) else response.data
        self._audit_medical_read([r['id'] for r in results])
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._audit_medical_read([response.data['id']])
        return response

    def perform_create(self, serializer):
        obj = serializer.save(club=self.club, created_by=self.request.user)
        log_event(action=AuditLog.Action.MEDICAL_RECORD_CHANGED, request=self.request, club=self.club,
                  extra_info={'availability_id': obj.pk, 'op': 'create'})

    def perform_update(self, serializer):
        obj = serializer.save()
        log_event(action=AuditLog.Action.MEDICAL_RECORD_CHANGED, request=self.request, club=self.club,
                  extra_info={'availability_id': obj.pk, 'op': 'update', 'fields': sorted(serializer.validated_data)})


class ExternalIdentityViewSet(ClubScopedMixin, viewsets.ReadOnlyModelViewSet):
    """
    The review queue for cross-provider links.
    GET  ?status=suggested          — what an analyst needs to check
    POST {id}/confirm/              — "yes, same player"
    POST {id}/reject/               — "no, different player": a new Player is created and relinked
    """
    permission_classes = (HasClubCapability,)
    serializer_class = s.ExternalIdentitySerializer
    required_cap = Cap.MANAGE_IDENTITIES
    write_cap = Cap.MANAGE_IDENTITIES

    def get_queryset(self):
        qs = ExternalIdentity.objects.filter(club=self.club).select_related('content_type')
        params = self.request.query_params
        if st := params.get('status'):
            qs = qs.filter(status=st)
        if et := params.get('entity_type'):
            qs = qs.filter(entity_type=et)
        if pr := params.get('provider'):
            qs = qs.filter(provider=pr)
        return qs.order_by('confidence', 'id')

    def _review(self, identity):
        identity.status = ExternalIdentity.Status.CONFIRMED
        identity.reviewed_by = self.request.user
        identity.reviewed_at = timezone.now()

    @action(detail=True, methods=['post'])
    def confirm(self, request, club_id=None, pk=None):
        identity = self.get_object()
        self._review(identity)
        identity.method = ExternalIdentity.Method.MANUAL
        identity.save()
        log_event(action=AuditLog.Action.IDENTITY_CONFIRMED, request=request, club=self.club,
                  provider=identity.provider, extra_info={'identity_id': identity.pk})
        return Response(self.get_serializer(identity).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, club_id=None, pk=None):
        identity = self.get_object()
        if identity.entity_type != ExternalIdentity.EntityType.PLAYER:
            raise ValidationError('Only player links can be rejected in v1.')
        old_target = identity.object_id
        with transaction.atomic():
            old_player = get_object_or_404(Player, pk=old_target, club=self.club)
            new_player = Player.objects.create(
                club=self.club,
                full_name=identity.external_name or old_player.full_name,
                known_name=identity.external_meta.get('known_name', ''),
                current_team=old_player.current_team,
            )
            # Move this provider's rows (events, appearances) to the new player.
            Event.objects.filter(club=self.club, player_id=old_target, provider=identity.provider) \
                .update(player=new_player)
            for app in old_player.appearances.filter(match__events__provider=identity.provider).distinct():
                app.player = new_player
                app.save(update_fields=['player'])
            identity.object_id = new_player.pk
            identity.method = ExternalIdentity.Method.MANUAL
            self._review(identity)
            identity.save()
        log_event(action=AuditLog.Action.IDENTITY_REJECTED, request=request, club=self.club,
                  provider=identity.provider,
                  extra_info={'identity_id': identity.pk, 'old_player': old_target, 'new_player': new_player.pk})
        return Response(self.get_serializer(identity).data, status=status.HTTP_200_OK)


class ActivityPeriodViewSet(ClubScopedMixin, viewsets.ReadOnlyModelViewSet):
    """
    Periods inside sessions and matches, with their resolved role.
    GET  ?needs_review=true          — periods nobody could classify (shown to analysts / S&C)
    POST {id}/assign_role/ {role, remember}
         remember=true (default) teaches the club's vocabulary: every period with the same
         name gets the role, now and in future syncs; match loads are recomputed.
    """
    permission_classes = (HasClubCapability,)
    serializer_class = s.ActivityPeriodSerializer
    required_cap = Cap.VIEW_PHYSICAL_LOAD
    write_cap = Cap.MANAGE_PERIODS

    def get_queryset(self):
        qs = ActivityPeriod.objects.filter(club=self.club).select_related('training_session', 'match')
        params = self.request.query_params
        if params.get('needs_review') == 'true':
            qs = qs.filter(role=ActivityPeriod.Role.UNKNOWN)
        if role := params.get('role'):
            qs = qs.filter(role=role)
        if sid := params.get('training_session'):
            qs = qs.filter(training_session_id=sid)
        if mid := params.get('match'):
            qs = qs.filter(match_id=mid)
        return qs.order_by('start')

    @action(detail=True, methods=['post'])
    def assign_role(self, request, club_id=None, pk=None):
        period = self.get_object()
        body = s.AssignRoleSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        role, remember = body.validated_data['role'], body.validated_data['remember']
        with transaction.atomic():
            period.role, period.role_source, period.role_confidence = role, ActivityPeriod.Source.MANUAL, 1
            period.save(update_fields=['role', 'role_source', 'role_confidence', 'updated_at'])
            touched = [period]
            if remember:
                PeriodRoleMapping.objects.update_or_create(
                    club=self.club, normalized_name=period.normalized_name,
                    defaults={'role': role, 'created_by': request.user},
                )
                others = (ActivityPeriod.objects.filter(club=self.club, normalized_name=period.normalized_name)
                          .exclude(pk=period.pk).exclude(role_source=ActivityPeriod.Source.MANUAL))
                for other in others:
                    other.role, other.role_source, other.role_confidence = role, ActivityPeriod.Source.CLUB, '0.95'
                    other.save(update_fields=['role', 'role_source', 'role_confidence', 'updated_at'])
                    touched.append(other)
            contexts = {(p.match_id, p.training_session_id): p for p in touched}
            recomputed = 0
            for p in contexts.values():
                if is_match_context(p.match, p.training_session):
                    recomputed += recompute_loads(match=p.match, training_session=p.training_session)
        log_event(action=AuditLog.Action.PERIOD_ROLE_CHANGED, request=request, club=self.club,
                  extra_info={'period_id': period.pk, 'name': period.name, 'role': role, 'remember': remember,
                              'periods_updated': len(touched), 'loads_recomputed': recomputed})
        data = self.get_serializer(period).data
        return Response({**data, 'periods_updated': len(touched), 'loads_recomputed': recomputed})


# --- metrics ---------------------------------------------------------------------------------

from rest_framework.exceptions import PermissionDenied  # noqa: E402

from clubs.permissions import has_cap  # noqa: E402
from metrics.models import MetricDefinition, MetricSet, ProviderMetric  # noqa: E402
from metrics.services import (  # noqa: E402
    CORE_METRICS, enable_from_catalogue, ensure_core_metrics, search_catalogue, value_of,
)


def resolve_metric_set(club, user, set_id=None) -> MetricSet | None:
    """Explicit set → my default → club default → first club set → None (core metrics)."""
    qs = MetricSet.objects.filter(club=club).filter(Q(owner__isnull=True) | Q(owner=user))
    if set_id:
        return qs.filter(pk=set_id).first()
    return (qs.filter(owner=user, is_default=True).first()
            or qs.filter(owner__isnull=True, is_default=True).first()
            or qs.filter(owner__isnull=True).order_by('pk').first())


class MetricCatalogueView(ClubScopedMixin, generics.ListAPIView):
    """GET /metrics/catalogue/?search=multidirectional — every parameter the provider offers this club."""
    permission_classes = (HasClubCapability,)
    serializer_class = s.CatalogueEntrySerializer
    required_cap = Cap.VIEW_PHYSICAL_LOAD

    def get_queryset(self):
        q = self.request.query_params.get('search', '').strip()
        qs = search_catalogue(self.club, q) if q else ProviderMetric.objects.filter(club=self.club)
        return qs.order_by('name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.membership is not None:
            ctx['tracked'] = {(d.provider, d.provider_slug): d.key for d in
                              MetricDefinition.objects.filter(club=self.club, enabled=True).exclude(provider_slug='')}
        return ctx


class MetricDefinitionViewSet(ClubScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                              mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    The club's metrics. POST {provider_slug} starts tracking a catalogue parameter
    (it arrives on the next sync); PATCH fixes label, unit, category or aggregation.
    """
    permission_classes = (HasClubCapability,)
    serializer_class = s.MetricDefinitionSerializer
    required_cap = Cap.VIEW_PHYSICAL_LOAD
    write_cap = Cap.MANAGE_METRICS
    pagination_class = None

    def get_queryset(self):
        if self.membership is not None:
            ensure_core_metrics(self.club)
        qs = MetricDefinition.objects.filter(club=self.club)
        if cat := self.request.query_params.get('category'):
            qs = qs.filter(category=cat)
        return qs

    def create(self, request, club_id=None):
        body = s.EnableMetricSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        pm = ProviderMetric.objects.filter(club=self.club, provider=data.pop('provider'),
                                           slug=data.pop('provider_slug')).first()
        if pm is None:
            raise ValidationError({'provider_slug': 'Not in this club\'s provider catalogue (run a sync first).'})
        md = enable_from_catalogue(self.club, pm, user=request.user, **data)
        return Response(self.get_serializer(md).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.is_core and 'enabled' in serializer.validated_data:
            serializer.validated_data.pop('enabled')     # core metrics are always available
        serializer.save()


class MetricSetViewSet(ClubScopedMixin, viewsets.ModelViewSet):
    """
    Metric sets: club-wide (published by S&C / analysts) and personal (anyone with load access).
    GET  default/            the set this user sees unless they pick another
    POST {id}/make_default/  becomes my default (club default for club sets, MANAGE_METRICS only)
    """
    permission_classes = (HasClubCapability,)
    serializer_class = s.MetricSetSerializer
    required_cap = Cap.VIEW_PHYSICAL_LOAD
    write_cap = Cap.VIEW_PHYSICAL_LOAD          # personal sets; club scope checked below
    pagination_class = None

    def get_queryset(self):
        return MetricSet.objects.filter(club=self.club).filter(Q(owner__isnull=True) | Q(owner=self.request.user))

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.membership is not None:
            ctx['club'] = self.club
        return ctx

    def _check_can_edit(self, metric_set):
        if metric_set.owner_id is None and not self.has_cap(Cap.MANAGE_METRICS):
            raise PermissionDenied('Only S&C, analysts and club admins change club-wide metric sets.')
        if metric_set.owner_id not in (None, self.request.user.pk):
            raise PermissionDenied

    def perform_create(self, serializer):
        scope = serializer.validated_data.pop('scope', 'personal')
        if scope == 'club' and not self.has_cap(Cap.MANAGE_METRICS):
            raise PermissionDenied('Only S&C, analysts and club admins publish club-wide metric sets.')
        is_default = serializer.validated_data.pop('is_default', False)
        obj = serializer.save(club=self.club, owner=None if scope == 'club' else self.request.user)
        if is_default:
            self._make_default(obj)

    def perform_update(self, serializer):
        self._check_can_edit(serializer.instance)
        serializer.validated_data.pop('scope', None)
        is_default = serializer.validated_data.pop('is_default', None)
        obj = serializer.save()
        if is_default:
            self._make_default(obj)

    def perform_destroy(self, instance):
        self._check_can_edit(instance)
        instance.delete()

    def _make_default(self, obj):
        with transaction.atomic():
            MetricSet.objects.filter(club=self.club, owner_id=obj.owner_id, is_default=True) \
                .exclude(pk=obj.pk).update(is_default=False)
            obj.is_default = True
            obj.save(update_fields=['is_default', 'updated_at'])

    @action(detail=False)
    def default(self, request, club_id=None):
        ms = resolve_metric_set(self.club, request.user)
        if ms is None:
            ensure_core_metrics(self.club)
            return Response({'id': None, 'name': 'Core', 'display': 'absolute', 'is_default': True, 'is_club': True,
                             'metric_keys': [m['key'] for m in CORE_METRICS],
                             'metrics': [{'key': m['key'], 'label': m['label'], 'short_label': m['short_label'],
                                          'unit': m['unit'], 'category': m['category']} for m in CORE_METRICS]})
        return Response(self.get_serializer(ms).data)

    @action(detail=True, methods=['post'])
    def make_default(self, request, club_id=None, pk=None):
        ms = self.get_object()
        self._check_can_edit(ms)
        self._make_default(ms)
        return Response(self.get_serializer(ms).data)
