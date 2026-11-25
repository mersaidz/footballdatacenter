#!/usr/bin/env python3
"""
OpenField Connect API probe — discovers the real response shapes before we
write the connector.

    python3 scripts/openfield_probe.py            # reads OPENFIELD_API_TOKEN from .env
    python3 scripts/openfield_probe.py --days 730 # look further back for activities

Standard library only (Python 3.8+), no Django, no pip install.
Writes `openfield_probe_report.json` (git-ignored) next to this project.

Privacy: the token is never printed or saved. The report contains field
names, types and counts; sample values are kept only for non-personal
fields — names are masked ("J***"), birth dates / emails / phones dropped.
Read-only: GET requests plus POST /stats (a query, not a write).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGION_HOSTS = {
    'eu': 'https://connect-eu.catapultsports.com/api/v6',
    'us': 'https://connect-us.catapultsports.com/api/v6',
    'au': 'https://connect-au.catapultsports.com/api/v6',
}

# Personal fields: value replaced, type kept.
MASK_KEYS = re.compile(r'(^|_)(first_name|last_name|nickname|athlete_name|full_name|player_name|owner)$', re.I)
DROP_KEYS = re.compile(r'(email|phone|date_of_birth|dob|birth|address|token|password|secret)', re.I)

# Metrics we expect to need; the probe checks which slugs exist on this account.
CANDIDATE_PARAMS = [
    'total_distance', 'total_duration', 'field_time', 'total_player_load', 'max_vel',
    'high_speed_distance', 'velocity_band4_total_distance', 'velocity_band5_total_distance',
    'velocity_band6_total_distance', 'velocity_band7_total_distance', 'velocity_band8_total_distance',
    'gen2_acceleration_band2plus_total_effort_count', 'gen2_deceleration_band2plus_total_effort_count',
    'gen2_acceleration_band3plus_total_effort_count', 'gen2_deceleration_band3plus_total_effort_count',
    'ima_band2_accel_count', 'ima_band2_decel_count', 'hsr_efforts', 'player_load_per_minute',
]


# --- helpers -------------------------------------------------------------------

def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def type_name(v) -> str:
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, int):
        return 'int'
    if isinstance(v, float):
        return 'float'
    if isinstance(v, str):
        return 'str'
    if isinstance(v, list):
        return 'list'
    if isinstance(v, dict):
        return 'object'
    return type(v).__name__


def safe_sample(key: str, v):
    if DROP_KEYS.search(key):
        return f'<{type_name(v)} hidden>'
    if MASK_KEYS.search(key) and isinstance(v, str) and v:
        return v[0] + '***'
    if isinstance(v, str) and len(v) > 80:
        return v[:80] + '…'
    return v


def schema(value, depth: int = 0, max_depth: int = 4, key: str = ''):
    """Describe a JSON value: types, keys, one safe sample per scalar field."""
    if isinstance(value, dict):
        if depth >= max_depth:
            return {'type': 'object', 'keys': sorted(value)[:50]}
        return {'type': 'object',
                'fields': {k: schema(v, depth + 1, max_depth, k) for k, v in list(value.items())[:80]}}
    if isinstance(value, list):
        out = {'type': 'list', 'length': len(value)}
        if value:
            # merge the first few items so optional fields show up
            items = value[:5]
            if all(isinstance(i, dict) for i in items):
                merged = {}
                for item in items:
                    for k, v in item.items():
                        if k not in merged or merged[k] is None:
                            merged[k] = v
                out['item'] = schema(merged, depth + 1, max_depth, key)
            else:
                out['item'] = schema(items[0], depth + 1, max_depth, key)
        return out
    return {'type': type_name(value), 'sample': safe_sample(key, value)}


class Client:
    def __init__(self, base: str, token: str, timeout: int = 60):
        self.base = base.rstrip('/')
        self._token = token
        self.timeout = timeout
        self.calls = []

    def request(self, method: str, path: str, params: dict | None = None, body=None, label: str = ''):
        url = self.base + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Authorization': f'Bearer {self._token}', 'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'

        record = {'label': label or path, 'method': method, 'path': path, 'params': params or {}}
        if body is not None:
            record['body'] = body
        for attempt in range(4):
            started = time.monotonic()
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    record.update(status=resp.status,
                                  elapsed_ms=int((time.monotonic() - started) * 1000),
                                  response_headers={k: v for k, v in resp.headers.items()
                                                    if k.lower().startswith(('x-ratelimit', 'x-rate', 'retry-after',
                                                                             'content-type', 'link', 'x-total',
                                                                             'x-page'))})
                try:
                    payload = json.loads(raw.decode('utf-8')) if raw else None
                except ValueError:
                    payload = None
                    record['non_json_bytes'] = len(raw)
                record['schema'] = schema(payload)
                self.calls.append(record)
                print(f'  {record["status"]}  {method:4} {label or path}  ({record["elapsed_ms"]} ms)')
                return payload
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < 3:
                    wait = int(err.headers.get('Retry-After') or 2 ** (attempt + 1))
                    print(f'  429 rate-limited, waiting {wait}s…')
                    time.sleep(wait)
                    continue
                text = err.read().decode('utf-8', 'replace')[:500].replace(self._token, '<token>')
                record.update(status=err.code, error=text)
                self.calls.append(record)
                print(f'  {err.code}  {method:4} {label or path}  — {text[:120]}')
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                record.update(status=None, error=f'{type(err).__name__}: {err}'.replace(self._token, '<token>'))
                self.calls.append(record)
                print(f'  ERR  {method:4} {label or path}  — {err}')
                return None
        return None


def as_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ('data', 'items', 'results', 'activities', 'athletes'):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


# --- probe ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--days', type=int, default=365, help='How far back to look for activities (default 365)')
    ap.add_argument('--out', default=str(PROJECT_ROOT / 'openfield_probe_report.json'))
    args = ap.parse_args()

    env = {**load_env(PROJECT_ROOT / '.env'), **os.environ}
    token = env.get('OPENFIELD_API_TOKEN', '')
    region = env.get('OPENFIELD_REGION', 'eu').lower()
    if not token:
        print('OPENFIELD_API_TOKEN not found in .env or environment', file=sys.stderr)
        return 1
    base = env.get('OPENFIELD_API_BASE') or REGION_HOSTS.get(region)
    if not base:
        print(f'Unknown OPENFIELD_REGION={region!r}; set OPENFIELD_API_BASE', file=sys.stderr)
        return 1

    c = Client(base, token)
    print(f'Probing {base}  (region={region})\n')
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'base_url': base,
              'python': sys.version.split()[0], 'calls': c.calls, 'findings': {}}
    findings = report['findings']

    print('Account & reference data')
    c.request('GET', '/teams')
    athletes = as_list(c.request('GET', '/athletes'))
    findings['athlete_count'] = len(athletes)
    c.request('GET', '/positions')
    c.request('GET', '/tags')
    c.request('GET', '/venues')

    params_payload = as_list(c.request('GET', '/parameters'))
    slugs = {}
    for p in params_payload:
        if isinstance(p, dict) and p.get('slug'):
            slugs[p['slug']] = {k: p.get(k) for k in ('name', 'unit_type', 'unit', 'parameter_type', 'lower_bound',
                                                     'upper_bound', 'is_protected') if k in p}
    findings['parameter_count'] = len(slugs)
    findings['candidate_params_available'] = {s: (s in slugs) for s in CANDIDATE_PARAMS}
    findings['velocity_band_params'] = sorted(s for s in slugs if 'velocity_band' in s and 'distance' in s)[:60]
    findings['accel_decel_params'] = sorted(s for s in slugs if re.search(r'(accel|decel)', s) and 'count' in s)[:60]
    findings['parameter_catalogue_sample'] = dict(list(slugs.items())[:40])
    findings['parameter_details_for_candidates'] = {s: slugs[s] for s in CANDIDATE_PARAMS if s in slugs}

    print('\nActivities')
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=args.days)).timestamp())
    end = int((now + timedelta(days=1)).timestamp())
    activities = as_list(c.request('GET', '/activities', {'startTime': start, 'endTime': end},
                                   label='/activities?startTime&endTime'))
    if not activities:
        activities = as_list(c.request('GET', '/activities', label='/activities (no filter)'))
    findings['activity_count'] = len(activities)
    findings['activity_names_sample'] = [a.get('name') for a in activities[:15] if isinstance(a, dict)]
    findings['activity_tags_sample'] = [a.get('tag_list') or a.get('tags') for a in activities[:15]
                                        if isinstance(a, dict)]

    available = [s for s in CANDIDATE_PARAMS if s in slugs] or ['total_distance', 'total_player_load', 'max_vel']
    if activities:
        # Prefer an activity with athletes in it.
        act = next((a for a in activities if isinstance(a, dict) and (a.get('athlete_count') or 0) > 0),
                   activities[0])
        aid = act.get('id')
        findings['probed_activity'] = {'id_type': type_name(aid), 'athlete_count': act.get('athlete_count'),
                                       'period_count': act.get('period_count'), 'start_time': act.get('start_time')}
        print(f'\nOne activity in depth (athletes={act.get("athlete_count")}, periods={act.get("period_count")})')
        c.request('GET', f'/activities/{aid}', label='/activities/{id}')
        c.request('GET', f'/activities/{aid}/periods', label='/activities/{id}/periods')
        act_athletes = as_list(c.request('GET', f'/activities/{aid}/athletes', label='/activities/{id}/athletes'))
        c.request('GET', f'/activities/{aid}/athletes', {'params': ','.join(available)},
                  label='/activities/{id}/athletes?params=…')
        c.request('GET', f'/activities/{aid}/tags', label='/activities/{id}/tags')

        print('\nStats (POST /stats is a query, not a write)')
        base_body = {
            'parameters': ['athlete_id', 'athlete_name', 'activity_id', 'activity_name', 'date', 'start_time',
                           'end_time', 'period_id', 'period_name', 'position_name'] + available,
            'filters': [{'name': 'activity_id', 'comparison': '=', 'values': [aid]}],
        }
        c.request('POST', '/stats', body={**base_body, 'group_by': ['athlete', 'activity']},
                  label='/stats group_by=athlete,activity')
        c.request('POST', '/stats', body={**base_body, 'group_by': ['athlete', 'period']},
                  label='/stats group_by=athlete,period')
        c.request('POST', '/stats', body={**base_body, 'group_by': ['athlete', 'activity'],
                                          'source': 'cached_stats'},
                  label='/stats source=cached_stats')

        if act_athletes:
            ath = act_athletes[0]
            ath_id = ath.get('athlete_id') or ath.get('id')
            print('\n10 Hz sensor data — first response only, to see the format')
            c.request('GET', f'/activities/{aid}/athletes/{ath_id}/sensor',
                      {'stream_type': 'gps'}, label='/activities/{id}/athletes/{athlete_id}/sensor')

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    ok = sum(1 for r in c.calls if r.get('status') and 200 <= r['status'] < 300)
    print(f'\n{ok}/{len(c.calls)} calls OK. Report saved to {args.out}')
    print('No token or personal data is stored in it — safe to share.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
