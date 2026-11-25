"""
Configurable metrics: every coach reads different numbers.

  ProviderMetric    the provider's own catalogue (OpenField: ~1900 parameters),
                    refreshed on every sync, searchable.
  MetricDefinition  a metric this club actually uses: label, unit, category and —
                    crucially — how it aggregates (sum / max / time-weighted mean),
                    so it adds up correctly from halves and normalises per 90.
                    Core metrics (distance, HSR…) are definitions too, so a metric
                    set can mix them freely with RHIE, metabolic power or MDL.
  MetricSet         an ordered list of metrics + a display mode ("S&C Daily",
                    "Mechanical", "RHIE"…). Club-wide or personal; one default each.

Values live in `metrics` (JSON) on PlayerLoad / PeriodLoad, keyed by
MetricDefinition.key — a new metric never needs a schema change.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from clubs.models import ClubOwnedModel


class Category(models.TextChoices):
    VOLUME = 'volume', 'Volume'
    SPEED = 'speed', 'Speed & high-speed running'
    ACCELERATION = 'acceleration', 'Accelerations & decelerations'
    MULTIDIRECTIONAL = 'multidirectional', 'Multidirectional load'
    MECHANICAL = 'mechanical', 'Mechanical load'
    METABOLIC = 'metabolic', 'Metabolic power'
    RHIE = 'rhie', 'Repeated high-intensity efforts'
    INTENSITY = 'intensity', 'Intensity / density'
    HEART_RATE = 'heart_rate', 'Heart rate'
    LOAD = 'load', 'PlayerLoad & accelerometry'
    OTHER = 'other', 'Other'


class Aggregation(models.TextChoices):
    SUM = 'sum', 'Sum (distances, counts, load)'
    MAX = 'max', 'Maximum (peak speed, peak power)'
    MEAN = 'weighted_mean', 'Time-weighted mean (rates, %, densities)'


class ProviderMetric(ClubOwnedModel):
    provider = models.CharField(max_length=40)
    slug = models.CharField(max_length=150)
    name = models.CharField(max_length=200)
    unit_type = models.CharField(max_length=40, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['club', 'provider', 'slug'], name='unique_catalogue_slug')]

    def __str__(self):
        return f'{self.name} ({self.slug})'


class MetricDefinition(ClubOwnedModel):
    key = models.SlugField(max_length=150, help_text='Stable key used in metric sets and load values.')
    label = models.CharField(max_length=120)
    short_label = models.CharField(max_length=24, blank=True, help_text='Column header, e.g. "HSR".')
    unit = models.CharField(max_length=20, blank=True, help_text='m, km/h, n, AU, W/kg, %, s …')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    aggregation = models.CharField(max_length=16, choices=Aggregation.choices, default=Aggregation.SUM)
    higher_is_better = models.BooleanField(null=True, blank=True)
    decimals = models.PositiveSmallIntegerField(default=0)
    multiplier = models.FloatField(default=1.0, help_text='Unit conversion applied at ingest, e.g. 3.6 for m/s → km/h.')
    description = models.TextField(blank=True)

    provider = models.CharField(max_length=40, blank=True)
    provider_slug = models.CharField(max_length=150, blank=True)
    core_field = models.CharField(
        max_length=40, blank=True,
        help_text='Built-in load column this metric mirrors (total_distance_m …). Empty for catalogue metrics.',
    )
    enabled = models.BooleanField(default=True, help_text='Requested from the provider on every sync.')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['category', 'label']
        constraints = [
            models.UniqueConstraint(fields=['club', 'key'], name='unique_metric_key_per_club'),
            models.UniqueConstraint(
                fields=['club', 'provider', 'provider_slug'], condition=~Q(provider_slug=''),
                name='one_definition_per_provider_slug',
            ),
        ]

    @property
    def is_core(self) -> bool:
        return bool(self.core_field)

    def __str__(self):
        return self.label


class MetricSet(ClubOwnedModel):
    class Display(models.TextChoices):
        ABSOLUTE = 'absolute', 'Absolute'
        PER_MIN = 'per_min', 'Per minute'
        PER_90 = 'per_90', 'Per 90'

    name = models.CharField(max_length=80)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='metric_sets',
        help_text='Empty = club-wide set, visible to all staff.',
    )
    metric_keys = models.JSONField(default=list, help_text='Ordered MetricDefinition keys.')
    display = models.CharField(max_length=10, choices=Display.choices, default=Display.ABSOLUTE)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['owner_id', 'name']
        constraints = [
            # One default per person, and one club-wide default (portable: no NULLS NOT DISTINCT needed).
            models.UniqueConstraint(fields=['club', 'owner'], condition=Q(is_default=True, owner__isnull=False),
                                    name='one_default_set_per_owner'),
            models.UniqueConstraint(fields=['club'], condition=Q(is_default=True, owner__isnull=True),
                                    name='one_club_default_set'),
        ]

    MAX_METRICS = 12

    def clean(self):
        super().clean()
        keys = list(self.metric_keys or [])
        if not keys:
            raise ValidationError({'metric_keys': 'Pick at least one metric.'})
        if len(keys) > self.MAX_METRICS:
            raise ValidationError({'metric_keys': f'At most {self.MAX_METRICS} metrics per set.'})
        if len(set(keys)) != len(keys):
            raise ValidationError({'metric_keys': 'A metric appears twice.'})
        known = set(MetricDefinition.objects.filter(club_id=self.club_id, key__in=keys).values_list('key', flat=True))
        missing = [k for k in keys if k not in known]
        if missing:
            raise ValidationError({'metric_keys': f'Unknown metrics: {missing}'})

    def __str__(self):
        return self.name
