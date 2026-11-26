"""
Team and player load views built from PlayerLoad: daily totals, EWMA ACWR,
squad readiness, match demand, microcycle and session history.

Everything is computed per request from stored loads (a squad-season is a few
thousand rows), so a re-synced session or a corrected period changes every view
at once. Reasons are returned as codes + numbers, the UI words them in its language.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Q

from clubs.models import Player, Team
from football.models import PlayerLoad, TrainingSession

METRICS = ('dist', 'hsr', 'spr', 'acc', 'dec', 'pl')
FIELD = {'dist': 'total_distance_m', 'hsr': 'hsr_distance_m', 'spr': 'sprint_distance_m', 'acc': 'accelerations',
         'dec': 'decelerations', 'pl': 'player_load'}
LAMBDA_ACUTE, LAMBDA_CHRONIC = 2 / 8, 2 / 29          # EWMA, 7 and 28 days
MODIFY_ABOVE, MONITOR_ABOVE, UNDERLOAD_BELOW, LOW_HSR_BELOW = 1.5, 1.3, 0.8, 0.6
NO_SESSION_DAYS, SHORT_HISTORY_DAYS = 3, 21
MATCH_REF_MIN = 45                                    # matches that define a player's match demand


def _f(v) -> float:
    return float(v or 0)


@dataclass
class Row:
    player_id: int
    day: date
    session_id: int
    is_match: bool
    minutes: float
    participation: str
    md: str
    name: str
    vals: dict
    vmax: float | None


def team_rows(team: Team, start: date | None = None, end: date | None = None) -> list[Row]:
    qs = (PlayerLoad.objects.filter(club=team.club, training_session__team=team)
          .select_related('training_session').order_by('training_session__start'))
    if start:
        qs = qs.filter(training_session__start__date__gte=start)
    if end:
        qs = qs.filter(training_session__start__date__lte=end)
    rows = []
    for pl in qs:
        ts = pl.training_session
        rows.append(Row(pl.player_id, ts.start.date(), ts.pk, ts.session_type == 'match', _f(pl.duration_min),
                        pl.participation or '', ts.md_code or '', ts.name or '',
                        {m: _f(getattr(pl, FIELD[m])) for m in METRICS},
                        None if pl.quality_flags else (float(pl.max_speed_kmh) if pl.max_speed_kmh else None)))
    return rows


def ewma(days: list[date], daily: dict[date, float]) -> list[float | None]:
    """ACWR series. Seeded with the first week's mean so the start isn't a cold-start spike."""
    if not days:
        return []
    seed = sum(daily.get(d, 0) for d in days[:7]) / 7
    a = c = seed
    out = []
    for d in days:
        v = daily.get(d, 0)
        a = v * LAMBDA_ACUTE + (1 - LAMBDA_ACUTE) * a
        c = v * LAMBDA_CHRONIC + (1 - LAMBDA_CHRONIC) * c
        out.append(round(a / c, 2) if c > 0 else None)
    return out


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(i) for i in range((b - a).days + 1)]


def match_reference(rows: list[Row], player_id: int | None = None, exclude_gk: set[int] = frozenset()) -> dict:
    """Per-90 match demand: the player's own matches of 45'+, else the team's."""
    def per90(rs):
        mins = sum(r.minutes for r in rs)
        return {m: sum(r.vals[m] for r in rs) / mins * 90 for m in METRICS} if mins else None
    matches = [r for r in rows if r.is_match and r.minutes >= MATCH_REF_MIN]
    team = per90([r for r in matches if r.player_id not in exclude_gk])
    if player_id is None:
        return team or {}
    return per90([r for r in matches if r.player_id == player_id]) or team or {}


def goalkeepers(team: Team) -> set[int]:
    return set(Player.objects.filter(club=team.club, current_team=team, primary_position='GK').values_list('pk', flat=True))


TEAM_SESSION_MIN_PLAYERS = 5      # a session with 1-2 players (a sensor test, a rehab run) doesn't move "today"


