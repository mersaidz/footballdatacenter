"""
Physical-data ingest (OpenField and future tracking providers).

Activity → where its loads attach:
  - match activity + an event-data Match of the same team that day → PlayerLoad.match
    (this is the join that lets us put physical and technical output side by side)
  - match activity without such a Match → TrainingSession(session_type="match")
  - anything else → TrainingSession, MD code from the provider tag or computed

Inside each activity:
  - periods are stored with a resolved role (football.services.period_roles);
  - per-period load is stored for every athlete;
  - for matches, PlayerLoad = playing periods only (football.services.loads);
  - the provider's participation tag (full / partial / alternate) is kept.

Same guarantees as the event ingest: idempotent, atomic per activity, raw
payloads kept, audited. Staff decisions (a period role set by hand) survive re-syncs.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from clubs.models import Club, Team
from core.models import AuditLog
from core.services.audit import log_event
from football.models import ActivityPeriod, Match, PeriodLoad, PeriodRoleMapping, PlayerLoad, TrainingSession
from football.services import period_roles
from football.services.loads import is_match_context, recompute_loads, snapshot
from football.services.matchday import match_dates, md_code_for
from metrics.services import custom_definitions, ensure_core_metrics, extract_metrics, sync_catalogue
from providers.connectors.base import NormalizedActivity, NormalizedLoad, NormalizedPlayer, PhysicalDataConnector
from providers.models import ExternalIdentity

from . import identity
from .ingest import store_raw

logger = logging.getLogger(__name__)
EntityType = ExternalIdentity.EntityType

LOAD_FIELDS = ('duration_min', 'total_distance_m', 'hsr_distance_m', 'sprint_distance_m', 'sprint_count',
               'accelerations', 'decelerations', 'max_speed_kmh', 'player_load')
DECIMAL_FIELDS = {'duration_min', 'max_speed_kmh', 'player_load'}


@dataclass
class PhysicalIngestSummary:
    activities: int = 0
    sessions_created: int = 0
    sessions_updated: int = 0
    linked_to_matches: int = 0
    loads: int = 0
    flagged: int = 0
    periods: int = 0
    periods_to_review: int = 0
    period_loads: int = 0
    catalogue: int = 0
    custom_metrics: int = 0
    errors: list[str] = field(default_factory=list)


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _speed_flags(max_speed: float | None, personal_best: float | None, connector) -> list[str]:
    if max_speed is None:
        return []
    limit = connector.max_speed_cap_kmh
    if personal_best:
        limit = min(limit, personal_best * connector.personal_max_tolerance)
    return [PlayerLoad.Flag.MAX_SPEED_OUTLIER] if max_speed > limit else []


def _load_values(load: NormalizedLoad, connector, personal_best: float | None = None, defs=()) -> dict:
    values = {'metrics': extract_metrics(load.extra_metrics, list(defs))}
    for name in LOAD_FIELDS:
        v = getattr(load, name)
        if v is None:
            values[name] = None
        elif name in DECIMAL_FIELDS:
            values[name] = Decimal(str(round(v, 2 if name == 'duration_min' else 1)))
        else:
            values[name] = int(round(v))
    values['extra_metrics'] = dict(load.extra_metrics)
    values['quality_flags'] = _speed_flags(load.max_speed_kmh, personal_best, connector)
    for name in ('hsr_threshold_kmh', 'sprint_threshold_kmh'):
        v = getattr(connector, name, None)
        values[name] = Decimal(str(round(v, 1))) if v is not None else None
    return values


def _find_same_day_match(club: Club, team: Team, provider: str, local_day, tz) -> Match | None:
    window = (local_day - timedelta(days=1), local_day + timedelta(days=1))
    mapped = ExternalIdentity.objects.filter(club=club, provider=provider, entity_type=EntityType.MATCH) \
        .values('object_id')
    for m in (Match.objects.filter(club=club, kickoff__date__range=window)
              .filter(Q(home_team=team) | Q(away_team=team)).exclude(pk__in=mapped)):
        if m.kickoff.astimezone(tz).date() == local_day:
            return m
    return None


def _resolve_context(club, team, provider, act: NormalizedActivity, tz, summary) -> tuple[Match | None, TrainingSession | None]:
    local_day = act.start.astimezone(tz).date()

    match = identity.get_mapped(club, provider, EntityType.MATCH, act.external_id, Match)
    if match is None and act.is_match:
        match = _find_same_day_match(club, team, provider, local_day, tz)
        if match is not None:
            identity.link(club, provider, EntityType.MATCH, act.external_id, match,
                          method=ExternalIdentity.Method.EXACT, external_name=act.name)
    if match is not None:
        summary.linked_to_matches += 1
        return match, None

    session_type = 'match' if act.is_match else 'training'
    md_code = act.day_code or ('MD' if act.is_match else md_code_for(local_day, match_dates(team, local_day)))
    fields = dict(team=team, start=act.start, end=act.end, name=act.name[:150],
                  md_code=md_code[:12], session_type=session_type)

    session = identity.get_mapped(club, provider, EntityType.TRAINING_SESSION, act.external_id, TrainingSession)
    if session is None:
        session = TrainingSession.objects.create(club=club, **fields)
        identity.link(club, provider, EntityType.TRAINING_SESSION, act.external_id, session,
                      method=ExternalIdentity.Method.CREATED, external_name=act.name)
        summary.sessions_created += 1
    else:
        for k, v in fields.items():
            setattr(session, k, v)
        session.save()
        summary.sessions_updated += 1
    return None, session


def _store_periods(club, connector, act, periods, ctx, is_match, summary) -> dict[str, ActivityPeriod]:
    provider = connector.provider
    existing = {p.external_id: p for p in ActivityPeriod.objects.filter(club=club, provider=provider, **ctx)}
    club_map = dict(PeriodRoleMapping.objects.filter(club=club).values_list('normalized_name', 'role'))
    inputs = [
        period_roles.PeriodInput(
            key=p.external_id, name=p.name, start=p.start, end=p.end, tags=p.tags,
            manual_role=(existing[p.external_id].role
                         if p.external_id in existing and existing[p.external_id].role_source == 'manual' else None),
        ) for p in periods
    ]
    decisions = period_roles.classify(inputs, is_match=is_match, club_map=club_map,
                                      tag_type=connector.period_role_tag_type)
    stored = {}
    for seq, p in enumerate(sorted(periods, key=lambda x: x.start)):
        d = decisions[p.external_id]
        defaults = {'match': None, 'training_session': None, **ctx,
                    'name': p.name[:150], 'normalized_name': period_roles.normalize(p.name)[:150],
                    'start': p.start, 'end': p.end, 'sequence': seq, 'role': d.role, 'role_source': d.source,
                    'role_confidence': Decimal(str(round(d.confidence, 2)))}
        obj, _ = ActivityPeriod.objects.update_or_create(
            club=club, provider=provider, external_id=p.external_id, defaults=defaults,
        )
        stored[p.external_id] = obj
        summary.periods += 1
        if d.role == ActivityPeriod.Role.UNKNOWN:
            summary.periods_to_review += 1
    ActivityPeriod.objects.filter(club=club, provider=provider, **ctx).exclude(external_id__in=stored).delete()
    return stored


def _ingest_activity(club, connector, team, act, loads, period_loads, periods, participation,
                     athletes, speed_bests, tz, summary, defs=()):
    provider = connector.provider
    with transaction.atomic():
        match, session = _resolve_context(club, team, provider, act, tz, summary)
        ctx = {'match': match} if match else {'training_session': session}
        is_match = is_match_context(match, session)

        players = {}

        def player_for(ext_id):
            if ext_id not in players:
                incoming = athletes.get(ext_id) or NormalizedPlayer(
                    external_id=ext_id, full_name=f'OpenField athlete {ext_id[:8]}')
                players[ext_id] = identity.resolve_player(club, provider, incoming, team=team)
            return players[ext_id]

        kept = []
        for load in loads:
            values = _load_values(load, connector, speed_bests.get(load.athlete_external_id), defs)
            values['extra_metrics']['activity_total'] = snapshot(values)
            values['extra_metrics']['activity_flags'] = values['quality_flags']
            values['extra_metrics']['activity_metrics'] = values['metrics']
            values['participation'] = participation.get(load.athlete_external_id, '')
            values['load_basis'] = PlayerLoad.Basis.ACTIVITY
            obj, _ = PlayerLoad.objects.update_or_create(
                club=club, player=player_for(load.athlete_external_id), provider=provider, **ctx, defaults=values,
            )
            kept.append(obj.pk)
        # Athletes removed from the activity upstream disappear here too.
        PlayerLoad.objects.filter(club=club, provider=provider, **ctx).exclude(pk__in=kept).delete()

        stored_periods = _store_periods(club, connector, act, periods, ctx, is_match, summary)
        kept_pl = []
        for pl in period_loads:
            period = stored_periods.get(pl.period_external_id)
            if period is None:
                continue
            values = _load_values(pl, connector, speed_bests.get(pl.athlete_external_id), defs)
            obj, _ = PeriodLoad.objects.update_or_create(
                club=club, player=player_for(pl.athlete_external_id), period=period, provider=provider,
                defaults=values,
            )
            kept_pl.append(obj.pk)
        PeriodLoad.objects.filter(club=club, provider=provider, period__in=stored_periods.values()) \
            .exclude(pk__in=kept_pl).delete()
        summary.period_loads += len(kept_pl)

        if is_match:
            recompute_loads(match=match, training_session=session)
        summary.loads += len(kept)
        summary.flagged += PlayerLoad.objects.filter(pk__in=kept).exclude(quality_flags=[]).count()


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 — optional detail; the activity still ingests without it
        logger.exception('Optional fetch %s failed', getattr(fn, '__name__', fn))
        return None


def ingest_physical(
    club: Club, connector: PhysicalDataConnector, team: Team, start: datetime, end: datetime,
    *, chunk_size: int = 25, period_chunk_size: int = 10,
) -> PhysicalIngestSummary:
    summary = PhysicalIngestSummary()
    tz = ZoneInfo(club.timezone or 'UTC')

    # Metric catalogue: refresh the provider's parameter list, then ask for every metric the club enabled.
    ensure_core_metrics(club)
    catalogue = _safe(connector.fetch_catalogue)
    if catalogue is not None and catalogue.payload:
        store_raw(club, connector, catalogue)
        try:
            with transaction.atomic():
                summary.catalogue = sync_catalogue(club, connector.provider, catalogue.payload)
        except Exception as exc:  # noqa: BLE001 — the catalogue is a convenience; loads must still sync
            logger.exception('Metric catalogue sync failed')
            summary.errors.append(f'metric catalogue: {exc}')
    defs = custom_definitions(club, connector.provider)
    connector.extra_slugs = tuple(d.provider_slug for d in defs)
    summary.custom_metrics = len(defs)

    athletes_res = connector.fetch_athletes()
    store_raw(club, connector, athletes_res)
    athletes = {p.external_id: p for p in connector.normalize_athletes(athletes_res.payload)}
    speed_bests = connector.athlete_max_speeds(athletes_res.payload)

    acts_res = connector.fetch_activities(start, end)
    store_raw(club, connector, acts_res)
    activities = connector.normalize_activities(acts_res.payload)
    summary.activities = len(activities)

    loads_by_activity: dict[str, list[NormalizedLoad]] = defaultdict(list)
    for chunk in _chunks(activities, chunk_size):
        try:
            stats_res = connector.fetch_activity_stats([a.external_id for a in chunk])
        except Exception as exc:  # noqa: BLE001 — record and continue with other chunks
            logger.exception('Stats fetch failed for %d activities', len(chunk))
            summary.errors.append(f'stats for {len(chunk)} activities: {exc}')
            continue
        store_raw(club, connector, stats_res)
        for load in connector.normalize_stats(stats_res.payload):
            loads_by_activity[load.activity_external_id].append(load)

    period_loads_by_activity: dict[str, list[NormalizedLoad]] = defaultdict(list)
    for chunk in _chunks(activities, period_chunk_size):
        res = _safe(connector.fetch_period_stats, [a.external_id for a in chunk])
        if res is None:
            continue
        store_raw(club, connector, res)
        for load in connector.normalize_stats(res.payload, by_period=True):
            period_loads_by_activity[load.activity_external_id].append(load)

    # Matches first, so MD codes of training days can count back from them.
    for act in sorted(activities, key=lambda a: (not a.is_match, a.start)):
        periods = list(act.periods)
        periods_res = _safe(connector.fetch_activity_periods, act.external_id)
        if periods_res is not None:
            store_raw(club, connector, periods_res)
            detailed = connector.normalize_periods(periods_res.payload)
            if detailed:
                periods = detailed   # the detail endpoint carries period tags
        athletes_res = _safe(connector.fetch_activity_athletes, act.external_id)
        participation = {}
        if athletes_res is not None:
            store_raw(club, connector, athletes_res)
            participation = connector.normalize_participation(athletes_res.payload)
        try:
            _ingest_activity(club, connector, team, act, loads_by_activity.get(act.external_id, []),
                             period_loads_by_activity.get(act.external_id, []), periods, participation,
                             athletes, speed_bests, tz, summary, defs)
        except Exception as exc:  # noqa: BLE001
            logger.exception('Ingest failed for activity %s', act.external_id)
            summary.errors.append(f'{act.external_id}: {exc}')

    if connector.account is not None:
        connector.account.last_synced_at = timezone.now()
        connector.account.save(update_fields=['last_synced_at', 'updated_at'])

    log_event(
        action=AuditLog.Action.SYNC_FAILED if summary.errors and not summary.loads else AuditLog.Action.SYNC_SUCCESS,
        club=club, provider=connector.provider,
        extra_info={'from': start.isoformat(), 'to': end.isoformat(), 'activities': summary.activities,
                    'loads': summary.loads, 'flagged': summary.flagged, 'linked_to_matches': summary.linked_to_matches,
                    'periods': summary.periods, 'periods_to_review': summary.periods_to_review,
                    'errors': summary.errors[:20]},
    )
    return summary
