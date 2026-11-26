"""
IMPECT ingest: a whole competition season (an IMPECT "iteration").

  every match   → Match, MatchAppearance (positions, shirt numbers, minutes),
                  PlayerMatchKpis (all ~100 KPIs per player and position)
  chosen squad  → also every event (passes, carries, shots with xG, packing…)

League-wide KPIs are what make percentiles possible ("his packing per 90 vs every
right winger in the league"); full events are only needed for the club's own matches.

Demo link: `demo_link_squad` pairs the club's players with a real squad's players
(goalkeeper with goalkeeper, then by minutes). The links carry method=demo, so the UI
can say plainly that this football data is someone else's.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q, Sum

from clubs.models import Club, Player, Team
from core.models import AuditLog
from core.services.audit import log_event
from football.models import Event, MatchAppearance, PlayerLoad, PlayerMatchKpis
from metrics.services import sync_catalogue
from providers.connectors.impect import POSITION, ImpectConnector
from providers.models import ExternalIdentity

from . import identity
from .ingest import EVENT_BATCH_SIZE, store_raw

logger = logging.getLogger(__name__)


@dataclass
class ImpectSummary:
    competition: str = ''
    matches: int = 0
    matches_with_events: int = 0
    appearances: int = 0
    kpi_rows: int = 0
    events: int = 0
    players_created: int = 0
    demo_links: list[tuple[str, str, str, int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _keep(club, connector, res):
    if res.persist:
        store_raw(club, connector, res)
    return res.payload


def find_squad(connector: ImpectConnector, name: str):
    target = identity.normalize_name(name)
    hits = [t for t in connector._squads.values() if target in identity.normalize_name(t.name)]
    if len(hits) != 1:
        names = ', '.join(sorted(t.name for t in connector._squads.values()))
        raise ValueError(f"'{name}' matches {len(hits)} squads. Available: {names}")
    return hits[0]


def _goalkeepers(players: list[Player]) -> set[int]:
    """Goalkeepers barely run above HSR speed: < 25 % of the squad's median HSR per minute."""
    rate = {}
    for p in players:
        agg = PlayerLoad.objects.filter(player=p).aggregate(h=Sum('hsr_distance_m'), m=Sum('duration_min'))
        if agg['m']:
            rate[p.pk] = float(agg['h'] or 0) / float(agg['m'])
    if len(rate) < 4:
        return set()
    med = sorted(rate.values())[len(rate) // 2]
    return {pk for pk, r in rate.items() if r < med * 0.25}


def demo_link_squad(club: Club, connector: ImpectConnector, squad_ext: str, our_team: Team,
                    kpi_payloads: list[dict], goalkeepers: set[int] | None = None) -> list[tuple[str, str, str, int]]:
    """Pair our players with the squad's: goalkeepers first, then most minutes with most minutes."""
    minutes, positions = Counter(), defaultdict(Counter)
    for payload in kpi_payloads:
        for row in connector.normalize_player_kpis(payload):
            if row['squad'] == squad_ext:
                minutes[row['player']] += row['seconds'] / 60
                positions[row['player']][row['position']] += row['seconds']
    already = ExternalIdentity.objects.filter(club=club, provider=connector.provider, entity_type='player')
    taken_ext = set(already.values_list('external_id', flat=True))
    linked_obj = set(already.values_list('object_id', flat=True))
    ours = [p for p in Player.objects.filter(club=club, current_team=our_team) if p.pk not in linked_obj]
    if not ours:
        return []
    gk = goalkeepers if goalkeepers is not None else _goalkeepers(ours)
    in_match = Q(match__isnull=False) | Q(training_session__session_type='match')
    match_min = {p.pk: float(PlayerLoad.objects.filter(in_match, player=p).aggregate(m=Sum('duration_min'))['m'] or 0)
                 for p in ours}
    by_minutes = lambda ps: sorted(ps, key=lambda p: -match_min[p.pk])
    theirs = [(pid, m, positions[pid].most_common(1)[0][0]) for pid, m in minutes.most_common() if pid not in taken_ext]
    their_gk = [t for t in theirs if t[2] == 'GOALKEEPER']
    their_out = [t for t in theirs if t[2] != 'GOALKEEPER']
    pairs = list(zip(by_minutes([p for p in ours if p.pk in gk]), their_gk)) + \
        list(zip(by_minutes([p for p in ours if p.pk not in gk]), their_out))
    out = []
    for ours_p, (pid, mins, pos) in pairs:
        np = connector.normalized_player(pid)
        identity.link(club, connector.provider, ExternalIdentity.EntityType.PLAYER, pid, ours_p,
                      method=ExternalIdentity.Method.DEMO, external_name=np.full_name,
                      external_meta={'demo': True, 'squad': connector.team(squad_ext).name, 'position': pos,
                                     'minutes': round(mins)})
        out.append((ours_p.display_name, np.full_name, pos, round(mins)))
    return out


def ingest_impect(club: Club, connector: ImpectConnector, iteration, *, events_squad: str | None = None,
                  demo_link_to: Team | None = None, goalkeepers: set[int] | None = None,
                  limit: int | None = None, progress=None) -> ImpectSummary:
    summary = ImpectSummary()
    info = connector.load_iteration(iteration)
    comp, season = connector.competition()
    summary.competition = f'{comp.name} {season.name}'
    connector.load_kpi_definitions()
    sync_catalogue(club, connector.provider, connector.kpi_catalogue())     # IMPECT KPIs become searchable metrics

    matches = sorted(connector.normalize_matches(_keep(club, connector, connector.fetch_matches(season_id=str(info['id'])))),
                     key=lambda m: m.kickoff)
    if limit:
        matches = matches[:limit]
    squad = find_squad(connector, events_squad) if events_squad else None
    in_squad = lambda m: squad is not None and squad.external_id in (m.home_team.external_id, m.away_team.external_id)

    kpi_cache: dict[str, dict] = {}
    if squad is not None and demo_link_to is not None:
        for nm in filter(in_squad, matches):
            kpi_cache[nm.external_id] = _keep(club, connector, connector.fetch_player_kpis(nm.external_id))
        with transaction.atomic():
            summary.demo_links = demo_link_squad(club, connector, squad.external_id, demo_link_to,
                                                 list(kpi_cache.values()), goalkeepers)

    created_before = ExternalIdentity.objects.filter(club=club, provider=connector.provider, entity_type='player',
                                                     method=ExternalIdentity.Method.CREATED).count()
    for i, nm in enumerate(matches, 1):
        try:
            with transaction.atomic():
                kp = kpi_cache.pop(nm.external_id, None) or _keep(club, connector, connector.fetch_player_kpis(nm.external_id))
                n_app, n_kpi, n_ev = _ingest_match(club, connector, nm, kp, with_events=in_squad(nm))
            summary.matches += 1
            summary.appearances += n_app
            summary.kpi_rows += n_kpi
            summary.events += n_ev
            summary.matches_with_events += bool(n_ev)
        except Exception as exc:  # noqa: BLE001 — one bad match must not stop the season
            logger.exception('IMPECT ingest failed for match %s', nm.external_id)
            summary.errors.append(f'{nm.external_id}: {exc}')
        if progress:
            progress(i, len(matches), nm)

    _fill_player_profiles(club, connector)
    summary.players_created = ExternalIdentity.objects.filter(
        club=club, provider=connector.provider, entity_type='player', method=ExternalIdentity.Method.CREATED,
    ).count() - created_before
    log_event(action=AuditLog.Action.SYNC_SUCCESS if not summary.errors or summary.matches else AuditLog.Action.SYNC_FAILED,
              club=club, provider=connector.provider,
              extra_info={'iteration': str(info['id']), 'competition': summary.competition, 'matches': summary.matches,
                          'events': summary.events, 'kpi_rows': summary.kpi_rows, 'demo_links': len(summary.demo_links),
                          'errors': summary.errors[:20]})
    return summary


def _ingest_match(club, connector: ImpectConnector, nm, kpi_payload: dict, *, with_events: bool) -> tuple[int, int, int]:
    provider = connector.provider
    match, _ = identity.resolve_match(club, provider, nm)
    teams = {nm.home_team.external_id: match.home_team, nm.away_team.external_id: match.away_team}
    kpi_rows = connector.normalize_player_kpis(kpi_payload)
    seconds, by_pos = defaultdict(float), defaultdict(Counter)
    for r in kpi_rows:
        seconds[r['player']] += r['seconds']
        by_pos[r['player']][r['position']] += r['seconds']
    main_pos = {pid: c.most_common(1)[0][0] for pid, c in by_pos.items()}

    events, ev_payload = [], None
    if with_events:
        ev_payload = _keep(club, connector, connector.fetch_events(nm.external_id))
        ek = _keep(club, connector, connector.fetch_event_kpis(nm.external_id))
        events = list(connector.normalize_events(ev_payload, ek))
    open_play = [e.minute for e in events if e.period <= 2]
    match.duration_minutes = (max(open_play) + 1) if open_play else max(90, round(max(seconds.values(), default=0) / 60))

    # score from goals (own goals count for the other side)
    goals = Counter()
    for r in kpi_rows:
        other = nm.away_team.external_id if r['squad'] == nm.home_team.external_id else nm.home_team.external_id
        goals[r['squad']] += int(r['kpis'].get('GOALS') or 0)
        goals[other] += int(r['kpis'].get('OWNGOALS') or 0)
    match.home_score, match.away_score = goals[nm.home_team.external_id], goals[nm.away_team.external_id]
    match.save(update_fields=['duration_minutes', 'home_score', 'away_score', 'updated_at'])

    lineups = _keep(club, connector, connector.fetch_lineups(nm.external_id))
    players = {}
    apps = []
    for app in connector.normalize_lineups(lineups, seconds, match.duration_minutes, main_pos):
        team = teams[app.team_external_id]
        player = identity.resolve_player(club, provider, app.player, team=team)
        players[app.player.external_id] = player
        end = app.minute_off if app.minute_off is not None else match.duration_minutes
        apps.append(MatchAppearance(club=club, match=match, team=team, player=player, started=app.started,
                                    position=app.position, shirt_number=app.shirt_number, minute_on=app.minute_on,
                                    minute_off=app.minute_off, minutes_played=max(0, end - (app.minute_on or 0))))
    MatchAppearance.objects.filter(match=match, player__in=[a.player for a in apps]).delete()
    MatchAppearance.objects.bulk_create(apps)

    PlayerMatchKpis.objects.filter(match=match, provider=provider).delete()
    rows = []
    for r in kpi_rows:
        player = players.get(r['player']) or identity.resolve_player(
            club, provider, connector.normalized_player(r['player']), team=teams[r['squad']])
        players[r['player']] = player
        rows.append(PlayerMatchKpis(club=club, provider=provider, match=match, team=teams[r['squad']], player=player,
                                    position=r['position'], play_seconds=r['seconds'], kpis=r['kpis']))
    PlayerMatchKpis.objects.bulk_create(rows, ignore_conflicts=True)

    n_ev = 0
    if with_events:
        Event.objects.filter(match=match, provider=provider).delete()
        batch = []
        for ev in events:
            player = None
            if ev.player_external_id:
                player = players.get(ev.player_external_id)
                if player is None:
                    player = identity.resolve_player(club, provider, connector.normalized_player(ev.player_external_id),
                                                     team=teams[ev.team_external_id])
                    players[ev.player_external_id] = player
            batch.append(Event(club=club, match=match, team=teams[ev.team_external_id], player=player, provider=provider,
                               external_id=ev.external_id, sequence=ev.sequence, period=ev.period, minute=ev.minute,
                               second=ev.second, period_ms=ev.period_ms, event_type=ev.event_type, outcome=ev.outcome,
                               possession=ev.possession, under_pressure=ev.under_pressure, x=ev.x, y=ev.y,
                               end_x=ev.end_x, end_y=ev.end_y,
                               xg=min(1.0, max(0.0, ev.xg)) if ev.xg is not None else None, attributes=ev.attributes))
        Event.objects.bulk_create(batch, batch_size=EVENT_BATCH_SIZE)
        n_ev = len(batch)
    return len(apps), len(rows), n_ev


def _fill_player_profiles(club, connector: ImpectConnector):
    """Position, foot and shirt number from IMPECT — only where the club hasn't set them."""
    links = ExternalIdentity.objects.filter(club=club, provider=connector.provider, entity_type='player')
    for ident in links:
        player = Player.objects.filter(pk=ident.object_id, club=club).first()
        if player is None:
            continue
        changed = []
        if not player.primary_position:
            pos = Counter()
            for row in PlayerMatchKpis.objects.filter(player=player, provider=connector.provider).only('position', 'play_seconds'):
                pos[row.position] += row.play_seconds
            if pos and POSITION.get(pos.most_common(1)[0][0]):
                player.primary_position = POSITION[pos.most_common(1)[0][0]]
                changed.append('primary_position')
        if not player.preferred_foot and connector.player_foot(ident.external_id):
            player.preferred_foot = connector.player_foot(ident.external_id)
            changed.append('preferred_foot')
        if player.shirt_number is None:
            last = MatchAppearance.objects.filter(player=player).exclude(shirt_number=None).order_by('-match__kickoff').first()
            if last:
                player.shirt_number = last.shirt_number
                changed.append('shirt_number')
        if changed:
            player.save(update_fields=changed + ['updated_at'])
