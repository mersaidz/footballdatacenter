"""
Provider-agnostic ingest pipeline. Connector in, database rows out.

Guarantees:
- Idempotent: re-running an ingest for the same match yields the same rows
  (events are replaced per (match, provider); raw payloads dedupe on SHA-256).
- Atomic per match: a failure half-way leaves the previous good state intact.
- Audited: every sync writes an AuditLog row, success or failure.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from clubs.models import Club, Team
from core.models import AuditLog
from core.sanitize import sanitize_payload
from core.services.audit import log_event
from football.models import Event, Match, MatchAppearance
from providers.connectors.base import BaseConnector, EventDataConnector, FetchedResource, NormalizedMatch
from providers.models import ExternalIdentity, RawPayload

from . import identity

logger = logging.getLogger(__name__)

EVENT_BATCH_SIZE = 1000
# Periods 1-2 regular time, 3-4 extra time, 5 = penalty shootout (not "minutes played").
MAX_OPEN_PLAY_PERIOD = 4


@dataclass
class MatchIngestResult:
    match_id: int
    created: bool
    appearances: int = 0
    events: int = 0
    new_players: int = 0
    players_needing_review: int = 0


@dataclass
class IngestSummary:
    matches: list[MatchIngestResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_events(self) -> int:
        return sum(m.events for m in self.matches)


def store_raw(club: Club, connector: BaseConnector, resource: FetchedResource) -> RawPayload:
    clean = sanitize_payload(resource.payload)
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    raw, _ = RawPayload.objects.get_or_create(
        club=club, provider=connector.provider, resource_type=resource.resource_type,
        external_id=resource.external_id, sha256=digest,
        defaults={
            'payload': clean,
            'schema_version': connector.schema_version,
            'provider_api_version': resource.provider_api_version,
        },
    )
    return raw


def ingest_match(club: Club, connector: EventDataConnector, normalized: NormalizedMatch) -> MatchIngestResult:
    provider = connector.provider
    lineups_res = connector.fetch_lineups(normalized.external_id)
    events_res = connector.fetch_events(normalized.external_id)

    with transaction.atomic():
        store_raw(club, connector, lineups_res)
        store_raw(club, connector, events_res)

        match, created = identity.resolve_match(club, provider, normalized)
        teams_by_ext = {
            normalized.home_team.external_id: match.home_team,
            normalized.away_team.external_id: match.away_team,
        }
        result = MatchIngestResult(match_id=match.pk, created=created)

        player_identity_count_before = _player_identity_counts(club, provider)

        # Events first: match length comes from the last event, minutes played need it.
        normalized_events = list(connector.normalize_events(events_res.payload))
        open_play = [e for e in normalized_events if e.period <= MAX_OPEN_PLAY_PERIOD]
        if open_play:
            match.duration_minutes = max(e.minute for e in open_play) + 1
            match.save(update_fields=['duration_minutes', 'updated_at'])

        players_by_ext = {}
        appearances = []
        for app in connector.normalize_lineups(lineups_res.payload):
            team = teams_by_ext[app.team_external_id]
            player = identity.resolve_player(club, provider, app.player, team=team)
            players_by_ext[app.player.external_id] = player
            appearances.append(_build_appearance(club, match, team, player, app))

        MatchAppearance.objects.filter(match=match, player__in=[a.player for a in appearances]).delete()
        MatchAppearance.objects.bulk_create(appearances)
        result.appearances = len(appearances)

        Event.objects.filter(match=match, provider=provider).delete()
        rows = []
        for ev in normalized_events:
            player = players_by_ext.get(ev.player_external_id) if ev.player_external_id else None
            rows.append(Event(
                club=club, match=match, team=teams_by_ext[ev.team_external_id], player=player,
                provider=provider, external_id=ev.external_id, sequence=ev.sequence,
                period=ev.period, minute=ev.minute, second=ev.second, period_ms=ev.period_ms,
                event_type=ev.event_type, outcome=ev.outcome, possession=ev.possession,
                under_pressure=ev.under_pressure, x=ev.x, y=ev.y, end_x=ev.end_x, end_y=ev.end_y,
                xg=ev.xg, attributes=ev.attributes,
            ))
        Event.objects.bulk_create(rows, batch_size=EVENT_BATCH_SIZE)
        result.events = len(rows)

        after = _player_identity_counts(club, provider)
        result.new_players = after['created'] - player_identity_count_before['created']
        result.players_needing_review = after['suggested'] - player_identity_count_before['suggested']

    return result


def _build_appearance(club, match: Match, team: Team, player, app) -> MatchAppearance:
    end = app.minute_off if app.minute_off is not None else (match.duration_minutes or 90)
    start = app.minute_on or 0
    return MatchAppearance(
        club=club, match=match, team=team, player=player, started=app.started,
        position=app.position, shirt_number=app.shirt_number,
        minute_on=start, minute_off=app.minute_off, minutes_played=max(0, end - start),
    )


def _player_identity_counts(club, provider) -> dict[str, int]:
    qs = ExternalIdentity.objects.filter(club=club, provider=provider, entity_type='player')
    return {
        'created': qs.filter(method=ExternalIdentity.Method.CREATED).count(),
        'suggested': qs.filter(status=ExternalIdentity.Status.SUGGESTED).count(),
    }


def ingest_season(
    club: Club, connector: EventDataConnector, competition_id: str, season_id: str, *,
    match_ids: set[str] | None = None, limit: int | None = None, own_team_name: str | None = None,
) -> IngestSummary:
    summary = IngestSummary()
    matches_res = connector.fetch_matches(competition_id, season_id)
    store_raw(club, connector, matches_res)
    normalized = sorted(connector.normalize_matches(matches_res.payload), key=lambda m: m.kickoff)

    if match_ids:
        normalized = [m for m in normalized if m.external_id in match_ids]
    if own_team_name:
        target = identity.normalize_name(own_team_name)
        normalized = [m for m in normalized
                      if target in (identity.normalize_name(m.home_team.name), identity.normalize_name(m.away_team.name))]
    if limit:
        normalized = normalized[:limit]

    for nm in normalized:
        try:
            summary.matches.append(ingest_match(club, connector, nm))
        except Exception as exc:  # noqa: BLE001 — one bad match must not stop the season
            logger.exception('Ingest failed for %s match %s', connector.provider, nm.external_id)
            summary.errors.append(f'{nm.external_id}: {exc}')

    if own_team_name:
        Team.objects.filter(club=club, name__iexact=own_team_name).update(is_own=True)

    _touch_account(club, connector)
    log_event(
        action=AuditLog.Action.SYNC_FAILED if summary.errors and not summary.matches else AuditLog.Action.SYNC_SUCCESS,
        club=club, provider=connector.provider,
        extra_info={
            'competition_id': competition_id, 'season_id': season_id,
            'matches': len(summary.matches), 'events': summary.total_events, 'errors': summary.errors[:20],
        },
    )
    return summary


def _touch_account(club, connector):
    if connector.account is not None:
        connector.account.last_synced_at = timezone.now()
        connector.account.save(update_fields=['last_synced_at', 'updated_at'])
