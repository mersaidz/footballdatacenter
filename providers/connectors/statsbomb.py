"""
StatsBomb Open Data connector — https://github.com/statsbomb/open-data

Free, licence-friendly event data (World Cups, Euros, Messi's La Liga
career, WSL, …). Used for development and demos until a club plugs in its
own provider keys. The commercial StatsBomb API uses the same JSON shapes,
so this connector is also the starting point for the paid feed.

StatsBomb pitch: 120 x 80 yards-ish units, origin top-left, every event
expressed from the acting team's attacking direction (left → right).
We rescale to our 105 x 68 m convention (see football.models).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from django.conf import settings

from football.models import PITCH_LENGTH_M, PITCH_WIDTH_M
from providers.models import Provider

from .base import (
    BaseConnector,
    FetchedResource,
    NormalizedAppearance,
    NormalizedCompetition,
    NormalizedEvent,
    NormalizedMatch,
    NormalizedPlayer,
    NormalizedSeason,
    NormalizedTeam,
)

SB_LENGTH = 120.0
SB_WIDTH = 80.0

EVENT_TYPE_MAP = {
    'Pass': 'pass',
    'Shot': 'shot',
    'Carry': 'carry',
    'Dribble': 'dribble',
    'Ball Receipt*': 'ball_receipt',
    'Pressure': 'pressure',
    'Duel': 'duel',
    '50/50': 'duel',
    'Interception': 'interception',
    'Ball Recovery': 'ball_recovery',
    'Clearance': 'clearance',
    'Block': 'block',
    'Foul Committed': 'foul_committed',
    'Foul Won': 'foul_won',
    'Goal Keeper': 'goalkeeper',
    'Miscontrol': 'miscontrol',
    'Dispossessed': 'dispossessed',
}

# Structural / bookkeeping events carry no football action — not stored as Events.
SKIPPED_EVENT_TYPES = {
    'Starting XI', 'Half Start', 'Half End', 'Tactical Shift', 'Substitution',
    'Player On', 'Player Off', 'Injury Stoppage', 'Referee Ball-Drop', 'Camera On', 'Camera off',
}

# Type-specific sub-objects we keep in Event.attributes (minus bulky freeze frames).
_ATTRIBUTE_KEYS = ('50_50', 'pass', 'shot', 'carry', 'dribble', 'duel', 'goalkeeper', 'clearance',
                   'interception', 'foul_committed', 'ball_receipt', 'block')


# Type name → key of the type-specific sub-object, where it isn't just snake_case.
_SUBKEY_OVERRIDES = {'Goal Keeper': 'goalkeeper', '50/50': '50_50'}


def to_metres(location: list[float] | None) -> tuple[float | None, float | None]:
    if not location or len(location) < 2:
        return None, None
    x = round(location[0] / SB_LENGTH * PITCH_LENGTH_M, 2)
    y = round(location[1] / SB_WIDTH * PITCH_WIDTH_M, 2)
    return x, y


def _clock_to_ms(ts: str) -> int:
    # "00:47:12.345" → ms since period start
    h, m, s = ts.split(':')
    return int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def _mmss_to_minute(value: str | None) -> int | None:
    if not value:
        return None
    m, _ = value.split(':')
    return int(m)


def _snake(name: str) -> str:
    return name.strip().lower().replace(' ', '_').replace('-', '_')


class StatsBombOpenConnector(BaseConnector):
    provider = Provider.STATSBOMB_OPEN
    schema_version = 'sb-open-1'

    def __init__(self, account=None, base_url: str | None = None, data_dir: str | None = None):
        super().__init__(account)
        self.base_url = (base_url or settings.STATSBOMB_OPEN_DATA_BASE_URL).rstrip('/')
        local = data_dir if data_dir is not None else settings.STATSBOMB_OPEN_DATA_DIR
        self.data_dir = Path(local) / 'data' if local else None
        self.session = requests.Session()

    # --- fetch -----------------------------------------------------------------
    def _get(self, rel_path: str) -> Any:
        if self.data_dir is not None:
            with open(self.data_dir / rel_path, encoding='utf-8') as fh:
                return json.load(fh)
        resp = self.session.get(f'{self.base_url}/{rel_path}', timeout=settings.PROVIDER_HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def fetch_competitions(self) -> FetchedResource:
        return FetchedResource('competitions', 'all', self._get('competitions.json'))

    def fetch_matches(self, competition_id: str, season_id: str) -> FetchedResource:
        return FetchedResource(
            'matches', f'{competition_id}:{season_id}', self._get(f'matches/{competition_id}/{season_id}.json'),
        )

    def fetch_lineups(self, match_id: str) -> FetchedResource:
        return FetchedResource('lineups', str(match_id), self._get(f'lineups/{match_id}.json'))

    def fetch_events(self, match_id: str) -> FetchedResource:
        return FetchedResource('events', str(match_id), self._get(f'events/{match_id}.json'))

    # --- normalise -------------------------------------------------------------
    @staticmethod
    def _team(raw: dict, prefix: str) -> NormalizedTeam:
        gender = raw.get(f'{prefix}_gender') or 'male'
        return NormalizedTeam(
            external_id=str(raw[f'{prefix}_id']),
            name=raw[f'{prefix}_name'],
            gender='female' if gender.lower().startswith('f') else 'male',
            country=(raw.get('country') or {}).get('name', ''),
        )

    def normalize_matches(self, payload: list[dict]) -> list[NormalizedMatch]:
        matches = []
        for m in payload:
            comp = m.get('competition') or {}
            season = m.get('season') or {}
            kickoff_time = (m.get('kick_off') or '00:00:00.000')[:8]
            kickoff = datetime.fromisoformat(f"{m['match_date']}T{kickoff_time}").replace(tzinfo=timezone.utc)
            home = self._team(m['home_team'], 'home_team')
            matches.append(NormalizedMatch(
                external_id=str(m['match_id']),
                competition=NormalizedCompetition(
                    external_id=str(comp['competition_id']),
                    name=comp.get('competition_name', ''),
                    country=comp.get('country_name', ''),
                    gender=home.gender,
                ) if comp else None,
                season=NormalizedSeason(
                    external_id=str(season['season_id']), name=season.get('season_name', ''),
                ) if season else None,
                home_team=home,
                away_team=self._team(m['away_team'], 'away_team'),
                kickoff=kickoff,
                status='played' if m.get('match_status') == 'available' else 'scheduled',
                home_score=m.get('home_score'),
                away_score=m.get('away_score'),
                stage=(m.get('competition_stage') or {}).get('name', ''),
                venue=(m.get('stadium') or {}).get('name', ''),
            ))
        return matches

    def normalize_lineups(self, payload: list[dict]) -> list[NormalizedAppearance]:
        appearances = []
        for team in payload:
            team_id = str(team['team_id'])
            for p in team.get('lineup', []):
                positions = p.get('positions') or []
                if not positions:
                    continue  # named in the squad, never entered the pitch
                first, last = positions[0], positions[-1]
                appearances.append(NormalizedAppearance(
                    team_external_id=team_id,
                    player=NormalizedPlayer(
                        external_id=str(p['player_id']),
                        full_name=p['player_name'],
                        known_name=p.get('player_nickname') or '',
                        nationality=(p.get('country') or {}).get('name', ''),
                    ),
                    started=first.get('start_reason') == 'Starting XI',
                    position=first.get('position', ''),
                    shirt_number=p.get('jersey_number'),
                    minute_on=_mmss_to_minute(first.get('from')) or 0,
                    minute_off=_mmss_to_minute(last.get('to')),
                ))
        return appearances

    def normalize_events(self, payload: list[dict]) -> Iterable[NormalizedEvent]:
        for e in payload:
            type_name = (e.get('type') or {}).get('name', '')
            if type_name in SKIPPED_EVENT_TYPES:
                continue
            event_type = EVENT_TYPE_MAP.get(type_name, 'other')

            x, y = to_metres(e.get('location'))
            end_x = end_y = None
            sub = e.get(_SUBKEY_OVERRIDES.get(type_name, _snake(type_name).rstrip('*'))) or {}
            if 'end_location' in sub:
                end_x, end_y = to_metres(sub['end_location'])

            outcome = ''
            if sub.get('outcome'):
                outcome = _snake(sub['outcome']['name'])
            elif event_type == 'pass':
                outcome = 'complete'  # StatsBomb omits outcome for successful passes

            attributes = {k: v for k, v in e.items() if k in _ATTRIBUTE_KEYS}
            if 'shot' in attributes:
                attributes['shot'] = {k: v for k, v in attributes['shot'].items() if k != 'freeze_frame'}
            if event_type == 'other':
                attributes['provider_type'] = type_name

            yield NormalizedEvent(
                external_id=e['id'],
                sequence=e['index'],
                period=e['period'],
                minute=e['minute'],
                second=e['second'],
                period_ms=_clock_to_ms(e['timestamp']),
                event_type=event_type,
                team_external_id=str(e['team']['id']),
                player_external_id=str(e['player']['id']) if e.get('player') else None,
                outcome=outcome,
                possession=e.get('possession'),
                under_pressure=bool(e.get('under_pressure')),
                x=x, y=y, end_x=end_x, end_y=end_y,
                xg=(e.get('shot') or {}).get('statsbomb_xg'),
                attributes=attributes,
            )