def last_session_day(team: Team) -> date | None:
    ts = (TrainingSession.objects.filter(team=team).annotate(n=Count('loads'))
          .filter(n__gte=TEAM_SESSION_MIN_PLAYERS).order_by('-start').first()
          or TrainingSession.objects.filter(team=team).order_by('-start').first())
    return ts.start.date() if ts else None


def squad_status(team: Team, as_of: date | None = None) -> dict:
    """Readiness traffic light for every player on `as_of` (default: the day after the last session)."""
    last_day = last_session_day(team)
    if last_day is None:
        return {'as_of': None, 'players': [], 'last_match': None}
    as_of = as_of or last_day + timedelta(1)
    rows = [r for r in team_rows(team, end=as_of - timedelta(1))]
    if not rows:
        return {'as_of': as_of.isoformat(), 'players': [], 'last_match': None}
    gk = goalkeepers(team)
    days = _days(rows[0].day, as_of - timedelta(1))
    daily = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in rows:
        for m in METRICS:
            daily[r.player_id][m][r.day] += r.vals[m]
    match_days = sorted({r.day for r in rows if r.is_match})
    last_match = max(match_days) if match_days else None
    last_match_session = next((r for r in reversed(rows) if r.is_match and r.day == last_match), None)
    players = Player.objects.filter(club=team.club, current_team=team, pk__in=daily.keys())
    out = []
    for p in players:
        mine = [r for r in rows if r.player_id == p.pk]
        ad = ewma(days, daily[p.pk]['dist'])[-1]
        ah = None if p.pk in gk else ewma(days, daily[p.pk]['hsr'])[-1]
        week = sum(v for d, v in daily[p.pk]['dist'].items() if as_of - timedelta(7) <= d < as_of)
        prev = sum(v for d, v in daily[p.pk]['dist'].items() if as_of - timedelta(14) <= d < as_of - timedelta(7))
        first, last = mine[0].day, mine[-1].day
        reasons, level = [], 'ready'
        if ad is not None and ad > MODIFY_ABOVE:
            level = 'modify'; reasons.append({'code': 'acwr_dist_high', 'value': ad})
        if ah is not None and ah > MODIFY_ABOVE:
            level = 'modify'; reasons.append({'code': 'acwr_hsr_high', 'value': ah})
        if level != 'modify':
            if ad is not None and MONITOR_ABOVE < ad <= MODIFY_ABOVE:
                level = 'monitor'; reasons.append({'code': 'acwr_dist_rising', 'value': ad})
            if ad is not None and ad < UNDERLOAD_BELOW:
                level = 'monitor'; reasons.append({'code': 'underloaded', 'value': ad})
            if ah is not None and ah < LOW_HSR_BELOW:
                level = 'monitor'; reasons.append({'code': 'low_hsr', 'value': ah})
        if (as_of - last).days >= NO_SESSION_DAYS:
            reasons.insert(0, {'code': 'no_session', 'date': last.isoformat()})
            if level == 'ready':
                level = 'monitor'
        short = (as_of - first).days < SHORT_HISTORY_DAYS
        if short and level != 'ready':
            reasons.append({'code': 'short_history', 'date': first.isoformat()})
        lm = next((r for r in mine if r.is_match and r.day == last_match), None)
        out.append({
            'player_id': p.pk, 'name': p.display_name, 'shirt_number': p.shirt_number, 'position': p.primary_position,
            'level': level, 'reasons': reasons, 'acwr_distance': ad, 'acwr_hsr': ah,
            'week_distance': round(week), 'week_change_pct': round((week / prev - 1) * 100) if prev else None,
            'last_match_minutes': round(lm.minutes) if lm else 0, 'last_session': last.isoformat(),
        })
    order = {'modify': 0, 'monitor': 1, 'ready': 2}
    out.sort(key=lambda s: (order[s['level']], -(s['acwr_distance'] or 0)))
    return {
        'as_of': as_of.isoformat(),
        'days_since_match': (as_of - last_match).days if last_match else None,
        'last_match': {'session_id': last_match_session.session_id, 'date': last_match.isoformat(),
                       'name': last_match_session.name, 'md': last_match_session.md} if last_match_session else None,
        'thresholds': {'modify_above': MODIFY_ABOVE, 'monitor_above': MONITOR_ABOVE,
                       'underload_below': UNDERLOAD_BELOW, 'low_hsr_below': LOW_HSR_BELOW},
        'players': out,
    }


