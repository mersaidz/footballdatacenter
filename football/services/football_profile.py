"""
A player's on-the-ball profile from event data (IMPECT): per-90 KPIs, percentiles
against every player of his position in the competition, match log, shot and carry maps.

Percentiles compare like with like: players whose main position (most minutes) is the
same, with at least MIN_MINUTES in the season. Rates are per 90 over all their minutes.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from football.models import Event, Match, PlayerMatchKpis, Season
from providers.models import ExternalIdentity

MIN_MINUTES = 450

# label, KPI (or computed), group, higher_is_better
PROFILE_KPIS = [
    (_('xG'), 'SHOT_XG', 'Attacking', True),
    (_('Shots'), 'SHOT_AT_GOAL_NUMBER', 'Attacking', True),
    (_('Goals'), 'GOALS', 'Attacking', True),
    (_('xA'), 'EXPECTED_GOAL_ASSISTS', 'Attacking', True),
    (_('Shot-creating actions'), 'SHOT_CREATING_ACTIONS', 'Attacking', True),
    (_('Packing (bypassed opponents)'), 'BYPASSED_OPPONENTS', 'Ball progression', True),
    (_('Bypassed defenders'), 'BYPASSED_DEFENDERS', 'Ball progression', True),
    (_('Packing by receiving'), 'BYPASSED_OPPONENTS_RECEIVING', 'Ball progression', True),
    (_('Ball carrying (m gained)'), 'DISTANCE_TO_GOAL_COVERED_DRIBBLE', 'Ball progression', True),
    (_('Pass completion %'), 'pass_pct', 'Ball progression', True),
    (_('Ball losses'), 'BALL_LOSS_NUMBER', 'Ball progression', False),
    (_('Ball wins'), 'BALL_WIN_NUMBER', 'Defending', True),
    (_('Presses'), 'NUMBER_OF_PRESSES', 'Defending', True),
    (_('Ground duels won %'), 'ground_duel_pct', 'Defending', True),
    (_('Aerial duels won %'), 'aerial_duel_pct', 'Defending', True),
]
GROUP_KEYS = {'Attacking': 'attacking', 'Ball progression': 'progression', 'Defending': 'defending'}
GROUP_LABELS = {'Attacking': _('Attacking'), 'Ball progression': _('Ball progression'), 'Defending': _('Defending')}
RATIOS = {
    'pass_pct': ('SUCCESSFUL_PASSES', 'UNSUCCESSFUL_PASSES'),
    'ground_duel_pct': ('WON_GROUND_DUELS', 'LOST_GROUND_DUELS'),
    'aerial_duel_pct': ('WON_AERIAL_DUELS', 'LOST_AERIAL_DUELS'),
}
PEERS = {
    'GOALKEEPER': 'goalkeepers', 'CENTRAL_DEFENDER': 'centre-backs', 'LEFT_WINGBACK_DEFENDER': 'full-backs',
    'RIGHT_WINGBACK_DEFENDER': 'full-backs', 'DEFENSE_MIDFIELD': 'defensive midfielders',
    'CENTRAL_MIDFIELD': 'central midfielders', 'ATTACKING_MIDFIELD': 'attacking midfielders',
    'LEFT_WINGER': 'wingers', 'RIGHT_WINGER': 'wingers', 'CENTER_FORWARD': 'centre-forwards',
}
PEER_GROUP = {'LEFT_WINGBACK_DEFENDER': 'FB', 'RIGHT_WINGBACK_DEFENDER': 'FB', 'LEFT_WINGER': 'W', 'RIGHT_WINGER': 'W'}


def _group(pos: str) -> str:
    return PEER_GROUP.get(pos, pos)


def _totals(rows) -> dict[int, dict]:
    """player → {'seconds', 'kpis': summed, 'pos': Counter(position → seconds), 'matches': set}"""
    out: dict[int, dict] = defaultdict(lambda: {'seconds': 0.0, 'kpis': Counter(), 'pos': Counter(), 'matches': set()})
    for r in rows:
        t = out[r.player_id]
        t['seconds'] += r.play_seconds
        t['pos'][r.position] += r.play_seconds
        t['matches'].add(r.match_id)
        for k, v in (r.kpis or {}).items():
            if isinstance(v, (int, float)):
                t['kpis'][k] += v
    return out


def _rate(t: dict, key: str) -> float | None:
    if key in RATIOS:
        won, lost = (t['kpis'].get(k, 0) for k in RATIOS[key])
        return round(100 * won / (won + lost), 1) if won + lost else None
    minutes = t['seconds'] / 60
    return round(t['kpis'].get(key, 0) / minutes * 90, 2) if minutes else None


def _percentile(sorted_vals: list[float], v: float) -> int:
    below, upto = bisect_left(sorted_vals, v), bisect_right(sorted_vals, v)
    return round(100 * (below + 0.5 * (upto - below)) / len(sorted_vals))


def football_profile(player, provider: str = 'impect', season: Season | None = None) -> dict | None:
    mine = PlayerMatchKpis.objects.filter(player=player, provider=provider).select_related('match__season__competition')
    if season is None:
        last = mine.order_by('-match__kickoff').first()
        if last is None:
            return None
        season = last.match.season
    season_q = Q(match__season=season) if season else Q()
    rows = list(PlayerMatchKpis.objects.filter(season_q, club=player.club, provider=provider))
    totals = _totals(rows)
    me = totals.get(player.pk)
    if not me:
        return None
    main_pos = me['pos'].most_common(1)[0][0]
    peers = [t for pid, t in totals.items()
             if t['seconds'] / 60 >= MIN_MINUTES and _group(t['pos'].most_common(1)[0][0]) == _group(main_pos)]

    groups: dict[str, list] = {}
    for label, key, group, hib in PROFILE_KPIS:
        v = _rate(me, key)
        if v is None:
            continue
        dist = sorted(x for x in (_rate(t, key) for t in peers) if x is not None)
        pct = _percentile(dist, v) if dist else None
        if pct is not None and not hib:
            pct = 100 - pct                          # fewer ball losses = better
        groups.setdefault(group, []).append({
            'label': str(label), 'kpi': key, 'per90': v, 'percentile': pct, 'higher_is_better': hib,
            'unit': '%' if key in RATIOS else 'per 90'})

    # match log (all his matches this season, newest first)
    by_match = defaultdict(lambda: {'seconds': 0.0, 'kpis': Counter(), 'pos': Counter()})
    for r in rows:
        if r.player_id == player.pk:
            m = by_match[r.match_id]
            m['seconds'] += r.play_seconds
            m['pos'][r.position] += r.play_seconds
            for k, v in (r.kpis or {}).items():
                if isinstance(v, (int, float)):
                    m['kpis'][k] += v
    matches = {m.pk: m for m in Match.objects.filter(pk__in=by_match).select_related('home_team', 'away_team')}
    team_of = dict(PlayerMatchKpis.objects.filter(player=player, match_id__in=by_match).values_list('match_id', 'team_id'))
    log = []
    for mid, t in sorted(by_match.items(), key=lambda kv: matches[kv[0]].kickoff, reverse=True):
        m = matches[mid]
        home = team_of.get(mid) == m.home_team_id
        k = t['kpis']
        log.append({
            'match_id': mid, 'date': m.kickoff.date().isoformat(), 'home': home,
            'opponent': (m.away_team if home else m.home_team).name,
            'score': f'{m.home_score}–{m.away_score}' if m.home_score is not None else '',
            'result': _result(m, home), 'minutes': round(t['seconds'] / 60), 'position': t['pos'].most_common(1)[0][0],
            'xg': round(k.get('SHOT_XG', 0), 2), 'shots': int(k.get('SHOT_AT_GOAL_NUMBER', 0)), 'goals': int(k.get('GOALS', 0)),
            'packing': round(k.get('BYPASSED_OPPONENTS', 0), 1),
            'carrying_m': round(k.get('DISTANCE_TO_GOAL_COVERED_DRIBBLE', 0)),
            'ball_losses': int(k.get('BALL_LOSS_NUMBER', 0)),
        })

    ev = Event.objects.filter(player=player, provider=provider, match_id__in=by_match)
    shots = [{'x': e.x, 'y': e.y, 'end_x': e.end_x, 'end_y': e.end_y, 'xg': round(e.xg or 0, 3),
              'goal': e.outcome == 'success', 'match_id': e.match_id, 'minute': e.minute,
              'kind': (e.attributes or {}).get('action', ''), 'body_part': (e.attributes or {}).get('body_part', ''),
              'pressure': (e.attributes or {}).get('pressure'),                 # IMPECT 0–100, None = unknown
              'opponent_distance': (e.attributes or {}).get('distance_to_opponent')}
             for e in ev.filter(event_type='shot').exclude(x=None).order_by('match_id', 'sequence')]
    progressive = lambda e: e.end_x - e.x >= 10 and e.end_x >= 40          # noqa: E731 — 10 m+ towards goal, beyond own third
    carries = [{'x': e.x, 'y': e.y, 'end_x': e.end_x, 'end_y': e.end_y, 'match_id': e.match_id, 'minute': e.minute,
                'bypassed': (e.attributes or {}).get('bypassed_opponents')}
               for e in ev.filter(event_type='carry').exclude(x=None).exclude(end_x=None) if progressive(e)]
    passes = [{'x': e.x, 'y': e.y, 'end_x': e.end_x, 'end_y': e.end_y, 'match_id': e.match_id, 'minute': e.minute,
               'bypassed': (e.attributes or {}).get('bypassed_opponents')}
              for e in ev.filter(event_type='pass', outcome='success').exclude(x=None).exclude(end_x=None)
              if progressive(e) and not (e.attributes or {}).get('set_piece')]
    touches = list(ev.exclude(x=None).values_list('x', 'y', 'match_id'))
    avg = ({'x': round(sum(t[0] for t in touches) / len(touches), 1),
            'y': round(sum(t[1] for t in touches) / len(touches), 1)} if touches else None)
    # where he is on the ball: share of his actions per zone (12 × 8 grid over the pitch), season and per match
    GX, GY = 12, 8
    def grid(points):
        cells = [[0] * GX for _ in range(GY)]
        for x, y, *_ in points:
            cells[min(GY - 1, int(y / 68 * GY))][min(GX - 1, int(x / 105 * GX))] += 1
        return cells
    heat = {'cols': GX, 'rows': GY, 'season': grid(touches),
            'matches': {mid: grid([t for t in touches if t[2] == mid]) for mid in by_match}}

    link = ExternalIdentity.objects.filter(club=player.club, provider=provider, entity_type='player',
                                           object_id=player.pk).first()
    return {
        'provider': provider,
        'competition': season.competition.name if season else '', 'season': season.name if season else '',
        'demo_link': ({'source_player': link.external_name, **{k: v for k, v in (link.external_meta or {}).items()
                                                                if k in ('squad', 'position')}}
                      if link and link.method == ExternalIdentity.Method.DEMO else None),
        'main_position': main_pos, 'peers': PEERS.get(main_pos, 'players'), 'peer_count': len(peers),
        'min_minutes': MIN_MINUTES, 'minutes': round(me['seconds'] / 60), 'matches': len(me['matches']),
        'groups': [{'key': GROUP_KEYS[g], 'label': str(GROUP_LABELS[g]), 'kpis': v} for g, v in groups.items()],
        'match_log': log, 'shots': shots, 'carries': carries[:400], 'passes': passes[:400], 'heat': heat,
        'average_position': avg,
    }


def _result(m: Match, home: bool) -> str:
    if m.home_score is None:
        return ''
    us, them = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
    return 'W' if us > them else 'L' if us < them else 'D'
