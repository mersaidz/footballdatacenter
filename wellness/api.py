"""
Wellness endpoints.

Player (no account — the personal link is the credential):
  GET  /api/p/<token>/                 who he is, today's check-in, sessions he can rate
  POST /api/p/<token>/checkin/         morning questionnaire (today or yesterday; re-sending edits it)
  POST /api/p/<token>/rpe/             how hard was today's session, 0–10

Staff (club-scoped):
  GET  /clubs/{id}/wellness/?date=     the squad's answers. Coaches: level + total. S&C/medical: every answer.
  POST /clubs/{id}/wellness/           entry on a player's behalf (after talking to him)
  POST /clubs/{id}/rpe/                RPE on a player's behalf
  GET  /clubs/{id}/players/{pid}/wellness/?days=28
  GET  /clubs/{id}/player-links/       who has a link, when it was last used
  POST /clubs/{id}/player-links/       {player_id} → new link (shown once); the old one stops working
  POST /clubs/{id}/player-links/{pid}/revoke/
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from api.permissions import ClubScopedMixin, HasClubCapability
from clubs.models import Player
from clubs.permissions import Cap
from football.models import TrainingSession
from football.services import performance as perf

from . import services as svc
from .models import ITEMS, SORE_AREAS, PlayerLink, RpeEntry, Source, WellnessCheckin


# ---------- shared validation ----------

class CheckinIn(serializers.Serializer):
    date = serializers.DateField(required=False)
    sleep_quality = serializers.IntegerField(min_value=1, max_value=5)
    energy = serializers.IntegerField(min_value=1, max_value=5)
    soreness = serializers.IntegerField(min_value=1, max_value=5)
    stress = serializers.IntegerField(min_value=1, max_value=5)
    mood = serializers.IntegerField(min_value=1, max_value=5)
    sleep_hours = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=16, required=False, allow_null=True)
    sore_areas = serializers.ListField(child=serializers.ChoiceField(choices=SORE_AREAS), required=False, max_length=len(SORE_AREAS))
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class RpeIn(serializers.Serializer):
    date = serializers.DateField(required=False)
    session_id = serializers.IntegerField(required=False, allow_null=True)
    rpe = serializers.IntegerField(min_value=0, max_value=10)


def _save_checkin(player, data, source, user=None) -> WellnessCheckin:
    day = data.pop('date')
    data['sore_areas'] = sorted(set(data.get('sore_areas') or [])) if data.get('soreness', 5) < 5 else []
    obj, _created = WellnessCheckin.objects.update_or_create(
        player=player, date=day, defaults={**data, 'club': player.club, 'source': source, 'entered_by': user})
    return obj


def _save_rpe(player, data, source, user=None) -> RpeEntry:
    session = None
    if sid := data.get('session_id'):
        session = TrainingSession.objects.filter(club=player.club, pk=sid).first()
        if session is None:
            raise ValidationError({'session_id': _('Unknown session.')})
    day = session.start.date() if session else data['date']
    obj, _created = RpeEntry.objects.update_or_create(
        player=player, date=day, defaults={'club': player.club, 'rpe': data['rpe'], 'session': session,
                                           'source': source, 'entered_by': user})
    svc.link_rpe(obj)
    return obj


def _player_window(day, today):
    if not (today - timedelta(1) <= day <= today):
        raise ValidationError({'date': _('You can answer for today or yesterday only.')})


# ---------- player ----------

class PlayerThrottle(AnonRateThrottle):
    rate = '60/min'


class _PlayerView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (PlayerThrottle,)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.link = PlayerLink.resolve(kwargs.get('token'))
        if self.link is None:
            raise NotFound(_('This link no longer works. Ask your S&C coach for a new one.'))
        lang = request.query_params.get('lang')       # otherwise the phone's language (LocaleMiddleware)
        if lang in dict(settings.LANGUAGES):
            translation.activate(lang)
        PlayerLink.objects.filter(pk=self.link.pk).update(last_used_at=timezone.now())

    @property
    def player(self) -> Player:
        return self.link.player


class PlayerHomeView(_PlayerView):
    def get(self, request, token):
        p, today = self.player, timezone.localdate()
        checkins = {c.date: c for c in WellnessCheckin.objects.filter(player=p, date__gte=today - timedelta(1))}
        rpe = {e.date: e for e in RpeEntry.objects.filter(player=p, date__gte=today - timedelta(2))}
        sessions = [{'id': s.pk, 'date': s.start.date().isoformat(), 'name': s.name, 'md': s.md_code, 'type': s.session_type,
                     'rpe': rpe[s.start.date()].rpe if s.start.date() in rpe else None}
                    for s in svc.recent_sessions(p, today)]
        return Response({
            'player': {'name': p.display_name, 'first_name': (p.display_name or '').split(' ')[0], 'shirt_number': p.shirt_number,
                       'club': p.club.name},
            'today': today.isoformat(),
            'checkin': svc.checkin_detail(checkins[today]) if today in checkins else None,
            'yesterday_done': (today - timedelta(1)) in checkins,
            'rpe_today': rpe[today].rpe if today in rpe else None,
            'sessions': sessions,
            'items': ITEMS, 'sore_areas': SORE_AREAS,
        })


class PlayerManifestView(_PlayerView):
    """So "Add to Home Screen" opens this player's page like an app."""

    def get(self, request, token):
        name = self.player.display_name.split(' ')[0] if self.player.display_name else 'FDC'
        data = {'name': f'FDC · {name}', 'short_name': 'FDC', 'start_url': f'/p/{token}', 'scope': f'/p/{token}',
                'display': 'standalone', 'background_color': '#0a0a0a', 'theme_color': '#0a0a0a',
                'icons': [{'src': f'{settings.STATIC_URL}icon-{n}.png', 'sizes': f'{n}x{n}', 'type': 'image/png'} for n in (192, 512)]}
        return Response(data, content_type='application/manifest+json')


