"""
Load an IMPECT competition season: lineups, positions, per-match KPIs for every player,
full events for one squad.

  # IMPECT open data (Bundesliga 23/24, iteration 743), Leverkusen events, demo-linked to our squad
  python manage.py ingest_impect --club demo --open-data --iteration 743 --squad Leverkusen --demo-link "First Team"

  # a club's own IMPECT account (IMPECT_USERNAME / IMPECT_PASSWORD in .env)
  python manage.py ingest_impect --club demo --list
  python manage.py ingest_impect --club demo --iteration <id> --squad "<our team in IMPECT>"

Open data licence: analysis and research only, no redistribution, credit IMPECT.
It's fetched from IMPECT's GitHub on demand and never stored in this repository.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from clubs.models import Club, Team
from providers.connectors.impect import CREDIT, ImpectApiSource, ImpectConnector, ImpectError, ImpectOpenData
from providers.services.impect_ingest import ingest_impect


class Command(BaseCommand):
    help = 'Ingest an IMPECT season (open data or customer API).'

    def add_arguments(self, parser):
        parser.add_argument('--club', required=True)
        parser.add_argument('--open-data', action='store_true', help='Use IMPECT open data instead of the API')
        parser.add_argument('--cache-dir', help='Keep downloaded open-data files here (gitignored data/ folder)')
        parser.add_argument('--list', action='store_true', help='List the seasons this source offers')
        parser.add_argument('--iteration', help='IMPECT iteration (competition season) id')
        parser.add_argument('--squad', help='Full events for this squad’s matches (name or part of it)')
        parser.add_argument('--demo-link', metavar='OUR_TEAM',
                            help='Demo only: pair our team’s players with --squad’s players (GK↔GK, then by minutes)')
        parser.add_argument('--goalkeepers', help='Our goalkeepers’ player ids for --demo-link (default: detected from GPS)')
        parser.add_argument('--limit', type=int, help='Only the first N matches (testing)')

    def handle(self, *args, **o):
        club = Club.objects.filter(slug=o['club']).first()
        if club is None:
            raise CommandError(f"Club '{o['club']}' not found")
        if o['open_data']:
            source = ImpectOpenData(cache_dir=o['cache_dir'])
        else:
            user, pwd = os.environ.get('IMPECT_USERNAME'), os.environ.get('IMPECT_PASSWORD')
            if not (user and pwd):
                raise CommandError('Set IMPECT_USERNAME and IMPECT_PASSWORD in .env, or use --open-data.')
            source = ImpectApiSource(user, pwd)
        connector = ImpectConnector(source)

        try:
            if o['list'] or not o['iteration']:
                for it in source.iterations():
                    comp = it.get('competition') or {}
                    self.stdout.write(f"  {it['id']:>6}  {comp.get('name', '?'):30} {it.get('season', '')}")
                if not o['iteration']:
                    return
            our_team = None
            if o['demo_link']:
                if not o['squad']:
                    raise CommandError('--demo-link needs --squad (the IMPECT squad to borrow data from).')
                our_team = Team.objects.filter(club=club, name__iexact=o['demo_link']).first()
                if our_team is None:
                    raise CommandError(f"Team '{o['demo_link']}' not found in {club}")
            gks = {int(x) for x in o['goalkeepers'].split(',')} if o['goalkeepers'] else None

            def progress(i, n, m):
                if i == 1 or i % 25 == 0 or i == n:
                    self.stdout.write(f'  {i}/{n} {m.home_team.name} – {m.away_team.name}')

            s = ingest_impect(club, connector, o['iteration'], events_squad=o['squad'], demo_link_to=our_team,
                              goalkeepers=gks, limit=o['limit'], progress=progress)
        except (ImpectError, ValueError) as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f'{s.competition}: {s.matches} matches, {s.appearances} appearances, {s.kpi_rows} player KPI rows, '
            f'{s.events} events in {s.matches_with_events} matches, {s.players_created} new players'))
        if s.demo_links:
            self.stdout.write(self.style.WARNING('Demo links (football data borrowed from another player):'))
            for ours, theirs, pos, mins in s.demo_links:
                self.stdout.write(f'  {ours:24} ← {theirs:28} {pos.lower().replace("_", " "):24} {mins} min')
        for e in s.errors[:10]:
            self.stdout.write(self.style.ERROR(f'  {e}'))
        if o['open_data']:
            self.stdout.write(f'{CREDIT} open data — analysis and research only, not for redistribution.')