def player_history(player: Player, as_of: date | None = None) -> dict:
    team = player.current_team
    rows = team_rows(team, end=as_of) if team else []
    mine = [r for r in rows if r.player_id == player.pk]
    if not mine:
        return {'days': [], 'acwr_distance': [], 'acwr_hsr': [], 'md_profile': [], 'match_log': [], 'reference': {}}
    gk = goalkeepers(team)
    days = _days(mine[0].day, as_of or mine[-1].day)
    by_day = defaultdict(lambda: defaultdict(float))
    meta = {}
    for r in mine:
        for m in METRICS:
            by_day[r.day][m] += r.vals[m]
        meta[r.day] = (r.md, r.is_match or meta.get(r.day, ('', False))[1], r.session_id)
    ref = match_reference(rows, player.pk, gk)
    prof = defaultdict(list)
    for r in mine:
        if not r.is_match and r.minutes >= 30 and r.participation in ('full', ''):
            prof[r.md.split('/')[0]].append(r)
    order = ['MD+1', 'MD+2', 'MD+3', 'MD-6', 'MD-5', 'MD-4', 'MD-3', 'MD-2', 'MD-1']
    md_profile = [{'md': code, 'sessions': len(rs), **{
        m: round(sum(r.vals[m] for r in rs) / len(rs) / ref[m] * 100) if ref.get(m) else None for m in ('dist', 'hsr', 'spr', 'acc')}}
        for code, rs in sorted(prof.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)]
    match_log = [{'session_id': r.session_id, 'date': r.day.isoformat(), 'name': r.name, 'minutes': round(r.minutes),
                  'distance': round(r.vals['dist']), 'hsr': round(r.vals['hsr']), 'sprint': round(r.vals['spr']),
                  'distance_p90': round(r.vals['dist'] / r.minutes * 90) if r.minutes else None, 'vmax': r.vmax,
                  'participation': r.participation}
                 for r in reversed(mine) if r.is_match]
    vmax = [r.vmax for r in mine if r.vmax]
    return {
        'days': [{'date': d.isoformat(), 'distance': round(by_day[d]['dist']), 'hsr': round(by_day[d]['hsr']),
                  'md': meta.get(d, ('', False, None))[0], 'is_match': meta.get(d, ('', False, None))[1],
                  'session_id': meta.get(d, ('', False, None))[2]} for d in days],
        'acwr_distance': ewma(days, {d: v['dist'] for d, v in by_day.items()}),
        'acwr_hsr': None if player.pk in gk else ewma(days, {d: v['hsr'] for d, v in by_day.items()}),
        'md_profile': md_profile, 'match_log': match_log,
        'reference': {m: round(v) for m, v in ref.items()},
        'totals': {'sessions': len({r.session_id for r in mine if not r.is_match}), 'matches': len(match_log),
                   'match_minutes': sum(m['minutes'] for m in match_log), 'top_speed': max(vmax) if vmax else None,
                   'flagged': PlayerLoad.objects.filter(player=player).exclude(quality_flags=[]).count()},
    }


