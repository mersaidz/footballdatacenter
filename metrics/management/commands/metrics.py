"""
Choose which provider metrics the club tracks — from the terminal.

  python manage.py metrics --club demo --suggest                 # MDL, mechanical, metabolic, RHIE… on this account
  python manage.py metrics --club demo --search multidirectional
  python manage.py metrics --club demo --enable <slug> --enable <slug>
  python manage.py metrics --club demo --list
  python manage.py metrics --club demo --create-set "Mechanical" --keys total_distance,<key>,<key> --club-wide --default

The catalogue is refreshed by every `sync_openfield`; enabled metrics arrive with the next sync.
"""
from django.core.management.base import BaseCommand, CommandError

from clubs.models import Club
from metrics.models import MetricDefinition, MetricSet, ProviderMetric
from metrics.services import enable_from_catalogue, ensure_core_metrics, guess_definition, search_catalogue

THEMES = {
    'Multidirectional Load (MDL)': ['multidirectional', 'multi directional', 'mdl'],
    'Mechanical load / work / power': ['mechanical'],
    'Metabolic power / HMLD': ['metabolic', 'hmld'],
    'RHIE': ['rhie'],
    'Acceleration load & density': ['acceleration load', 'density'],
    'Heart rate': ['heart rate', 'trimp'],
}


class Command(BaseCommand):
    help = 'Search the provider catalogue, enable metrics, build metric sets.'

    def add_arguments(self, parser):
        parser.add_argument('--club', required=True)
        parser.add_argument('--provider', default='catapult_openfield')
        parser.add_argument('--search')
        parser.add_argument('--suggest', action='store_true')
        parser.add_argument('--enable', action='append', default=[], metavar='SLUG')
        parser.add_argument('--list', action='store_true')
        parser.add_argument('--create-set', metavar='NAME')
        parser.add_argument('--keys', help='Comma-separated metric keys for --create-set')
        parser.add_argument('--club-wide', action='store_true')
        parser.add_argument('--default', action='store_true')
        parser.add_argument('--limit', type=int, default=25)

    def handle(self, *args, **o):
        club = Club.objects.filter(slug=o['club']).first()
        if club is None:
            raise CommandError(f"Club '{o['club']}' not found")
        ensure_core_metrics(club)
        total = ProviderMetric.objects.filter(club=club, provider=o['provider']).count()
        if not total and (o['search'] or o['suggest'] or o['enable']):
            raise CommandError('Catalogue is empty: run sync_openfield first.')

        if o['suggest']:
            for theme, words in THEMES.items():
                seen = {}
                for w in words:
                    for pm in search_catalogue(club, w, o['provider'])[:o['limit']]:
                        seen[pm.slug] = pm
                self.stdout.write(self.style.MIGRATE_HEADING(f'\n{theme} — {len(seen)} found'))
                for pm in list(seen.values())[:o['limit']]:
                    self._row(pm)

        if o['search']:
            rows = list(search_catalogue(club, o['search'], o['provider'])[:o['limit']])
            self.stdout.write(self.style.MIGRATE_HEADING(f"'{o['search']}': {len(rows)} shown of {total} parameters"))
            for pm in rows:
                self._row(pm)

        for slug in o['enable']:
            pm = ProviderMetric.objects.filter(club=club, provider=o['provider'], slug=slug).first()
            if pm is None:
                raise CommandError(f'{slug}: not in the catalogue')
            md = enable_from_catalogue(club, pm)
            self.stdout.write(self.style.SUCCESS(
                f'tracking {md.label} as "{md.key}" ({md.category}, {md.aggregation}, {md.unit or "no unit"})'))

        if o['create_set']:
            keys = [k.strip() for k in (o['keys'] or '').split(',') if k.strip()]
            ms = MetricSet(club=club, name=o['create_set'], metric_keys=keys,
                           owner=None, is_default=False)
            ms.full_clean(exclude=['owner'])
            if not o['club_wide']:
                raise CommandError('From the terminal only club-wide sets can be created (add --club-wide).')
            if o['default']:
                MetricSet.objects.filter(club=club, owner__isnull=True, is_default=True).update(is_default=False)
                ms.is_default = True
            ms.save()
            self.stdout.write(self.style.SUCCESS(f'Created club set "{ms.name}" with {len(keys)} metrics'))

        if o['list'] or not any((o['suggest'], o['search'], o['enable'], o['create_set'])):
            self.stdout.write(self.style.MIGRATE_HEADING('Metrics tracked by the club'))
            for md in MetricDefinition.objects.filter(club=club, enabled=True):
                src = 'core' if md.core_field else md.provider_slug
                self.stdout.write(f'  {md.key:42} {md.label[:40]:40} {md.aggregation:13} {md.unit:6} {src}')
            for ms in MetricSet.objects.filter(club=club, owner__isnull=True):
                self.stdout.write(f"  set: {ms.name}{' (default)' if ms.is_default else ''}: {', '.join(ms.metric_keys)}")

    def _row(self, pm):
        g = guess_definition(pm)
        self.stdout.write(f'  {pm.slug:58} {pm.name[:44]:44} {pm.unit_type or "-":10} → {g["category"]}, {g["aggregation"]}')
