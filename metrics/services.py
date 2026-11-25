"""
Metric catalogue logic: core metrics, guessing how a provider parameter behaves,
reading values off a load in any display mode, and adding up periods correctly.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable

from django.utils.text import slugify

from .models import Aggregation, Category, MetricDefinition, ProviderMetric

# Built-in columns, exposed as metrics so a set can mix them with catalogue metrics.
CORE_METRICS = [
    dict(key='duration', label='Duration', short_label='Min', unit='min', category=Category.VOLUME,
         aggregation=Aggregation.SUM, decimals=0, core_field='duration_min'),
    dict(key='total_distance', label='Total Distance', short_label='Dist', unit='m', category=Category.VOLUME,
         aggregation=Aggregation.SUM, decimals=0, core_field='total_distance_m', higher_is_better=True),
    dict(key='hsr_distance', label='High-Speed Running', short_label='HSR', unit='m', category=Category.SPEED,
         aggregation=Aggregation.SUM, decimals=0, core_field='hsr_distance_m', higher_is_better=True),
    dict(key='sprint_distance', label='Sprint Distance', short_label='Sprint', unit='m', category=Category.SPEED,
         aggregation=Aggregation.SUM, decimals=0, core_field='sprint_distance_m', higher_is_better=True),
    dict(key='accelerations', label='Accelerations', short_label='Acc', unit='n', category=Category.ACCELERATION,
         aggregation=Aggregation.SUM, decimals=0, core_field='accelerations'),
    dict(key='decelerations', label='Decelerations', short_label='Dec', unit='n', category=Category.ACCELERATION,
         aggregation=Aggregation.SUM, decimals=0, core_field='decelerations'),
    dict(key='max_speed', label='Top Speed', short_label='Vmax', unit='km/h', category=Category.SPEED,
         aggregation=Aggregation.MAX, decimals=1, core_field='max_speed_kmh', higher_is_better=True),
    dict(key='player_load', label='PlayerLoad', short_label='PL', unit='AU', category=Category.LOAD,
         aggregation=Aggregation.SUM, decimals=0, core_field='player_load'),
]

# Keyword → category, checked in order against "slug name".
CATEGORY_RULES = [
    (Category.MULTIDIRECTIONAL, r'multi ?direction|\bmdl\b|lateral|change of direction|\bcod\b|\bima\b'),
    (Category.RHIE, r'rhie|repeat(ed)? high'),
    (Category.METABOLIC, r'metabolic|\bhmld\b|\bmp\b|equivalent distance'),
    (Category.MECHANICAL, r'mechanical|work|stride|impact|jump|landing'),
    (Category.HEART_RATE, r'heart|\bhr\b|trimp|edwards'),
    (Category.ACCELERATION, r'accel|decel'),
    (Category.SPEED, r'velocity|speed|sprint|\bvel\b|high speed|hsr|max_vel'),
    (Category.LOAD, r'player ?load|player_load'),
    (Category.VOLUME, r'distance|duration|field time'),
]
MAX_WORDS = r'\bmax|peak|maximum|\bbest\b'
MEAN_WORDS = r'average|\bavg\b|\bmean\b|per minute|per min|\bpercent|%|density|index|ratio|rate|\bper\b'
SPEED_UNIT = {'speed', 'velocity'}


def _text(slug: str, name: str) -> str:
    return f"{slug.replace('_', ' ')} {name}".lower()


def guess_definition(pm: ProviderMetric) -> dict:
    """Sensible defaults for a catalogue parameter; staff can correct any of them."""
    text = _text(pm.slug, pm.name)
    category = next((c for c, rx in CATEGORY_RULES if re.search(rx, text)), Category.OTHER)
    unit_type = (pm.unit_type or '').lower()
    if re.search(MAX_WORDS, text):
        aggregation = Aggregation.MAX
    elif re.search(MEAN_WORDS, text) or unit_type in ('percentage', 'rate'):
        aggregation = Aggregation.MEAN
    else:
        aggregation = Aggregation.SUM
    unit, multiplier, decimals = '', 1.0, 0
    if unit_type in SPEED_UNIT:
        unit, multiplier, decimals = 'km/h', 3.6, 1          # Connect API reports m/s
        if aggregation == Aggregation.SUM:
            aggregation = Aggregation.MAX
    elif unit_type == 'distance':
        unit = 'm'
    elif unit_type == 'duration':
        unit, multiplier, decimals = 'min', 1 / 60, 1        # seconds → minutes
    elif unit_type == 'count':
        unit = 'n'
    elif unit_type == 'percentage':
        unit, decimals = '%', 1
    elif aggregation == Aggregation.MEAN:
        decimals = 2
    if 'power' in text and unit_type not in SPEED_UNIT:
        unit, decimals = unit or 'W/kg', max(decimals, 1)
    # A mean or a peak of exactly 0 means "nothing to measure", not a real zero.
    zero_is_missing = aggregation in (Aggregation.MEAN, Aggregation.MAX)
    return dict(category=category, aggregation=aggregation, unit=unit, multiplier=multiplier, decimals=decimals,
                zero_is_missing=zero_is_missing)


def ensure_core_metrics(club) -> None:
    for spec in CORE_METRICS:
        MetricDefinition.objects.get_or_create(club=club, key=spec['key'], defaults=spec)


def sync_catalogue(club, provider: str, parameters: Iterable[dict]) -> int:
    """Upsert the provider's parameter list. Returns number of catalogue rows."""
    existing = {pm.slug: pm for pm in ProviderMetric.objects.filter(club=club, provider=provider)}
    new, changed, seen = [], [], set()
    for p in parameters:
        slug = (p.get('slug') or '')[:150] if isinstance(p, dict) else ''
        # Providers repeat slugs (OpenField lists 12 MII parameters twice): first one wins.
        if not slug or slug in seen:
            continue
        seen.add(slug)
        name = (p.get('name') or slug)[:200]
        unit_type = (p.get('unit_type') or '')[:40]
        if slug in existing:
            pm = existing[slug]
            if (pm.name, pm.unit_type) != (name, unit_type):
                pm.name, pm.unit_type, pm.raw = name, unit_type, p
                changed.append(pm)
        else:
            new.append(ProviderMetric(club=club, provider=provider, slug=slug, name=name,
                                      unit_type=unit_type, raw=p))
    ProviderMetric.objects.bulk_create(new, batch_size=500)
    if changed:
        ProviderMetric.objects.bulk_update(changed, ['name', 'unit_type', 'raw'], batch_size=500)
    return ProviderMetric.objects.filter(club=club, provider=provider).count()