def microcycle(team: Team, match_session: TrainingSession | None = None) -> dict:
    """The week leading into a match: team load per day as % of match demand, and each player's grid."""
    matches = list(TrainingSession.objects.filter(team=team, session_type='match').order_by('start'))
    if not matches:
        return {'match': None, 'days': [], 'grid': [], 'matches': []}
    match_session = match_session or matches[-1]
    idx = next(i for i, m in enumerate(matches) if m.pk == match_session.pk)
    md_day = match_session.start.date()
    start = matches[idx - 1].start.date() + timedelta(1) if idx > 0 else md_day - timedelta(6)
    start = max(start, md_day - timedelta(6))
    all_rows = team_rows(team, end=md_day)
    gk = goalkeepers(team)
    team_ref = match_reference(all_rows, None, gk)
    rows = [r for r in all_rows if start <= r.day <= md_day]
    days = []
    for d in _days(start, md_day):
        rs = [r for r in rows if r.day == d and r.player_id not in gk and r.minutes >= 30]
        if not rs:
            days.append({'date': d.isoformat(), 'md': '', 'session_id': None, 'name': '', 'players': 0})
            continue
        is_match = rs[0].is_match
        if is_match:
            rs = [r for r in rs if r.minutes >= 60]
            vals = {m: sum(r.vals[m] / r.minutes * 90 for r in rs) / len(rs) for m in METRICS} if rs else {}
        else:
            rs = [r for r in rs if r.participation in ('full', '')] or rs
            vals = {m: sum(r.vals[m] for r in rs) / len(rs) for m in METRICS}
        days.append({'date': d.isoformat(), 'md': rs[0].md if rs else '', 'session_id': rs[0].session_id if rs else None,
                     'name': rs[0].name if rs else '', 'players': len(rs), 'is_match': is_match,
                     **{m: round(vals[m]) for m in vals}, 'pct': {m: round(vals[m] / team_ref[m] * 100)
                                                                  for m in vals if team_ref.get(m)}})
    grid = []
    for p in Player.objects.filter(club=team.club, current_team=team).exclude(pk__in=gk).order_by('shirt_number', 'full_name'):
        ref = match_reference(all_rows, p.pk, gk)
        cells = []
        for d in _days(start, md_day):
            r = next((r for r in rows if r.player_id == p.pk and r.day == d), None)
            if r is None:
                cells.append(None)
                continue
            k = 90 / r.minutes if r.is_match and r.minutes else 1
            cells.append({**{m: round(r.vals[m] * k / ref[m] * 100) if ref.get(m) else None for m in ('dist', 'hsr', 'spr', 'acc')},
                          'minutes': round(r.minutes), 'alternate': r.participation == 'alternate'})
        if any(cells):
            grid.append({'player_id': p.pk, 'name': p.display_name, 'shirt_number': p.shirt_number, 'cells': cells})
    return {
        'match': {'session_id': match_session.pk, 'date': md_day.isoformat(), 'name': match_session.name},
        'matches': [{'session_id': m.pk, 'date': m.start.date().isoformat(), 'name': m.name} for m in reversed(matches)],
        'reference': {m: round(v) for m, v in team_ref.items()}, 'days': days, 'grid': grid,
    }


def session_summaries(team: Team, start: date | None = None, end: date | None = None, kind: str | None = None) -> list[dict]:
    qs = TrainingSession.objects.filter(team=team).order_by('-start')
    if start:
        qs = qs.filter(start__date__gte=start)
    if end:
        qs = qs.filter(start__date__lte=end)
    if kind == 'match':
        qs = qs.filter(session_type='match')
    elif kind == 'training':
        qs = qs.exclude(session_type='match')
    sessions = list(qs)
    loads = defaultdict(list)
    for pl in PlayerLoad.objects.filter(training_session__in=sessions).only(
            'training_session_id', 'duration_min', 'total_distance_m', 'hsr_distance_m', 'sprint_distance_m', 'participation'):
        loads[pl.training_session_id].append(pl)
    out = []
    for s in sessions:
        ls = loads[s.pk]
        core = [x for x in ls if x.participation in ('full', '') and _f(x.duration_min) >= 30] or ls
        avg = lambda f: round(sum(_f(getattr(x, f)) for x in core) / len(core)) if core else None   # noqa: E731
        out.append({'id': s.pk, 'date': s.start.date().isoformat(), 'start': s.start.isoformat(), 'name': s.name,
                    'md': s.md_code, 'type': s.session_type, 'players': len(ls),
                    'duration': avg('duration_min'), 'distance': avg('total_distance_m'),
                    'hsr': avg('hsr_distance_m'), 'sprint': avg('sprint_distance_m')})
    return out


def own_team(club) -> Team | None:
    return Team.objects.filter(club=club, is_own=True).order_by('pk').first()


def session_queryset(club):
    return TrainingSession.objects.filter(club=club).filter(Q(team__is_own=True))
