"""
python manage.py wellness --demo          # made-up answers for the last 4 weeks, to see the screens with data
python manage.py wellness --clear-demo    # remove them (real answers are never touched)
python manage.py wellness --link "Name"   # print a player's personal questionnaire link
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from clubs.models import Club, Player
from football.models import PlayerLoad
from football.services import performance as perf
from wellness.models import ITEMS, PlayerLink, RpeEntry, Source, WellnessCheckin

RPE_BY_MD = {'MD': 8, 'MD+1': 2, 'MD+2': 4, 'MD-4': 7, 'MD-3': 6, 'MD-2': 5, 'MD-1': 3}


class Command(BaseCommand):
    help = 'Wellness: demo answers and player links.'

    def add_arguments(self, parser):
        parser.add_argument('--club', help='Club slug (default: the only club)')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--clear-demo', action='store_true')
        parser.add_argument('--days', type=int, default=28)
        parser.add_argument('--link', metavar='PLAYER')
        parser.add_argument('--host', default='http://127.0.0.1:8000')

    def handle(self, *args, **o):
        club = Club.objects.get(slug=o['club']) if o['club'] else Club.objects.first()
        if club is None:
            raise CommandError('No club.')
        if o['clear_demo']:
            a = WellnessCheckin.objects.filter(club=club, source=Source.DEMO).delete()[0]
            b = RpeEntry.objects.filter(club=club, source=Source.DEMO).delete()[0]
            self.stdout.write(f'Removed {a} demo check-ins and {b} demo RPE answers.')
        if o['demo']:
            self.demo(club, o['days'])
        if o['link']:
            p = Player.objects.filter(club=club, full_name__icontains=o['link']).first()
            if p is None:
                raise CommandError(f'No player matching "{o["link"]}".')
            _link, raw = PlayerLink.issue(p)
            self.stdout.write(f'{p.display_name}: {o["host"]}/p/{raw}\n(the previous link of this player no longer works)')

    @transaction.atomic
    def demo(self, club, days):
        team = perf.own_team(club)
        last = perf.last_session_day(team) if team else None
        if last is None:
            raise CommandError('No sessions yet: run a sync first.')
        today = last + timedelta(1)            # the day "Сегодня" shows
        rnd = random.Random(7)
        players = list(Player.objects.filter(club=club, current_team=team))
        md_by_day = {}
        for load in PlayerLoad.objects.filter(training_session__team=team, training_session__start__date__gte=today - timedelta(days)) \
                .select_related('training_session'):
            md_by_day[(load.player_id, load.training_session.start.date())] = (load.training_session, load.training_session.md_code or '')
        tired = set(rnd.sample([p.pk for p in players], k=min(3, len(players))))
        n_c = n_r = 0
        for p in players:
            base = {i: rnd.uniform(3.4, 4.4) for i in ITEMS}
            for k in range(days, -1, -1):
                d = today - timedelta(k)
                if rnd.random() > 0.88 and k:
                    continue
                prev = md_by_day.get((p.pk, d - timedelta(1)))
                after_match = prev and prev[1].split('/')[0] == 'MD'
                vals = {}
                for i in ITEMS:
                    v = base[i] + rnd.gauss(0, 0.45) - (0.8 if after_match and i in ('soreness', 'energy') else 0)
                    if k == 0 and p.pk in tired:
                        v -= 1.8 if i in ('sleep_quality', 'soreness', 'energy') else 0.6
                    vals[i] = max(1, min(5, round(v)))
                sore = rnd.sample(['hamstring', 'quad', 'calf', 'adductor', 'groin', 'lower_back'], k=1 if vals['soreness'] <= 3 else 0)
                WellnessCheckin.objects.update_or_create(player=p, date=d, defaults={
                    **vals, 'club': club, 'sleep_hours': round(max(4.5, min(10, 7.6 + (vals['sleep_quality'] - 3.5) * 0.7 + rnd.gauss(0, 0.4))) * 2) / 2,
                    'sore_areas': sore, 'source': Source.DEMO})
                n_c += 1
                if (sess := md_by_day.get((p.pk, d))) and rnd.random() < 0.9:
                    rpe = max(1, min(10, RPE_BY_MD.get(sess[1].split('/')[0], 5) + rnd.choice((-1, 0, 0, 1))))
                    RpeEntry.objects.update_or_create(player=p, date=d, defaults={'club': club, 'rpe': rpe, 'session': sess[0],
                                                                               'source': Source.DEMO})
                    n_r += 1
        self.stdout.write(f'Demo: {n_c} check-ins and {n_r} RPE answers up to {today} for {len(players)} players '
                          f'(remove with --clear-demo).')
