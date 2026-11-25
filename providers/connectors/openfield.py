"""
Catapult OpenField Connect API (v6) connector — read-only.

Shapes below were verified against a live EU account with
scripts/openfield_probe.py (Nov 2026):

  GET  /athletes                       → list; date_of_birth = epoch seconds
  GET  /activities?startTime&endTime    → list; times = epoch seconds; tag_list = [{tag_type_name, name}]
  POST /stats                          → list of rows, one per athlete × activity when
                                          group_by=["athlete","activity"]
  GET  /parameters                     → ~1900 metric slugs for this account

Units in /stats: distance in metres, durations in seconds, velocity in m/s.
Rate limits seen: 1001 req/window in general, 150 for /stats → stats are
fetched for many activities per call (STATS_CHUNK).

Which velocity band counts as "high-speed running" is an account setting
(OpenField → Settings → Bands), so the slug → field mapping is configurable
per club in ProviderAccount.config["metric_map"].
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import requests
from django.conf import settings

from providers.models import Provider

from .base import (
    FetchedResource,
    NormalizedActivity,
    NormalizedLoad,
    NormalizedPeriod,
    NormalizedPlayer,
    PhysicalDataConnector,
)

logger = logging.getLogger(__name__)

REGION_BASE_URLS = {
    'eu': 'https://connect-eu.catapultsports.com/api/v6',
    'us': 'https://connect-us.catapultsports.com/api/v6',
    'au': 'https://connect-au.catapultsports.com/api/v6',
}

STATS_CHUNK = 25

# field on PlayerLoad → OpenField slugs (summed). HSR = Band 5 and above,
# sprint = Band 6 and above; the km/h those bands start at is the club's own
# setting and is recorded via ProviderAccount.config["hsr_threshold_kmh"] /
# ["sprint_threshold_kmh"]. Override slugs per club with config["metric_map"].
DEFAULT_METRIC_MAP: dict[str, list[str]] = {
    'total_distance_m': ['total_distance'],
    'hsr_distance_m': ['velocity_band5_total_distance', 'velocity_band6_total_distance',
                       'velocity_band7_total_distance', 'velocity_band8_total_distance'],
    'sprint_distance_m': ['velocity_band6_total_distance', 'velocity_band7_total_distance',
                          'velocity_band8_total_distance'],
    'sprint_count': [],
    'accelerations': ['gen2_acceleration_band7plus_total_effort_count'],
    'decelerations': ['gen2_acceleration_band2plus_total_effort_count'],
    'player_load': ['total_player_load'],
}
DURATION_SLUGS = ['field_time', 'total_duration']    # seconds; first available wins
MAX_SPEED_SLUG = 'max_vel'                           # m/s
# Requested on every sync and kept verbatim in PlayerLoad.extra_metrics.
EXTRA_SLUGS = [
    'high_speed_distance', 'player_load_per_minute', 'ima_band2_accel_count', 'ima_band2_decel_count',
    'velocity_band4_total_distance', 'velocity_band5_total_distance', 'velocity_band6_total_distance',
    'velocity_band7_total_distance', 'velocity_band8_total_distance',
]
CONTEXT_FIELDS = ['athlete_id', 'activity_id', 'date', 'start_time', 'end_time']

DAY_CODE_TAG_TYPE = 'DayCode'
PARTICIPATION_TAG_TYPE = 'Participation'
DEFAULT_PERIOD_ROLE_TAG_TYPE = 'Period Type'
PERIOD_STATS_CHUNK = 10
MATCH_DAY_CODES = {'MD'}

INTEGER_FIELDS = {'sprint_count', 'accelerations', 'decelerations'}


class OpenFieldError(Exception):
    pass


class OpenFieldClient:
    """Thin HTTP client: bearer auth, retries on 429/5xx, token never in errors or logs."""

    def __init__(self, base_url: str, token: str, *, timeout: int | None = None, max_retries: int = 4,
                 session: requests.Session | None = None, sleep: Callable[[float], None] | None = None):
        if not token:
            raise OpenFieldError('OpenField API token is missing (OPENFIELD_API_TOKEN or ProviderAccount.api_key)')
        self.base_url = base_url.rstrip('/')
        self._token = token
        self.timeout = timeout or settings.PROVIDER_HTTP_TIMEOUT
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep = sleep or (lambda seconds: time.sleep(seconds))

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request('GET', path, params=params)

    def post(self, path: str, body: dict) -> Any:
        return self._request('POST', path, json=body)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = {'Authorization': f'Bearer {self._token}', 'Accept': 'application/json'}
        last_error = ''
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(method, self.base_url + path, headers=headers,
                                            timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_error = f'{type(exc).__name__}'
                self._sleep(2 ** attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get('Retry-After')
                wait = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                last_error = f'HTTP {resp.status_code}'
                logger.warning('OpenField %s %s → %s, retrying in %ss', method, path, resp.status_code, wait)
                self._sleep(wait)
                continue
            if resp.status_code >= 400:
                detail = resp.text[:300].replace(self._token, '<token>')
                raise OpenFieldError(f'{method} {path} → HTTP {resp.status_code}: {detail}')
            return resp.json() if resp.content else None
        raise OpenFieldError(f'{method} {path} failed after {self.max_retries} attempts ({last_error})')


def _epoch_to_dt(value) -> datetime | None:
    if value in (None, '', 0):
        return None
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=float(value))


def _epoch_to_date(value) -> date | None:
    dt = _epoch_to_dt(value)
    return dt.date() if dt else None


def _num(value) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tags(raw_tags) -> dict[str, list[str]]:
    """Tag objects → {tag_type_name: [names]}; bare strings (no type) go under "Other"."""
    out: dict[str, list[str]] = {}
    for t in raw_tags or []:
        if isinstance(t, dict):
            out.setdefault(t.get('tag_type_name') or 'Other', []).append(t.get('name') or t.get('tag_name') or '')
        elif isinstance(t, str):
            out.setdefault('Other', []).append(t)
    return out


class OpenFieldConnector(PhysicalDataConnector):
    provider = Provider.CATAPULT_OPENFIELD
    schema_version = 'of-connect-v6-1'

    def __init__(self, account=None, *, token: str | None = None, region: str | None = None,
                 base_url: str | None = None, client: OpenFieldClient | None = None,
                 metric_map: dict[str, list[str]] | None = None, match_name_pattern: str | None = None):
        super().__init__(account)
        config = (account.config if account is not None else None) or {}
        self.region = (region or config.get('region') or os.getenv('OPENFIELD_REGION') or 'eu').lower()
        if client is None:
            token = token or (account.api_key if account is not None else '') or os.getenv('OPENFIELD_API_TOKEN', '')
            url = base_url or (account.base_url if account is not None else '') or REGION_BASE_URLS.get(self.region)
            if not url:
                raise OpenFieldError(f'Unknown OpenField region {self.region!r}')
            client = OpenFieldClient(url, token)
        self.client = client
        self.metric_map = {**DEFAULT_METRIC_MAP, **(config.get('metric_map') or {}), **(metric_map or {})}
        pattern = match_name_pattern or config.get('match_name_pattern')
        self.match_name_re = re.compile(pattern, re.I) if pattern else None
        self._available: set[str] | None = None
        # Band setup of this account (OpenField → Settings → Bands), e.g. 21 / 24 km/h.
        self.hsr_threshold_kmh = _num(config.get('hsr_threshold_kmh'))
        self.sprint_threshold_kmh = _num(config.get('sprint_threshold_kmh'))
        if config.get('max_speed_cap_kmh'):
            self.max_speed_cap_kmh = float(config['max_speed_cap_kmh'])
        self.period_role_tag_type = config.get('period_role_tag_type', DEFAULT_PERIOD_ROLE_TAG_TYPE)

    # --- fetch -----------------------------------------------------------------
    def fetch_catalogue(self) -> FetchedResource:
        payload = self.client.get('/parameters') or []
        self._available = {p['slug'] for p in payload if isinstance(p, dict) and p.get('slug')}
        return FetchedResource('parameters', 'all', payload, 'v6')

    def available_parameters(self) -> set[str]:
        if self._available is None:
            self.fetch_catalogue()
        return self._available

    def requested_slugs(self) -> list[str]:
        wanted = {s for slugs in self.metric_map.values() for s in slugs}
        wanted |= set(DURATION_SLUGS) | {MAX_SPEED_SLUG} | set(EXTRA_SLUGS) | set(self.extra_slugs)
        available = self.available_parameters()
        missing = sorted(wanted - available)
        if missing:
            logger.info('OpenField slugs not available on this account, skipped: %s', missing)
        return CONTEXT_FIELDS + sorted(wanted & available)

    def fetch_athletes(self) -> FetchedResource:
        return FetchedResource('athletes', 'all', self.client.get('/athletes') or [], 'v6')

    def fetch_activities(self, start: datetime, end: datetime) -> FetchedResource:
        params = {'startTime': int(start.timestamp()), 'endTime': int(end.timestamp())}
        payload = self.client.get('/activities', params=params) or []
        return FetchedResource('activities', f'{params["startTime"]}-{params["endTime"]}', payload, 'v6')

    def _stats(self, activity_ids: list[str], group_by: list[str], resource: str) -> FetchedResource:
        body = {
            'parameters': self.requested_slugs() + (['period_id', 'period_name'] if 'period' in group_by else []),
            'filters': [{'name': 'activity_id', 'comparison': '=', 'values': list(activity_ids)}],
            'group_by': group_by,
        }
        key = hashlib.sha1(','.join(sorted(activity_ids)).encode()).hexdigest()[:16]
        return FetchedResource(resource, key, self.client.post('/stats', body) or [], 'v6')

    def fetch_activity_stats(self, activity_ids: list[str]) -> FetchedResource:
        return self._stats(activity_ids, ['athlete', 'activity'], 'stats')

    def fetch_period_stats(self, activity_ids: list[str]) -> FetchedResource:
        return self._stats(activity_ids, ['athlete', 'period'], 'period_stats')

    def fetch_activity_periods(self, activity_id: str) -> FetchedResource:
        return FetchedResource('periods', activity_id, self.client.get(f'/activities/{activity_id}/periods') or [], 'v6')

    def fetch_activity_athletes(self, activity_id: str) -> FetchedResource:
        return FetchedResource('activity_athletes', activity_id,
                               self.client.get(f'/activities/{activity_id}/athletes') or [], 'v6')

    # --- normalise -------------------------------------------------------------
    def normalize_athletes(self, payload: list[dict]) -> list[NormalizedPlayer]:
        players = []
        for a in payload:
            if a.get('is_deleted'):
                continue
            full = f"{a.get('first_name', '').strip()} {a.get('last_name', '').strip()}".strip()
            players.append(NormalizedPlayer(
                external_id=str(a['id']),
                full_name=full or a.get('nickname') or str(a['id']),
                known_name=(a.get('nickname') or '').strip(),
                date_of_birth=_epoch_to_date(a.get('date_of_birth')),
            ))
        return players

    def athlete_max_speeds(self, athletes_payload: list[dict]) -> dict[str, float]:
        # velocity_max is the athlete's max speed in m/s (shown as "Max" in Settings → Bands).
        out = {}
        for a in athletes_payload or []:
            v = _num(a.get('velocity_max'))
            if v and v > 0:
                out[str(a['id'])] = round(v * 3.6 if v < 15 else v, 1)
        return out

    def normalize_activities(self, payload: list[dict]) -> list[NormalizedActivity]:
        activities = []
        for a in payload:
            if a.get('is_deleted'):
                continue
            # /activities puts tag objects in tag_list, /activities/{id} puts them in tags.
            candidates = [a.get('tag_list') or [], a.get('tags') or []]
            tags = _tags(next((c for c in candidates if c and isinstance(c[0], dict)), candidates[0]))
            day_code = (tags.get(DAY_CODE_TAG_TYPE) or [''])[0]
            name = a.get('name') or ''
            is_match = day_code in MATCH_DAY_CODES or bool(self.match_name_re and self.match_name_re.search(name))
            activities.append(NormalizedActivity(
                external_id=str(a['id']),
                name=name,
                start=_epoch_to_dt(a['start_time']),
                end=_epoch_to_dt(a.get('end_time')),
                day_code=day_code,
                is_match=is_match,
                tags=tags,
                periods=tuple(self.normalize_periods(a.get('periods') or [])),
            ))
        return activities

    def normalize_periods(self, payload: list[dict]) -> list[NormalizedPeriod]:
        periods = []
        for p in payload or []:
            if p.get('is_deleted') or not p.get('start_time') or not p.get('end_time'):
                continue
            candidates = [p.get('tags') or [], p.get('tag_list') or []]
            tag_src = next((c for c in candidates if c and isinstance(c[0], dict)), [])
            periods.append(NormalizedPeriod(
                external_id=str(p['id']),
                name=(p.get('name') or '').strip() or 'Unnamed period',
                start=_epoch_to_dt(p['start_time'] + (p.get('start_centiseconds') or 0) / 100),
                end=_epoch_to_dt(p['end_time'] + (p.get('end_centiseconds') or 0) / 100),
                tags=_tags(tag_src),
            ))
        return periods

    def normalize_participation(self, payload: list[dict]) -> dict[str, str]:
        out = {}
        for a in payload or []:
            tags = _tags(next((c for c in (a.get('tags') or [], a.get('tag_list') or [])
                               if c and isinstance(c[0], dict)), []))
            value = ((tags.get(PARTICIPATION_TAG_TYPE) or [''])[0]).strip().lower()
            if not value:
                continue
            if value == 'full':
                out[str(a['id'])] = 'full'
            elif value.startswith('part'):
                out[str(a['id'])] = 'partial'
            elif value.startswith('alt'):
                out[str(a['id'])] = 'alternate'
            else:
                out[str(a['id'])] = 'other'
        return out

    def normalize_stats(self, payload: list[dict], by_period: bool = False) -> list[NormalizedLoad]:
        loads = []
        for row in payload:
            if not row.get('athlete_id') or not row.get('activity_id'):
                continue
            if by_period and not row.get('period_id'):
                continue
            values: dict[str, Any] = {}
            for field_name, slugs in self.metric_map.items():
                nums = [_num(row.get(s)) for s in slugs if s in row]
                nums = [n for n in nums if n is not None]
                if nums:
                    total = sum(nums)
                    values[field_name] = int(round(total)) if field_name in INTEGER_FIELDS else total

            seconds = next((_num(row[s]) for s in DURATION_SLUGS if _num(row.get(s)) is not None), None)
            if seconds is not None:
                values['duration_min'] = round(seconds / 60, 2)

            vmax = _num(row.get(MAX_SPEED_SLUG))
            if vmax is not None:
                # API returns m/s. Guard: nobody runs 15 m/s (54 km/h), so a larger value is already km/h.
                values['max_speed_kmh'] = round(vmax * 3.6 if vmax < 15 else vmax, 1)

            extra = {s: row[s] for s in (*EXTRA_SLUGS, *self.extra_slugs) if s in row}
            loads.append(NormalizedLoad(
                activity_external_id=str(row['activity_id']),
                athlete_external_id=str(row['athlete_id']),
                # Activity-level rows also carry a period_id (the first period): only trust it when grouped by period.
                period_external_id=str(row['period_id']) if by_period else None,
                extra_metrics=extra,
                **values,
            ))
        return loads
