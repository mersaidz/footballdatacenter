"""
Physical-data ingest (OpenField and future tracking providers).

Activity → where its loads attach:
  - match activity + an event-data Match of the same team that day → PlayerLoad.match
    (this is the join that lets us put physical and technical output side by side)
  - match activity without such a Match → TrainingSession(session_type="match")
  - anything else → TrainingSession, MD code from the provider tag or computed

Same guarantees as the event ingest: idempotent, atomic per activity, raw
payloads kept, audited.
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
from football.models import Match, PlayerLoad, TrainingSession
from football.services.matchday import match_dates, md_code_for
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


def _load_values(load: NormalizedLoad, connector, personal_best: float | None = None) -> dict:
    values = {}
    for name in LOAD_FIELDS:
        v = getattr(load, name)
        if v is None:
            values[name] = None
        elif name in DECIMAL_FIELDS:
            values[name] = Decimal(str(round(v, 2 if name == 'duration_min' else 1)))
        else:
            values[name] = int(round(v))
    values['extra_metrics'] = load.extra_metrics
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


def _ingest_activity(club, connector, team, act, loads, athletes, speed_bests, tz, summary):
    provider = connector.provider
    with transaction.atomic():
        match, session = _resolve_context(club, team, provider, act, tz, summary)
        context = {'match': match} if match else {'training_session': session}
        kept = []
        for load in loads:
            incoming = athletes.get(load.athlete_external_id) or NormalizedPlayer(
                external_id=load.athlete_external_id, full_name=f'OpenField athlete {load.athlete_external_id[:8]}',
            )
            player = identity.resolve_player(club, provider, incoming, team=team)
            obj, _ = PlayerLoad.objects.update_or_create(
                club=club, player=player, provider=provider, **context,
                defaults=_load_values(load, connector, speed_bests.get(load.athlete_external_id)),
            )
            kept.append(obj.pk)
            if obj.quality_flags:
                summary.flagged += 1
        # Athletes removed from the activity upstream disappear here too.
        PlayerLoad.objects.filter(club=club, provider=provider, **context).exclude(pk__in=kept).delete()
        summary.loads += len(kept)


def ingest_physical(
    club: Club, connector: PhysicalDataConnector, team: Team, start: datetime, end: datetime,
    *, chunk_size: int = 25,
) -> PhysicalIngestSummary:
    summary = PhysicalIngestSummary()
    tz = ZoneInfo(club.timezone or 'UTC')

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

    # Matches first, so MD codes of training days can count back from them.
    for act in sorted(activities, key=lambda a: (not a.is_match, a.start)):
        try:
            _ingest_activity(club, connector, team, act, loads_by_activity.get(act.external_id, []),
                             athletes, speed_bests, tz, summary)
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
                    'errors': summary.errors[:20]},
    )
    return summary
