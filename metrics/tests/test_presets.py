import pytest
from django.core.management import call_command

from metrics.models import MetricDefinition, MetricSet
from metrics.presets import CATAPULT_METRICS, PRESETS, install_preset
from metrics.services import CORE_METRICS, sync_catalogue

pytestmark = pytest.mark.django_db

ALL_SLUGS = sorted({m for p in PRESETS.values() for m in p.metrics} - {m['key'] for m in CORE_METRICS})


@pytest.fixture
def full_catalogue(club):
    sync_catalogue(club, 'catapult_openfield',
                   [{'slug': s, 'name': s.replace('_', ' ').title(), 'unit_type': ''} for s in ALL_SLUGS])


def u(club, path):
    return f'/api/clubs/{club.pk}/{path}'


def test_every_preset_metric_has_settings_and_fits_a_set():
    assert set(ALL_SLUGS) <= set(CATAPULT_METRICS)
    assert all(len(p.metrics) <= MetricSet.MAX_METRICS for p in PRESETS.values())


def test_install_enables_with_hand_checked_settings(club, full_catalogue):
    r = install_preset(club, 'rhie')
    assert r.skipped == [] and r.metric_set.metric_keys[:3] == ['duration', 'hsr_distance', 'sprint_distance']
    rec = MetricDefinition.objects.get(club=club, provider_slug='rhie_average_effort_recovery')
    assert (rec.unit, rec.multiplier, rec.aggregation, rec.higher_is_better) == ('s', 1.0, 'weighted_mean', False)
    # only what the preset needs is enabled
    assert not MetricDefinition.objects.filter(club=club, provider_slug='equivalent_distance_index').exists()


def test_install_is_idempotent_and_keeps_staff_edits(club, full_catalogue):
    install_preset(club, 'mdl')
    MetricDefinition.objects.filter(club=club, provider_slug='total_multidirectional_load').update(short_label='MD')
    install_preset(club, 'mdl')
    assert MetricSet.objects.filter(club=club, name='Mechanical / MDL').count() == 1
    assert MetricDefinition.objects.get(club=club, provider_slug='total_multidirectional_load').short_label == 'MD'


def test_missing_metrics_are_skipped_not_invented(club):
    sync_catalogue(club, 'catapult_openfield', [{'slug': 'rhie_bout_count', 'name': 'RHIE Total Bouts'}])
    r = install_preset(club, 'rhie')
    assert 'rhie_average_effort_count' in r.skipped
    assert r.metric_set.metric_keys == ['duration', 'hsr_distance', 'sprint_distance', 'rhie-bout-count']


def test_default_moves_between_presets(club, full_catalogue):
    install_preset(club, 'sc-daily', make_default=True)
    install_preset(club, 'metabolic', make_default=True)
    assert list(MetricSet.objects.filter(club=club, is_default=True).values_list('name', flat=True)) == ['Metabolic']


def test_command_installs_all(club, full_catalogue, capsys):
    call_command('metrics', '--club', club.slug, '--install', 'all', '--default-preset', 'sc-daily')
    out = capsys.readouterr().out
    assert 'S&C Daily' in out and 'club default' in out
    assert MetricSet.objects.filter(club=club, owner__isnull=True).count() == len(PRESETS)


def test_api_presets_and_install(make_member, club, full_catalogue):
    _, coach = make_member(club, 'head_coach')
    listed = coach.get(u(club, 'metric-sets/presets/')).data
    assert [p['key'] for p in listed] == list(PRESETS) and all(m['available'] for m in listed[0]['metrics'])
    assert coach.post(u(club, 'metric-sets/install_preset/'), {'preset': 'rhie'}).status_code == 403
    _, sc = make_member(club, 'sports_scientist')
    r = sc.post(u(club, 'metric-sets/install_preset/'), {'preset': 'rhie', 'make_default': True})
    assert r.status_code == 201 and r.data['is_club'] and r.data['is_default'] and r.data['skipped'] == []
    assert sc.post(u(club, 'metric-sets/install_preset/'), {'preset': 'nope'}).status_code == 400
    assert coach.get(u(club, 'metric-sets/presets/')).data[3]['installed'] is True


def test_zero_means_not_measured_for_mdl_and_rhie_means(club, full_catalogue):
    from metrics.services import extract_metrics
    install_preset(club, 'mdl')
    install_preset(club, 'rhie')
    defs = list(MetricDefinition.objects.filter(club=club).exclude(provider_slug=''))
    out = extract_metrics({'total_multidirectional_load': 0, 'rhie_bout_count': 0, 'rhie_average_effort_recovery': 0,
                           'lateral_load_left': 12.5}, defs)
    # old file without MDL and a period without RHIE bouts: real zero only for the bout count
    assert out == {'rhie-bout-count': 0.0, 'lateral-load-left': 12.5}