class PlayerCheckinView(_PlayerView):
    def post(self, request, token):
        s = CheckinIn(data=request.data); s.is_valid(raise_exception=True)
        data, today = dict(s.validated_data), timezone.localdate()
        data.setdefault('date', today)
        _player_window(data['date'], today)
        c = _save_checkin(self.player, data, Source.PLAYER)
        return Response({'ok': True, 'date': c.date.isoformat()}, status=status.HTTP_201_CREATED)


class PlayerRpeView(_PlayerView):
    def post(self, request, token):
        s = RpeIn(data=request.data); s.is_valid(raise_exception=True)
        data, today = dict(s.validated_data), timezone.localdate()
        data.setdefault('date', today)
        if sid := data.get('session_id'):
            if not any(x.pk == sid for x in svc.recent_sessions(self.player, today)):
                raise ValidationError({'session_id': _('You can rate the last two days only.')})
        else:
            _player_window(data['date'], today)
        e = _save_rpe(self.player, data, Source.PLAYER)
        return Response({'ok': True, 'date': e.date.isoformat(), 'rpe': e.rpe}, status=status.HTTP_201_CREATED)


# ---------- staff ----------

class _StaffView(ClubScopedMixin, generics.GenericAPIView):
    permission_classes = (HasClubCapability,)
    required_cap = Cap.VIEW_PHYSICAL_LOAD
    write_cap = Cap.VIEW_WELLNESS_DETAILS

    @property
    def details(self) -> bool:
        return self.has_cap(Cap.VIEW_WELLNESS_DETAILS)

    def summary(self, item: dict | None) -> dict | None:
        if item is None or self.details:
            return item
        return {k: item[k] for k in ('date', 'total', 'z', 'level', 'normal')}

    def player(self, pid) -> Player:
        return get_object_or_404(Player, club=self.club, pk=pid)


def _day(value, default):
    from api.views_app import _date
    return _date(value) or default


class SquadWellnessView(_StaffView):
    def get(self, request, club_id=None):
        team = perf.own_team(self.club)
        players = list(Player.objects.filter(club=self.club, current_team=team)) if team else []
        day = _day(request.query_params.get('date'), svc.default_day(self.club, timezone.localdate()))
        answers = svc.day_summary(players, day)
        rows = [{'player_id': p.pk, 'name': p.display_name, 'shirt_number': p.shirt_number, 'position': p.primary_position,
                 'answer': self.summary(answers.get(p.pk))} for p in players]
        order = {'very_low': 0, 'low': 1, 'ok': 2}
        rows.sort(key=lambda r: (order[r['answer']['level']] if r['answer'] else 3, r['shirt_number'] or 99))
        levels = [a['level'] for a in answers.values()]
        return Response({'date': day.isoformat(), 'details': self.details, 'answered': len(answers), 'squad': len(players),
                         'low': levels.count('low'), 'very_low': levels.count('very_low'), 'rows': rows})

    def post(self, request, club_id=None):
        player = self.player(request.data.get('player_id'))
        s = CheckinIn(data=request.data); s.is_valid(raise_exception=True)
        data = dict(s.validated_data); data.setdefault('date', timezone.localdate())
        c = _save_checkin(player, data, Source.STAFF, request.user)
        return Response({'ok': True, 'date': c.date.isoformat()}, status=status.HTTP_201_CREATED)


