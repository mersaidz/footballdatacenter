"""
Session-level load from period-level load.

A match's PlayerLoad counts only its playing periods (halves, extra time).
Warm-up, half-time and anything recorded around the game stay in the
period table but do not inflate match demands, minutes or per-90 values.
Training keeps the whole activity: for S&C the warm-up is training load too.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import QuerySet

from football.models import ActivityPeriod, LoadMetrics, PlayerLoad, PeriodLoad
from metrics.services import aggregate_metrics, custom_definitions

SUM_INT = ('total_distance_m', 'hsr_distance_m', 'sprint_distance_m', 'sprint_count', 'accelerations',
           'decelerations')
SUM_DEC = ('duration_min', 'player_load')
METRIC_FIELDS = SUM_INT + SUM_DEC + ('max_speed_kmh',)


def snapshot(values: dict) -> dict:
    """JSON-safe copy of whole-activity metrics, kept so a load can always fall back to them."""
    return {k: (float(values[k]) if isinstance(values.get(k), Decimal) else values.get(k)) for k in METRIC_FIELDS}


def aggregate(rows: list[LoadMetrics]) -> dict:
    out: dict = {}
    for f in SUM_INT:
        vals = [getattr(r, f) for r in rows if getattr(r, f) is not None]
        out[f] = sum(vals) if vals else None
    for f in SUM_DEC:
        vals = [getattr(r, f) for r in rows if getattr(r, f) is not None]
        out[f] = sum(vals, Decimal('0')) if vals else None
    clean = [r.max_speed_kmh for r in rows if r.max_speed_kmh is not None and not r.quality_flags]
    anyv = [r.max_speed_kmh for r in rows if r.max_speed_kmh is not None]
    out['max_speed_kmh'] = max(clean) if clean else (max(anyv) if anyv else None)
    flags = sorted({f for r in rows for f in (r.quality_flags or [])})
    # A spike in a half only taints max speed if no clean half exists.
    out['quality_flags'] = [] if clean else flags
    return out


def is_match_context(match, session) -> bool:
    return match is not None or (session is not None and session.session_type == 'match')


def recompute_loads(*, match=None, training_session=None) -> int:
    """Re-derive PlayerLoad rows of one match/session from its periods. Returns rows changed."""
    ctx = {'match': match} if match is not None else {'training_session': training_session}
    loads: QuerySet[PlayerLoad] = PlayerLoad.objects.filter(**ctx)
    playing = list(ActivityPeriod.objects.filter(**ctx, role__in=ActivityPeriod.PLAYING_ROLES))
    use_periods = is_match_context(match, training_session) and bool(playing)
    defs_by_provider: dict[str, list] = {}
    changed = 0
    for load in loads:
        if load.provider not in defs_by_provider:
            defs_by_provider[load.provider] = custom_definitions(load.club_id, load.provider)
        defs = defs_by_provider[load.provider]
        if use_periods:
            rows = list(PeriodLoad.objects.filter(player=load.player, period__in=playing, provider=load.provider))
            values = aggregate(rows)
            values['metrics'] = aggregate_metrics(rows, defs)
            if not rows:  # in the squad file but never on the pitch (unused substitute who warmed up)
                values = {**{f: 0 for f in SUM_INT}, 'duration_min': Decimal('0'), 'player_load': Decimal('0'),
                          'max_speed_kmh': None, 'quality_flags': [], 'metrics': {}}
            basis = PlayerLoad.Basis.MATCH_PERIODS
        else:
            total = (load.extra_metrics or {}).get('activity_total')
            if not total:
                continue
            values = {f: (Decimal(str(total[f])) if f in SUM_DEC + ('max_speed_kmh',) and total.get(f) is not None
                          else total.get(f)) for f in METRIC_FIELDS}
            values['quality_flags'] = (load.extra_metrics or {}).get('activity_flags', [])
            values['metrics'] = (load.extra_metrics or {}).get('activity_metrics', load.metrics or {})
            basis = PlayerLoad.Basis.ACTIVITY
        for k, v in values.items():
            setattr(load, k, v)
        load.load_basis = basis
        load.save()
        changed += 1
    return changed
