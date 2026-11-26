"""
IMPECT connector — event data, lineups and per-match player KPIs (packing, xG…).

Two sources, one format:
  ImpectApiSource   the customer API (https://api.impect.com/v5/customerapi), username +
                    password exchanged for a bearer token. What a club with an IMPECT
                    contract uses; it sees the competitions in that contract.
  ImpectOpenData    IMPECT's free open data (Bundesliga 23/24) — same JSON as the API.
                    Licence: analysis and research only, no redistribution, credit IMPECT.
                    So it's downloaded on demand and never committed, and the UI credits it.

Pitch: IMPECT's `adjCoordinates` are metres from the centre spot with the acting team
attacking +x and its left touchline at +y. Converted to the platform convention
(football.models): x 0..105 from own goal line, y 0..68 from the acting team's left touchline.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import requests

from providers.models import Provider

from .base import (
    EventDataConnector,
    FetchedResource,
    NormalizedAppearance,
    NormalizedCompetition,
    NormalizedEvent,
    NormalizedMatch,
    NormalizedPlayer,
    NormalizedSeason,
    NormalizedTeam,
)

logger = logging.getLogger(__name__)

API_HOST = 'https://api.impect.com'
TOKEN_URL = 'https://login.impect.com/auth/realms/production/protocol/openid-connect/token'
OPEN_DATA_URL = 'https://raw.githubusercontent.com/ImpectAPI/open-data/main/data'
CREDIT = 'Data: IMPECT'

PITCH_X, PITCH_Y = 105.0, 68.0
PERIOD_OFFSET_S = 10000      # IMPECT game clock: period n starts at (n-1) * 10000 s

# IMPECT position → platform position (clubs.Player.Position)
POSITION = {
    'GOALKEEPER': 'GK', 'CENTRAL_DEFENDER': 'CB',
    'LEFT_WINGBACK_DEFENDER': 'FB', 'RIGHT_WINGBACK_DEFENDER': 'FB',
    'DEFENSE_MIDFIELD': 'DM', 'CENTRAL_MIDFIELD': 'CM', 'ATTACKING_MIDFIELD': 'AM',
    'LEFT_WINGER': 'W', 'RIGHT_WINGER': 'W', 'CENTER_FORWARD': 'CF',
}
POSITION_LABEL = {
    'GOALKEEPER': 'Goalkeeper', 'CENTRAL_DEFENDER': 'Centre-back', 'LEFT_WINGBACK_DEFENDER': 'Left wing-back',
    'RIGHT_WINGBACK_DEFENDER': 'Right wing-back', 'DEFENSE_MIDFIELD': 'Defensive midfielder',
    'CENTRAL_MIDFIELD': 'Central midfielder', 'ATTACKING_MIDFIELD': 'Attacking midfielder',
    'LEFT_WINGER': 'Left winger', 'RIGHT_WINGER': 'Right winger', 'CENTER_FORWARD': 'Centre-forward',
}
FOOT = {'LEFT': 'left', 'RIGHT': 'right', 'BOTH': 'both'}

EVENT_TYPE = {
    'PASS': 'pass', 'THROW_IN': 'pass', 'FREE_KICK': 'pass', 'CORNER': 'pass', 'GOAL_KICK': 'pass',
    'KICK_OFF': 'pass', 'RECEPTION': 'ball_receipt', 'DRIBBLE': 'carry', 'SHOT': 'shot',
    'LOOSE_BALL_REGAIN': 'ball_recovery', 'INTERCEPTION': 'interception', 'BLOCK': 'block',
    'CLEARANCE': 'clearance', 'GROUND_DUEL': 'duel', 'AERIAL_DUEL': 'duel', 'FOUL': 'foul_committed',
    'GK_CATCH': 'goalkeeper', 'GK_SAVE': 'goalkeeper',
}
SET_PIECES = {'THROW_IN', 'FREE_KICK', 'CORNER', 'GOAL_KICK', 'KICK_OFF'}
# Event-level KPIs worth keeping on the event row (the rest stay in player match sums).
EVENT_KPIS = {'SHOT_XG', 'POSTSHOT_XG', 'PACKING_XG', 'BYPASSED_OPPONENTS', 'BYPASSED_DEFENDERS', 'GOALS', 'ASSISTS'}


class ImpectError(Exception):
    pass


# --- sources ---------------------------------------------------------------------------------

class ImpectOpenData:
    """IMPECT open data, read from a local folder or fetched from GitHub (optionally cached)."""
    api_version = 'open-data'

    def __init__(self, folder: str | Path | None = None, cache_dir: str | Path | None = None,
                 base_url: str = OPEN_DATA_URL, session: requests.Session | None = None):
        self.folder = Path(folder) if folder else None
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.base_url = base_url.rstrip('/')
        self.session = session or requests.Session()

    def _get(self, rel: str) -> Any:
        for root in (self.folder, self.cache_dir):
            if root and (root / rel).exists():
                return json.loads((root / rel).read_text(encoding='utf-8'))
        resp = self.session.get(f'{self.base_url}/{rel}', timeout=120)
        if resp.status_code == 404:
            raise ImpectError(f'{rel}: not in IMPECT open data')
        resp.raise_for_status()
        if self.cache_dir:
            (self.cache_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / rel).write_bytes(resp.content)
        return resp.json()

    def iterations(self): return self._get('iterations.json')
    def squads(self, it): return self._get(f'squads/squads_{it}.json')
    def players(self, it): return self._get(f'players/players_{it}.json')
    def matches(self, it): return self._get(f'matches/matches_{it}.json')
    def lineups(self, m): return self._get(f'lineups/lineups_{m}.json')
    def events(self, m): return self._get(f'events/events_{m}.json')
    def event_kpis(self, m): return self._get(f'events_kpis/events_kpis_{m}.json')
    def player_kpis(self, m): return self._get(f'player_kpis/player_kpis_{m}.json')
    def kpi_definitions(self): return self._get('kpi_definitions.json')


class ImpectApiSource:
    """IMPECT customer API v5. 10 requests/s per user; we stay well below and retry on 429/5xx."""
    api_version = 'v5'
    MIN_INTERVAL = 0.12

    def __init__(self, username: str, password: str, host: str = API_HOST, token_url: str = TOKEN_URL,
                 session: requests.Session | None = None, sleep=None):
        self.username, self.password = username, password
        self.host, self.token_url = host.rstrip('/'), token_url
        self.session = session or requests.Session()
        self._token: str | None = None
        self._last = 0.0
        self._sleep = sleep or time.sleep

    def _login(self) -> str:
        resp = self.session.post(self.token_url, data={
            'client_id': 'api', 'grant_type': 'password', 'username': self.username, 'password': self.password,
        }, timeout=30)
        if resp.status_code in (400, 401):
            raise ImpectError('IMPECT login refused: check IMPECT_USERNAME / IMPECT_PASSWORD.')
        resp.raise_for_status()
        return resp.json()['access_token']

    def _get(self, path: str) -> Any:
        if self._token is None:
            self._token = self._login()
        url = f'{self.host}/v5/customerapi/{path.lstrip("/")}'
        for attempt in range(4):
            wait = self.MIN_INTERVAL - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            resp = self.session.get(url, headers={'Authorization': f'Bearer {self._token}'}, timeout=120)
            if resp.status_code == 401 and attempt == 0:
                self._token = self._login()          # token expired mid-sync
                continue
            if resp.status_code == 403:
                raise ImpectError(f'{path}: not included in this IMPECT account (403).')
            if resp.status_code == 429 or resp.status_code >= 500:
                self._sleep(min(2 ** attempt, 8))
                continue
            resp.raise_for_status()
            return resp.json().get('data', [])
        raise ImpectError(f'{path}: IMPECT kept refusing (rate limit or server error).')

    def iterations(self): return self._get('iterations/')
    def squads(self, it): return self._get(f'iterations/{it}/squads')
    def players(self, it): return self._get(f'iterations/{it}/players')
    def matches(self, it): return self._get(f'iterations/{it}/matches')
    def lineups(self, m): return self._get(f'matches/{m}')
    def events(self, m): return self._get(f'matches/{m}/events')
    def event_kpis(self, m): return self._get(f'matches/{m}/event-kpis')
    def player_kpis(self, m): return self._get(f'matches/{m}/player-kpis')
    def kpi_definitions(self): return self._get('kpis')


# --- helpers ---------------------------------------------------------------------------------

def _as_one(payload):
    """The API wraps single objects in a list; open data doesn't."""
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
        return payload[0]
    return payload


