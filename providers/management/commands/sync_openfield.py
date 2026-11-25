"""
Pull activities and per-athlete load from Catapult OpenField.

  python manage.py sync_openfield --club demo --team "First Team" --days 90
  python manage.py sync_openfield --club demo --team "First Team" --from 2026-09-01 --to 2026-11-30

Token: ProviderAccount.api_key for the club, else OPENFIELD_API_TOKEN from .env.
Read-only — the token only needs "Summary Data" scope.
"""
from datetime import datetime, time, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError

from clubs.models import Club, Team
from providers.connectors.openfield import OpenFieldConnector, OpenFieldError
from providers.models import Provider, ProviderAccount
from providers.services.physical_ingest import ingest_physical


def _day(value: str, end_of_day=False) -> datetime:
    d = datetime.strptime(value, '%Y-%m-%d').date()
    return datetime.combine(d, time.max if end_of_day else time.min, tzinfo=timezone.utc)


class Command(BaseCommand):
    help = 'Sync activities and player load from Catapult OpenField (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--club', required=True, help='Club slug')
        parser.add_argument('--create-club', action='store_true')
        parser.add_argument('--team', default='First Team', help="Club's own team these athletes belong to")
        parser.add_argument('--days', type=int, default=90, help='Look-back window (ignored with --from)')
        parser.add_argument('--from', dest='date_from', help='YYYY-MM-DD')
        parser.add_argument('--to', dest='date_to', help='YYYY-MM-DD (default today)')
        parser.add_argument('--region', help='eu / us / au (default from account or OPENFIELD_REGION)')

    def handle(self, *args, **opts):
        club = Club.objects.filter(slug=opts['club']).first()
        if club is None:
            if not opts['create_club']:
                raise CommandError(f"Club '{opts['club']}' not found (use --create-club)")
            club = Club.objects.create(slug=opts['club'], name=opts['club'].replace('-', ' ').title())

        team, created = Team.objects.get_or_create(club=club, name=opts['team'], defaults={'is_own': True})
        if not team.is_own:
            team.is_own = True
            team.save(update_fields=['is_own', 'updated_at'])
        if created:
            self.stdout.write(f'Created own team "{team.name}"')

        account, _ = ProviderAccount.objects.get_or_create(club=club, provider=Provider.CATAPULT_OPENFIELD)

        end = _day(opts['date_to'], end_of_day=True) if opts['date_to'] else datetime.now(timezone.utc)
        start = _day(opts['date_from']) if opts['date_from'] else end - timedelta(days=opts['days'])

        try:
            connector = OpenFieldConnector(account, region=opts['region'])
            summary = ingest_physical(club, connector, team, start, end)
        except OpenFieldError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f'{summary.activities} activities → {summary.sessions_created} sessions created, '
            f'{summary.sessions_updated} updated, {summary.linked_to_matches} linked to matches, '
            f'{summary.loads} player loads'
        )
        for err in summary.errors:
            self.stderr.write(self.style.ERROR(err))
        style = self.style.SUCCESS if not summary.errors else self.style.WARNING
        self.stdout.write(style(f'Done ({start:%Y-%m-%d} → {end:%Y-%m-%d}), {len(summary.errors)} errors'))
