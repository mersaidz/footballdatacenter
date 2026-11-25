"""
Ready-made metric sets for the usual coaching "schools": daily S&C, MDL / mechanical,
metabolic power and RHIE. Installing a preset enables its catalogue metrics with
hand-checked settings (aggregation, unit, short label) and publishes a club-wide set.

Metrics the provider account doesn't offer are skipped and reported, never invented.
Staff edits win: an already tracked metric keeps its settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from .models import Aggregation as A, Category as C, MetricDefinition, MetricSet, ProviderMetric
from .services import enable_from_catalogue, ensure_core_metrics

SUM, MAX, MEAN = A.SUM, A.MAX, A.MEAN
SECONDS = dict(unit='s', multiplier=1.0, decimals=1)   # RHIE times read better in seconds than minutes

# slug → settings. One place, shared by every preset that uses the metric.
CATAPULT_METRICS: dict[str, dict] = {
    # Multidirectional load (MDL) — Catapult's 2025 update
    'total_multidirectional_load': dict(zero_is_missing=True, label='Multidirectional Load', short_label='MDL', category=C.MULTIDIRECTIONAL,
                                        aggregation=SUM, unit='AU', decimals=0),
    'lateral_load': dict(zero_is_missing=True, short_label='Lat Load', category=C.MULTIDIRECTIONAL, aggregation=SUM, unit='AU', decimals=0),
    'lateral_load_left': dict(zero_is_missing=True, short_label='Lat L', category=C.MULTIDIRECTIONAL, aggregation=SUM, unit='AU', decimals=0),
    'lateral_load_right': dict(zero_is_missing=True, short_label='Lat R', category=C.MULTIDIRECTIONAL, aggregation=SUM, unit='AU', decimals=0),
    'high_lateral_load_left': dict(zero_is_missing=True, short_label='Hi-Lat L', category=C.MULTIDIRECTIONAL, aggregation=SUM, unit='AU',
                                   decimals=0),
    'high_lateral_load_right': dict(zero_is_missing=True, short_label='Hi-Lat R', category=C.MULTIDIRECTIONAL, aggregation=SUM, unit='AU',
                                    decimals=0),
    'max_multidirectional_acceleration': dict(zero_is_missing=True, short_label='Max MD Acc', category=C.MULTIDIRECTIONAL, aggregation=MAX,
                                              unit='m/s²', decimals=2),
    'max_multidirectional_deceleration': dict(zero_is_missing=True, short_label='Max MD Dec', category=C.MULTIDIRECTIONAL, aggregation=MAX,
                                              unit='m/s²', decimals=2),
    # Mechanical
    'total_mechanical_work': dict(zero_is_missing=True, short_label='Mech Work', category=C.MECHANICAL, aggregation=SUM, unit='AU',
                                  decimals=0),
    'mechanical_work_per_minute': dict(zero_is_missing=True, short_label='Mech W/min', category=C.MECHANICAL, aggregation=MEAN, unit='AU',
                                       decimals=1),
    'max_mechanical_power': dict(zero_is_missing=True, short_label='Max MechP', category=C.MECHANICAL, aggregation=MAX, unit='W/kg',
                                 decimals=1),
    'average_mechanical_power': dict(zero_is_missing=True, short_label='Avg MechP', category=C.MECHANICAL, aggregation=MEAN, unit='W/kg',
                                     decimals=1),
    # Metabolic
    'equivalent_distance': dict(zero_is_missing=True, short_label='EqDist', category=C.METABOLIC, aggregation=SUM, unit='m', decimals=0),
    'equivalent_distance_index': dict(zero_is_missing=True, label='Equivalent Distance Index', short_label='EDI', category=C.METABOLIC,
                                      aggregation=MEAN, unit='ratio', decimals=2),
    'high_metabolic_load_distance': dict(label='High Metabolic Load Distance', short_label='HMLD',
                                         category=C.METABOLIC, aggregation=SUM, unit='m', decimals=0),
    'high_metabolic_power_efforts': dict(short_label='HMP Eff', category=C.METABOLIC, aggregation=SUM, unit='n',
                                         decimals=0),
    'average_metabolic_power': dict(zero_is_missing=True, short_label='Avg MP', category=C.METABOLIC, aggregation=MEAN, unit='W/kg',
                                    decimals=1),
    # RHIE
    'rhie_bout_count': dict(label='RHIE Bouts', short_label='RHIE', category=C.RHIE, aggregation=SUM, unit='n',
                            decimals=0),
    'rhie_average_effort_count': dict(zero_is_missing=True, label='RHIE Efforts per Bout (mean)', short_label='Eff/Bout', category=C.RHIE,
                                      aggregation=MEAN, unit='n', decimals=1),
    'rhie_max_effort_count': dict(zero_is_missing=True, label='RHIE Efforts per Bout (max)', short_label='Max Eff/Bout', category=C.RHIE,
                                  aggregation=MAX, unit='n', decimals=0),
    'rhie_average_effort_duration': dict(zero_is_missing=True, label='RHIE Effort Duration (mean)', short_label='Eff Dur', category=C.RHIE,
                                         aggregation=MEAN, **SECONDS),
    'rhie_average_effort_recovery': dict(zero_is_missing=True, label='RHIE Effort Recovery (mean)', short_label='Eff Rec', category=C.RHIE,
                                         aggregation=MEAN, higher_is_better=False, **SECONDS),
    'rhie_average_bout_recovery': dict(zero_is_missing=True, label='RHIE Bout Recovery (mean)', short_label='Bout Rec', category=C.RHIE,
                                       aggregation=MEAN, higher_is_better=False, unit='s', multiplier=1.0, decimals=0),
    # Acceleration load
    'total_acceleration_load': dict(zero_is_missing=True, short_label='Acc Load', category=C.ACCELERATION, aggregation=SUM, unit='AU',
                                    decimals=0),
}


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    description: str
    metrics: list[str] = field(default_factory=list)   # core keys or catalogue slugs, in column order
    display: str = MetricSet.Display.ABSOLUTE


PRESETS: dict[str, Preset] = {p.key: p for p in [
    Preset('sc-daily', 'S&C Daily', 'Volume, speed and intensity at a glance — the default daily view.',
           ['duration', 'total_distance', 'hsr_distance', 'sprint_distance', 'max_speed', 'accelerations',
            'decelerations', 'high_metabolic_load_distance', 'total_multidirectional_load', 'player_load']),
    Preset('mdl', 'Mechanical / MDL', 'Multidirectional and lateral load, left/right balance, mechanical work.',
           ['duration', 'total_multidirectional_load', 'lateral_load_left', 'lateral_load_right',
            'high_lateral_load_left', 'high_lateral_load_right', 'max_multidirectional_acceleration',
            'max_multidirectional_deceleration', 'total_mechanical_work', 'mechanical_work_per_minute',
            'max_mechanical_power']),
    Preset('metabolic', 'Metabolic', 'Metabolic power: equivalent distance, HMLD and high-power efforts.',
           ['duration', 'total_distance', 'equivalent_distance', 'equivalent_distance_index',
            'high_metabolic_load_distance', 'high_metabolic_power_efforts', 'average_metabolic_power']),
    Preset('rhie', 'RHIE', 'Repeated high-intensity efforts: how many bouts, how dense, how much recovery.',
           ['duration', 'hsr_distance', 'sprint_distance', 'rhie_bout_count', 'rhie_average_effort_count',
            'rhie_max_effort_count', 'rhie_average_effort_duration', 'rhie_average_effort_recovery',
            'rhie_average_bout_recovery']),
]}


@dataclass
class InstallResult:
    preset: Preset
    metric_set: MetricSet | None
    enabled: list[str]
    skipped: list[str]          # not offered by this provider account


def install_preset(club, preset_key: str, *, provider='catapult_openfield', make_default=False,
                   user=None) -> InstallResult:
    preset = PRESETS[preset_key]
    ensure_core_metrics(club)
    core = set(MetricDefinition.objects.filter(club=club).exclude(core_field='').values_list('key', flat=True))
    catalogue = {pm.slug: pm for pm in ProviderMetric.objects.filter(
        club=club, provider=provider, slug__in=[m for m in preset.metrics if m not in core])}
    keys, enabled, skipped = [], [], []
    with transaction.atomic():
        for item in preset.metrics:
            if item in core:
                keys.append(item)
                continue
            pm = catalogue.get(item)
            if pm is None:
                skipped.append(item)
                continue
            md = enable_from_catalogue(club, pm, user, **CATAPULT_METRICS.get(item, {}))
            keys.append(md.key)
            enabled.append(item)
        if len(keys) <= 1:
            return InstallResult(preset, None, enabled, skipped)
        ms, _ = MetricSet.objects.update_or_create(
            club=club, owner=None, name=preset.name, defaults=dict(metric_keys=keys, display=preset.display))
        if make_default:
            MetricSet.objects.filter(club=club, owner=None, is_default=True).exclude(pk=ms.pk).update(is_default=False)
            ms.is_default = True
            ms.save(update_fields=['is_default', 'updated_at'])
    return InstallResult(preset, ms, enabled, skipped)