def parse_clock(game_time: str) -> tuple[int, int]:
    """'45:00.1090' → (45, 0); '90:00.0000 (+05:47.6470)' → (95, 47)."""
    m = re.match(r'(\d+):(\d+)(?:\.\d+)?(?:\s*\(\+(\d+):(\d+)(?:\.\d+)?\))?', game_time or '')
    if not m:
        return 0, 0
    minute, second = int(m.group(1)), int(m.group(2))
    if m.group(3):
        minute += int(m.group(3))
        second = int(m.group(4))
    return minute, second


def to_pitch(point: dict | None) -> tuple[float | None, float | None]:
    adj = (point or {}).get('adjCoordinates') or {}
    x, y = adj.get('x'), adj.get('y')
    if x is None or y is None:
        return None, None
    return (round(min(PITCH_X, max(0.0, x + PITCH_X / 2)), 2),
            round(min(PITCH_Y, max(0.0, PITCH_Y / 2 - y)), 2))


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


# --- connector -------------------------------------------------------------------------------

class ImpectConnector(EventDataConnector):
    provider = Provider.IMPECT
    schema_version = '1'

    def __init__(self, source, account=None, iteration: str | int | None = None):
        super().__init__(account)
        self.source = source
        self.iteration = str(iteration) if iteration is not None else None
        self._squads: dict[str, NormalizedTeam] = {}
        self._players: dict[str, dict] = {}
        self._iteration_info: dict | None = None
        self._kpi_names: dict[int, str] = {}
        self._kpi_rows: list[dict] = []

    @property
    def persist_raw(self) -> bool:
        # Open data can always be fetched again (and may not be copied); customer data is kept.
        return not isinstance(self.source, ImpectOpenData)

    def _res(self, kind: str, key, payload) -> FetchedResource:
        return FetchedResource(kind, str(key), payload, self.source.api_version, persist=self.persist_raw)

    # --- reference data ---
    def load_iteration(self, iteration: str | int) -> dict:
        self.iteration = str(iteration)
        its = self.source.iterations()
        info = next((i for i in its if str(i.get('id')) == self.iteration), None)
        if info is None:
            raise ImpectError(f'Iteration {iteration} is not available ({len(its)} available).')
        self._iteration_info = info
        country = ''
        self._squads = {str(s['id']): NormalizedTeam(str(s['id']), s['name'], country=country)
                        for s in self.source.squads(self.iteration)}
        self._players = {str(p['id']): p for p in self.source.players(self.iteration)}
        return info

    def load_kpi_definitions(self) -> list[dict]:
        rows = self.source.kpi_definitions()
        self._kpi_rows = rows
        self._kpi_names = {int(k['id']): k['name'] for k in rows}
        return rows

    def kpi_catalogue(self) -> list[dict]:
        """For metrics.ProviderMetric: slug = KPI name, name = human label."""
        out = []
        for k in self._kpi_rows:
            details = k.get('details') or {}
            out.append({'slug': k['name'], 'name': details.get('label') or k['name'].replace('_', ' ').title(),
                        'unit_type': '', 'definition': details.get('definition', '')})
        return out

    def competition(self) -> tuple[NormalizedCompetition, NormalizedSeason]:
        info = self._iteration_info or {}
        comp = info.get('competition') or {}
        gender = 'female' if comp.get('gender') == 'FEMALE' else 'male'
        return (NormalizedCompetition(str(comp.get('id', '')), comp.get('name', 'IMPECT competition'), gender=gender),
                NormalizedSeason(str(info.get('id', self.iteration)), info.get('season', '')))

    def normalized_player(self, player_id) -> NormalizedPlayer:
        p = self._players.get(str(player_id)) or {}
        full = ' '.join(x for x in (p.get('firstname'), p.get('lastname')) if x) or p.get('commonname') or f'IMPECT {player_id}'
        return NormalizedPlayer(str(player_id), full, known_name=p.get('commonname') or '',
                                date_of_birth=_date(p.get('birthdate')))

    def player_foot(self, player_id) -> str:
        return FOOT.get((self._players.get(str(player_id)) or {}).get('leg') or '', '')

    def team(self, squad_id) -> NormalizedTeam:
        return self._squads.get(str(squad_id)) or NormalizedTeam(str(squad_id), f'Squad {squad_id}')

    # --- EventDataConnector ---
    def fetch_matches(self, competition_id: str = '', season_id: str = '') -> FetchedResource:
        it = season_id or self.iteration
        return self._res('matches', it, self.source.matches(it))

    def fetch_lineups(self, match_id: str) -> FetchedResource:
        return self._res('lineups', match_id, _as_one(self.source.lineups(match_id)))

    def fetch_events(self, match_id: str) -> FetchedResource:
        return self._res('events', match_id, self.source.events(match_id))

    def fetch_event_kpis(self, match_id: str) -> FetchedResource:
        return self._res('event_kpis', match_id, self.source.event_kpis(match_id))

    def fetch_player_kpis(self, match_id: str) -> FetchedResource:
        return self._res('player_kpis', match_id, _as_one(self.source.player_kpis(match_id)))

    def normalize_matches(self, payload: Any) -> list[NormalizedMatch]:
        comp, season = self.competition()
        out = []
        for m in payload or []:
            if not m.get('available', True):
                continue
            kickoff = datetime.fromisoformat(m['scheduledDate'].replace('Z', '+00:00'))
            md = (m.get('matchDay') or {}).get('name', '')
            out.append(NormalizedMatch(
                external_id=str(m['id']), competition=comp, season=season,
                home_team=self.team(m['homeSquadId']), away_team=self.team(m['awaySquadId']),
                kickoff=kickoff, status='played', stage=md,
            ))
        return out

    def normalize_lineups(self, payload: Any, play_seconds: dict[str, float] | None = None,
                          match_minutes: int = 90, positions: dict[str, str] | None = None) -> list[NormalizedAppearance]:
        """Shirt numbers + starting positions; minutes from the player-KPI play durations,
        substitutes' position from where they played (`positions`: player → IMPECT position)."""
        play_seconds, positions = play_seconds or {}, positions or {}
        out = []
        for side in ('squadHome', 'squadAway'):
            sq = payload.get(side) or {}
            starters = {str(s['playerId']): s.get('position', '') for s in sq.get('startingPositions') or []}
            for p in sq.get('players') or []:
                pid = str(p['id'])
                played = play_seconds.get(pid)
                if pid not in starters and not played:
                    continue                       # on the bench, never came on
                minutes = round((played or 0) / 60)
                started = pid in starters
                out.append(NormalizedAppearance(
                    team_external_id=str(sq['id']), player=self.normalized_player(pid), started=started,
                    position=POSITION.get(starters.get(pid) or positions.get(pid, ''), ''), shirt_number=p.get('shirtNumber'),
                    minute_on=0 if started else max(0, match_minutes - minutes),
                    minute_off=None if (not started or minutes >= match_minutes - 1) else minutes,
                ))
        return out

    def normalize_player_kpis(self, payload: Any) -> list[dict]:
        """One row per player and position: {'squad', 'player', 'position', 'seconds', 'share', 'kpis'}."""
        rows = []
        for side in ('squadHome', 'squadAway'):
            sq = payload.get(side) or {}
            for p in sq.get('players') or []:
                kpis = {}
                for k in p.get('kpis') or []:
                    name = self._kpi_names.get(int(k['kpiId']), str(k['kpiId']))
                    kpis[name] = k.get('value')
                rows.append({'squad': str(sq['id']), 'player': str(p['id']), 'position': p.get('position', ''),
                             'seconds': float(p.get('playDuration') or 0), 'share': p.get('matchShare'), 'kpis': kpis})
        return rows

    def normalize_events(self, payload: Any, event_kpis: Iterable[dict] | None = None) -> Iterable[NormalizedEvent]:
        per_event: dict[int, dict] = {}
        for k in event_kpis or []:
            name = self._kpi_names.get(int(k['kpiId']))
            if name in EVENT_KPIS:
                per_event.setdefault(k['eventId'], {})[name] = k.get('value')
        for seq, e in enumerate(payload or []):
            if not e.get('squadId'):
                continue
            action = e.get('actionType') or ''
            period = int(e.get('periodId') or 1)
            minute, second = parse_clock((e.get('gameTime') or {}).get('gameTime', ''))
            secs = float((e.get('gameTime') or {}).get('gameTimeInSec') or 0)
            x, y = to_pitch(e.get('start'))
            ex, ey = to_pitch(e.get('end'))
            kpis = per_event.get(e.get('id'), {})
            player = e.get('player') or {}
            attrs = {'action': e.get('action'), 'action_type': action, 'phase': e.get('phase'),
                     'body_part': e.get('bodyPart'), 'position': player.get('position'),
                     'pressure': e.get('pressure'), 'opponents': e.get('opponents'), **{k.lower(): v for k, v in kpis.items()}}
            if action in SET_PIECES:
                attrs['set_piece'] = action.lower()
            if e.get('shot'):
                attrs['shot'] = e['shot']
            yield NormalizedEvent(
                external_id=str(e.get('id')), sequence=seq, period=period, minute=minute, second=second,
                period_ms=max(0, int((secs - (period - 1) * PERIOD_OFFSET_S) * 1000)),
                event_type=EVENT_TYPE.get(action, 'other'), team_external_id=str(e['squadId']),
                player_external_id=str(player['id']) if player.get('id') else None,
                outcome=(e.get('result') or '').lower(), possession=e.get('sequenceIndex'),
                under_pressure=bool(e.get('pressure')), x=x, y=y, end_x=ex, end_y=ey,
                xg=kpis.get('SHOT_XG') if action == 'SHOT' else None,
                attributes={k: v for k, v in attrs.items() if v is not None},
            )
