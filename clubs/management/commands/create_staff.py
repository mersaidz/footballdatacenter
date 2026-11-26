"""
Give someone a login to the web app.

  python manage.py create_staff --club demo --email you@club.com --role sports_scientist --name "Mersaid Z."

Asks for the password (never pass it on the command line). Re-running updates role / language.
Roles: club_admin, sporting_director, head_coach, assistant_coach, analyst, sports_scientist,
physio, doctor, scout.
"""
import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from clubs.models import Club, StaffMembership


class Command(BaseCommand):
    help = 'Create or update a staff login for a club.'

    def add_arguments(self, parser):
        parser.add_argument('--club', required=True)
        parser.add_argument('--email', required=True)
        parser.add_argument('--role', required=True, choices=StaffMembership.Role.values)
        parser.add_argument('--name', default='')
        parser.add_argument('--language', default='ru', choices=['ru', 'en', 'kk'])
        parser.add_argument('--password-stdin', action='store_true', help='Read the password from stdin (scripts/tests)')

    def handle(self, *args, **o):
        club = Club.objects.filter(slug=o['club']).first()
        if club is None:
            raise CommandError(f"Club '{o['club']}' not found")
        email = o['email'].strip().lower()
        user = User.objects.filter(email=email).first()
        password = None
        if user is None or not user.has_usable_password():
            if o['password_stdin']:
                password = input().strip()
            else:
                password = getpass.getpass('Password (10+ characters): ')
                if password != getpass.getpass('Repeat password: '):
                    raise CommandError('Passwords do not match.')
            if len(password) < 10:
                raise CommandError('Use at least 10 characters.')
        with transaction.atomic():
            if user is None:
                user = User.objects.create_user(email=email, password=password, full_name=o['name'], language=o['language'])
            else:
                user.language = o['language']
                if o['name']:
                    user.full_name = o['name']
                if password:
                    user.set_password(password)
                user.save()
            StaffMembership.objects.update_or_create(user=user, club=club, defaults={'role': o['role'], 'is_active': True})
        self.stdout.write(self.style.SUCCESS(f'{email}: {o["role"]} at {club.name}. Log in at http://127.0.0.1:8000/'))