def _norm(text: str) -> str:
    """'Velocity_Band4 Total-Distance' → 'velocity band 4 total distance' (so 'band4' finds 'Band 4')."""
    text = re.sub(r'[_\-/()#%]+', ' ', text.lower())
    text = re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])', ' ', text)
    return ' '.join(text.split())


def search_catalogue(club, query: str, provider: str | None = None) -> list[ProviderMetric]:
    """
    Every word starts a word of the name or slug; numbers match whole ("band 4" never finds
    "band 24"). Best matches first: the exact name,
    then names that contain the whole phrase, then the shortest names
    ("Velocity Band 4 Total Distance" before "... Distance Band 7 Total # Efforts").
    """
    qs = ProviderMetric.objects.filter(club=club)
    if provider:
        qs = qs.filter(provider=provider)
    q = _norm(query)
    words = q.split()
    if not words:
        return list(qs.order_by('name'))
    hits = []
    for pm in qs.only('id', 'provider', 'slug', 'name', 'unit_type'):
        name = _norm(pm.name)
        tokens = f'{name} {_norm(pm.slug)}'.split()
        if all(any(t == w if w.isdigit() else t.startswith(w) for t in tokens) for w in words):
            rank = 0 if name == q else 1 if name.startswith(q) else 2 if q in name else 3
            hits.append((rank, len(name), pm.name, pm))
    return [h[-1] for h in sorted(hits, key=lambda h: h[:3])]


def enable_from_catalogue(club, pm: ProviderMetric, user=None, **overrides) -> MetricDefinition:
    guess = guess_definition(pm)
    base_key = slugify(pm.slug.replace('_', '-'))[:140] or 'metric'
    defaults = dict(label=pm.name[:120], provider=pm.provider, provider_slug=pm.slug, created_by=user,
                    enabled=True, **guess)
    defaults.update({k: v for k, v in overrides.items() if v not in (None, '')})
    md, created = MetricDefinition.objects.get_or_create(
        club=club, provider=pm.provider, provider_slug=pm.slug, defaults={'key': base_key, **defaults},
    )
    if not created and not md.enabled:
        md.enabled = True
        md.save(update_fields=['enabled', 'updated_at'])
    return md


def custom_definitions(club, provider: str) -> list[MetricDefinition]:
    return list(MetricDefinition.objects.filter(club=club, provider=provider, enabled=True).exclude(provider_slug=''))


def extract_metrics(extra: dict, definitions: list[MetricDefinition]) -> dict:
    """Provider values (by slug) → club metric values (by key), unit-converted."""
    out = {}
    for d in definitions:
        raw = extra.get(d.provider_slug)
        if raw is None or raw == '':
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value == 0 and d.zero_is_missing:
            continue
        out[d.key] = round(value * d.multiplier, max(d.decimals, 2))
    return out


def aggregate_metrics(rows: list, definitions: list[MetricDefinition]) -> dict:
    """Combine per-period metric values into one value per metric, following each metric's rule."""
    out = {}
    for d in definitions:
        pairs = [((r.metrics or {}).get(d.key), float(r.duration_min or 0)) for r in rows]
        pairs = [(v, w) for v, w in pairs if v is not None]
        if not pairs:
            continue
        if d.aggregation == Aggregation.MAX:
            out[d.key] = max(v for v, _ in pairs)
        elif d.aggregation == Aggregation.MEAN:
            total_w = sum(w for _, w in pairs)
            out[d.key] = round(sum(v * w for v, w in pairs) / total_w if total_w else
                               sum(v for v, _ in pairs) / len(pairs), max(d.decimals, 2))
        else:
            out[d.key] = round(sum(v for v, _ in pairs), max(d.decimals, 2))
    return out


def value_of(load, d: MetricDefinition, display: str = 'absolute'):
    """One metric of one load, in the requested display mode. None when not measured."""
    if d.core_field:
        v = getattr(load, d.core_field, None)
        if d.core_field == 'max_speed_kmh' and v is not None and getattr(load, 'quality_flags', None):
            v = None                                    # flagged GPS spike never reaches a report
    else:
        v = (load.metrics or {}).get(d.key)
    if v is None:
        return None
    v = float(v) if isinstance(v, Decimal) else v
    if display != 'absolute' and d.aggregation == Aggregation.SUM and d.key != 'duration':
        minutes = float(load.duration_min or 0)
        if not minutes:
            return None
        v = v / minutes * (90 if display == 'per_90' else 1)
    return round(v, d.decimals if display == 'absolute' else max(d.decimals, 1))
