"""
Ingest StatsBomb Open Data into a club tenant.

Examples:
  # 2022 World Cup (competition 43, season 106), only Argentina's matches,
  # and mark Argentina as the club's own team:
  python manage.py ingest_statsbomb --club demo --competition 43 --season 106 --own-team Argentina

  # Just the final:
  python manage.py ingest_statsbomb --club demo --competition 43 --season 106 --match 3869685

  # List what's available:
  python manage.py ingest_statsbomb --list
"""
from django.core.management.base import BaseCommand, CommandError

from clubs.models import Club
from providers.connectors.statsbomb import StatsBombOpenConnector
from providers.models import Provider, ProviderAccount
from providers.services.ingest import ingest_season


class Command(BaseCommand):
    help = 'Ingest StatsBomb Open Data (matches, lineups, events) for a club.'

    def add_arguments(self, parser):
        parser.add_argument('--club', help='Club slug (created if missing, with --create-club)')
        parser.add_argument('--create-club', action='store_true')
        parser.add_argument('--competition')
        parser.add_argument('--season')
        parser.add_argument('--match', action='append', dest='matches', help='Repeatable')
        parser.add_argument('--own-team', help='Only matches of this team; marks it as the club\'s own team')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--list', action='store_true', help='List available competitions/seasons')

    def handle(self, *args, **opts):
        connector = StatsBombOpenConnector()

        if opts['list']:
            for c in connector.fetch_competitions().payload:
                self.stdout.write(
                    f"{c['competition_id']:>4} / {c['season_id']:<4} {c['competition_name']} — {c['season_name']}"
                )
            return

        if not (opts['club'] and opts['competition'] and opts['season']):
            raise CommandError('--club, --competition and --season are required')

        club = Club.objects.filter(slug=opts['club']).first()
        if club is None:
            if not opts['create_club']:
                raise CommandError(f"Club '{opts['club']}' not found (use --create-club)")
            club = Club.objects.create(slug=opts['club'], name=opts['club'].replace('-', ' ').title())

        account, _ = ProviderAccount.objects.get_or_create(club=club, provider=Provider.STATSBOMB_OPEN)
        connector.account = account

        summary = ingest_season(
            club, connector, opts['competition'], opts['season'],
            match_ids=set(opts['matches']) if opts['matches'] else None,
            limit=opts['limit'], own_team_name=opts['own_team'],
        )

        for m in summary.matches:
            self.stdout.write(
                f'match #{m.match_id}: {m.events} events, {m.appearances} appearances, '
                f'{m.new_players} new players, {m.players_needing_review} need review'
            )
        for err in summary.errors:
            self.stderr.write(self.style.ERROR(err))
        self.stdout.write(self.style.SUCCESS(
            f'Done: {len(summary.matches)} matches, {summary.total_events} events, {len(summary.errors)} errors'
        ))