class StaffRpeView(_StaffView):
    def post(self, request, club_id=None):
        player = self.player(request.data.get('player_id'))
        s = RpeIn(data=request.data); s.is_valid(raise_exception=True)
        data = dict(s.validated_data); data.setdefault('date', timezone.localdate())
        e = _save_rpe(player, data, Source.STAFF, request.user)
        return Response({'ok': True, 'date': e.date.isoformat(), 'rpe': e.rpe}, status=status.HTTP_201_CREATED)


class PlayerWellnessView(_StaffView):
    def get(self, request, club_id=None, pk=None):
        player = self.player(pk)
        try:
            days = max(7, min(int(request.query_params.get('days', 28)), 180))
        except ValueError:
            raise ValidationError({'days': _('Use a number of days.')})
        end = _day(request.query_params.get('to'), svc.default_day(self.club, timezone.localdate()))
        start = end - timedelta(days - 1)
        checkins = list(WellnessCheckin.objects.filter(player=player, date__gte=start, date__lte=end).order_by('date'))
        history = []
        for c in checkins:
            item = {**svc.assess(c, svc.baseline(player, c.date)), **svc.checkin_detail(c)}
            history.append(self.summary(item))
        rpe = []
        for e in RpeEntry.objects.filter(player=player, date__gte=start, date__lte=end).select_related('session').order_by('date'):
            svc.link_rpe(e)
            mins = None
            if e.session_id:
                load = e.session.loads.filter(player=player).first()
                mins = float(load.duration_min) if load and load.duration_min is not None else None
            rpe.append({'date': e.date.isoformat(), 'rpe': e.rpe, 'minutes': round(mins) if mins else None,
                        'srpe': round(e.rpe * mins) if mins else None, 'session_id': e.session_id,
                        'session_name': e.session.name if e.session_id else None, 'source': e.source})
        base = svc.baseline(player, end + timedelta(1))
        return Response({
            'from': start.isoformat(), 'to': end.isoformat(), 'details': self.details,
            'baseline': ({k: v for k, v in base.items()} if self.details else {'n': base['n'], 'total': base['total']}) if base else None,
            'latest': history[-1] if history else None,
            'history': history, 'rpe': rpe,
            'answered_days': len(checkins), 'items': ITEMS,
        })


class PlayerLinksView(_StaffView):
    required_cap = Cap.VIEW_WELLNESS_DETAILS

    def get(self, request, club_id=None):
        team = perf.own_team(self.club)
        players = Player.objects.filter(club=self.club, current_team=team).order_by('shirt_number', 'full_name') if team else []
        links = {lk.player_id: lk for lk in PlayerLink.objects.filter(club=self.club, revoked_at__isnull=True)}
        last = {}
        for c in WellnessCheckin.objects.filter(club=self.club, source=Source.PLAYER).order_by('date'):
            last[c.player_id] = c.date.isoformat()
        return Response([{'player_id': p.pk, 'name': p.display_name, 'shirt_number': p.shirt_number, 'position': p.primary_position,
                          'active': p.pk in links,
                          'created_at': links[p.pk].created_at.isoformat() if p.pk in links else None,
                          'last_used_at': links[p.pk].last_used_at.isoformat() if p.pk in links and links[p.pk].last_used_at else None,
                          'last_answer': last.get(p.pk)} for p in players])

    def post(self, request, club_id=None):
        player = self.player(request.data.get('player_id'))
        with transaction.atomic():
            _link, raw = PlayerLink.issue(player, request.user)
        return Response({'player_id': player.pk, 'token': raw, 'path': f'/p/{raw}'}, status=status.HTTP_201_CREATED)


class RevokePlayerLinkView(_StaffView):
    required_cap = Cap.VIEW_WELLNESS_DETAILS

    def post(self, request, club_id=None, pk=None):
        player = self.player(pk)
        n = PlayerLink.objects.filter(player=player, revoked_at__isnull=True).update(revoked_at=timezone.now())
        return Response({'revoked': n})
