"""
Read views that power the web app: squad status, session history and detail,
microcycle, a player's load history. Values for the chosen metric set come from
the same definitions as /loads/, so every screen agrees.
"""
from datetime import date

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from clubs.models import Player
from clubs.permissions import Cap
from football.models import ActivityPeriod, PeriodLoad, PlayerLoad, TrainingSession
from football.services import performance as perf
from metrics.models import MetricDefinition
from metrics.services import CORE_METRICS, ensure_core_metrics, value_of

from wellness.services import rpe_for_session

from .permissions import ClubScopedMixin, HasClubCapability
from .views import resolve_metric_set


def _date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({'date': _('Use YYYY-MM-DD.')})


def _team(view):
    team = perf.own_team(view.club)
    if team is None:
        raise NotFound(_('The club has no own team yet: run a sync first.'))
    return team


class _LoadView(ClubScopedMixin, generics.GenericAPIView):
    permission_classes = (HasClubCapability,)
    required_cap = Cap.VIEW_PHYSICAL_LOAD


class SquadStatusView(_LoadView):
    """GET /clubs/{id}/squad-status/?date=YYYY-MM-DD — readiness traffic light (default: day after the last session)."""

    def get(self, request, club_id=None):
        data = perf.squad_status(_team(self), _date(request.query_params.get('date')))
        if not self.has_cap(Cap.VIEW_WELLNESS_DETAILS):          # coaches: how he feels overall, not what he said
            for row in data['players']:
                if row.get('wellness'):
                    row['wellness'] = {k: row['wellness'][k] for k in ('level', 'total', 'z', 'normal')}
                for r in row['reasons']:
                    r.pop('flags', None)
        return Response(data)


class MicrocycleView(_LoadView):
    """GET /clubs/{id}/microcycle/?match=<session id> — the week into a match (default: the latest)."""

    def get(self, request, club_id=None):
        team = _team(self)
        match = None
        if mid := request.query_params.get('match'):
            match = get_object_or_404(TrainingSession, club=self.club, team=team, pk=mid, session_type='match')
        return Response(perf.microcycle(team, match))


def metric_columns(club, user, params):
    ensure_core_metrics(club)
    ms = resolve_metric_set(club, user, None if params.get('metric_set') in (None, '', 'default') else params.get('metric_set'))
    keys = ms.metric_keys if ms else [m['key'] for m in CORE_METRICS]
    defs = {d.key: d for d in MetricDefinition.objects.filter(club=club, key__in=keys)}
    ordered = [defs[k] for k in keys if k in defs]
    display = params.get('display') or (ms.display if ms else 'absolute')
    meta = {'id': ms.pk if ms else None, 'name': ms.name if ms else 'Core', 'display': display,
            'metrics': [{'key': d.key, 'label': str(d.label), 'short_label': d.short_label or str(d.label), 'unit': d.unit,
                         'category': d.category, 'aggregation': d.aggregation} for d in ordered]}
    return ordered, display, meta


class SessionViewSet(ClubScopedMixin, viewsets.ViewSet):
    """
    GET /clubs/{id}/sessions/?from=&to=&type=match|training   history, newest first
    GET /clubs/{id}/sessions/{sid}/?metric_set=&display=        one session: periods and every player's values
    """
    permission_classes = (HasClubCapability,)
    required_cap = Cap.VIEW_PHYSICAL_LOAD

    def list(self, request, club_id=None):
        p = request.query_params
        return Response(perf.session_summaries(_team(self), _date(p.get('from')), _date(p.get('to')), p.get('type')))

    def retrieve(self, request, club_id=None, pk=None):
        session = get_object_or_404(TrainingSession, club=self.club, pk=pk)
        defs, display, meta = metric_columns(self.club, request.user, request.query_params)
        periods = list(ActivityPeriod.objects.filter(training_session=session).order_by('start'))
        by_player_period = {}
        for pl in PeriodLoad.objects.filter(period__in=periods).select_related('period'):
            by_player_period.setdefault(pl.player_id, {})[pl.period_id] = {d.key: value_of(pl, d, display) for d in defs}
        rpe = rpe_for_session(session)
        rows = []
        for load in PlayerLoad.objects.filter(training_session=session).select_related('player').order_by('-duration_min'):
            p = load.player
            rows.append({
                'player_id': p.pk, 'name': p.display_name, 'shirt_number': p.shirt_number, 'position': p.primary_position,
                'participation': load.participation, 'flagged': bool(load.quality_flags), 'load_basis': load.load_basis,
                'values': {d.key: value_of(load, d, display) for d in defs},
                'periods': by_player_period.get(p.pk, {}),
                'rpe': rpe.get(p.pk, {}).get('rpe'), 'srpe': rpe.get(p.pk, {}).get('srpe'),
            })
        neighbours = TrainingSession.objects.filter(club=self.club, team=session.team)
        prev = neighbours.filter(start__lt=session.start).order_by('-start').first()
        nxt = neighbours.filter(start__gt=session.start).order_by('start').first()
        return Response({
            'session': {'id': session.pk, 'date': session.start.date().isoformat(), 'start': session.start.isoformat(),
                        'end': session.end.isoformat() if session.end else None, 'name': session.name,
                        'md': session.md_code, 'type': session.session_type,
                        'previous_id': prev.pk if prev else None, 'next_id': nxt.pk if nxt else None},
            'metric_set': meta,
            'periods': [{'id': pr.id, 'name': pr.name, 'role': pr.role, 'role_label': str(pr.get_role_display()),
                         'minutes': round(pr.duration_min, 1) if pr.duration_min is not None else None,
                         'counts_as_play': pr.role in ActivityPeriod.PLAYING_ROLES} for pr in periods],
            'rows': rows,
            'rpe': {'answered': sum(1 for r in rows if r['rpe'] is not None), 'squad': len(rows),
                    'mean': round(sum(r['rpe'] for r in rows if r['rpe'] is not None) / max(1, sum(1 for r in rows if r['rpe'] is not None)), 1)
                    if any(r['rpe'] is not None for r in rows) else None},
        })


class PlayerHistoryView(_LoadView):
    """GET /clubs/{id}/players/{pid}/load-history/?to=YYYY-MM-DD — daily load, ACWR, MD profile, match log."""

    def get(self, request, club_id=None, pk=None):
        player = get_object_or_404(Player, club=self.club, pk=pk)
        return Response({'player': {'id': player.pk, 'name': player.display_name, 'shirt_number': player.shirt_number,
                                    'position': player.primary_position, 'foot': player.preferred_foot},
                         **perf.player_history(player, _date(request.query_params.get('to')))})
