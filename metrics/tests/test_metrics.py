from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from metrics.models import MetricDefinition, MetricSet, ProviderMetric
from metrics.services import (
    aggregate_metrics, enable_from_catalogue, ensure_core_metrics, extract_metrics, guess_definition,
    search_catalogue, sync_catalogue, value_of,
)

pytestmark = pytest.mark.django_db


def pm(slug, name, unit_type=''):
    return ProviderMetric(provider='catapult_openfield', slug=slug, name=name, unit_type=unit_type)


@pytest.mark.parametrize('slug,name,unit,expect', [
    ('max_vel', 'Maximum Velocity', 'speed', ('speed', 'max', 'km/h', 3.6)),
    ('velocity_band5_total_distance', 'Velocity Band 5 Total Distance', 'distance', ('speed', 'sum', 'm', 1.0)),
    ('player_load_per_minute', 'Player Load Per Minute', '', ('load', 'weighted_mean', '', 1.0)),
    ('rhie_total_bouts', 'RHIE Total Bouts', 'count', ('rhie', 'sum', 'n', 1.0)),
    ('total_multidirectional_load', 'Multidirectional Load', '', ('multidirectional', 'sum', '', 1.0)),
    ('metabolic_power_average', 'Average Metabolic Power', '', ('metabolic', 'weighted_mean', 'W/kg', 1.0)),
    ('field_time', 'Field Time', 'duration', ('volume', 'sum', 'min', 1 / 60)),
    ('mechanical_power_max', 'Peak Mechanical Power', '', ('mechanical', 'max', 'W/kg', 1.0)),
])
def test_guess_definition(slug, name, unit, expect):
    g = guess_definition(pm(slug, name, unit))
    assert (g['category'], g['aggregation'], g['unit'], g['multiplier']) == expect


def test_catalogue_sync_is_idempotent_and_updates(club):
    params = [{'slug': 'rhie_total_bouts', 'name': 'RHIE Bouts', 'unit_type': 'count'},
              {'slug': 'max_vel', 'name': 'Maximum Velocity', 'unit_type': 'speed'}]
    assert sync_catalogue(club, 'catapult_openfield', params) == 2
    params[0]['name'] = 'RHIE Total Bouts'
    assert sync_catalogue(club, 'catapult_openfield', params) == 2
    assert ProviderMetric.objects.get(slug='rhie_total_bouts').name == 'RHIE Total Bouts'
    assert [p.slug for p in search_catalogue(club, 'rhie')] == ['rhie_total_bouts']


def test_enable_from_catalogue(club):
    sync_catalogue(club, 'catapult_openfield', [{'slug': 'rhie_total_bouts', 'name': 'RHIE Total Bouts',
                                                 'unit_type': 'count'}])
    md = enable_from_catalogue(club, ProviderMetric.objects.get(), short_label='RHIE')
    assert (md.key, md.category, md.aggregation, md.short_label) == ('rhie-total-bouts', 'rhie', 'sum', 'RHIE')
    again = enable_from_catalogue(club, ProviderMetric.objects.get())
    assert again.pk == md.pk and MetricDefinition.objects.filter(provider_slug='rhie_total_bouts').count() == 1


def _defs():
    return [MetricDefinition(key='rhie', provider_slug='rhie_total_bouts', aggregation='sum', decimals=0),
            MetricDefinition(key='peak_mp', provider_slug='mp_max', aggregation='max', decimals=1),
            MetricDefinition(key='mp_avg', provider_slug='mp_avg', aggregation='weighted_mean', decimals=2),
            MetricDefinition(key='vmax2', provider_slug='vel', aggregation='max', decimals=1, multiplier=3.6)]


def test_extract_converts_units_and_skips_missing():
    out = extract_metrics({'rhie_total_bouts': 4, 'vel': 8.5, 'mp_avg': ''}, _defs())
    assert out == {'rhie': 4.0, 'vmax2': 30.6}


def test_aggregate_follows_each_metric_rule():
    h1 = SimpleNamespace(metrics={'rhie': 3, 'peak_mp': 40.0, 'mp_avg': 10.0}, duration_min=Decimal('45'))
    h2 = SimpleNamespace(metrics={'rhie': 2, 'peak_mp': 52.5, 'mp_avg': 13.0}, duration_min=Decimal('15'))
    out = aggregate_metrics([h1, h2], _defs())
    assert out['rhie'] == 5 and out['peak_mp'] == 52.5
    assert out['mp_avg'] == pytest.approx((10 * 45 + 13 * 15) / 60)   # time-weighted, not 11.5


def test_value_of_display_modes(club):
    ensure_core_metrics(club)
    dist = MetricDefinition.objects.get(club=club, key='total_distance')
    vmax = MetricDefinition.objects.get(club=club, key='max_speed')
    load = SimpleNamespace(total_distance_m=10000, duration_min=Decimal('100'), max_speed_kmh=Decimal('31.5'),
                           quality_flags=[], metrics={})
    assert value_of(load, dist) == 10000
    assert value_of(load, dist, 'per_90') == 9000
    assert value_of(load, dist, 'per_min') == 100
    assert value_of(load, vmax, 'per_90') == 31.5          # a peak is never normalised
    load.quality_flags = ['max_speed_outlier']
    assert value_of(load, vmax) is None                     # GPS spike never reaches a report


def test_metric_set_validation(club):
    ensure_core_metrics(club)
    with pytest.raises(ValidationError):
        MetricSet(club=club, name='x', metric_keys=['total_distance', 'nope']).clean()
    with pytest.raises(ValidationError):
        MetricSet(club=club, name='x', metric_keys=['total_distance', 'total_distance']).clean()
    with pytest.raises(ValidationError):
        MetricSet(club=club, name='x', metric_keys=[]).clean()
    MetricSet(club=club, name='ok', metric_keys=['total_distance', 'hsr_distance']).clean()


def test_metrics_command(club):
    from io import StringIO

    from django.core.management import call_command
    sync_catalogue(club, 'catapult_openfield', [
        {'slug': 'total_multidirectional_load', 'name': 'Multidirectional Load', 'unit_type': ''},
        {'slug': 'rhie_total_bouts', 'name': 'RHIE Total Bouts', 'unit_type': 'count'}])
    out = StringIO()
    call_command('metrics', '--club', club.slug, '--suggest', stdout=out)
    assert 'Multidirectional Load (MDL) — 1 found' in out.getvalue()
    call_command('metrics', '--club', club.slug, '--enable', 'rhie_total_bouts', stdout=out)
    call_command('metrics', '--club', club.slug, '--create-set', 'RHIE', '--keys', 'total_distance,rhie-total-bouts',
                 '--club-wide', '--default', stdout=out)
    ms = MetricSet.objects.get(club=club, name='RHIE')
    assert ms.is_default and ms.owner is None and ms.metric_keys == ['total_distance', 'rhie-total-bouts']


def test_catalogue_with_repeated_slugs(club):
    """Regression: the live OpenField catalogue lists 12 MII parameters twice."""
    dup = {'slug': 'max_intensity_interval_dist_interval_1_start_time', 'name': 'MII Distance Interval 1 Start Time'}
    params = [dup, {'slug': 'max_vel', 'name': 'Maximum Velocity'}, dict(dup, id='other-id')]
    assert sync_catalogue(club, 'catapult_openfield', params) == 2
    assert sync_catalogue(club, 'catapult_openfield', params) == 2
