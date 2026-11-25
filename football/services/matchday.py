"""
Match-day (MD) codes — the calendar language of football performance staff.

    MD      match day
    MD-1    day before the next match (MD-2, MD-3 … further out)
    MD+1    day after the previous match (MD+2 …)

When a day sits between two close matches the "after" code wins for the
first two days (recovery phase), then the countdown to the next match.
Providers that tag sessions themselves (OpenField DayCode tags) take
precedence; this is the fallback.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Q

from clubs.models import Team
from football.models import Match, TrainingSession

RECOVERY_DAYS = 2
LOOKAROUND_DAYS = 7


def match_dates(team: Team, around: date) -> list[date]:
    lo = date.fromordinal(around.toordinal() - LOOKAROUND_DAYS)
    hi = date.fromordinal(around.toordinal() + LOOKAROUND_DAYS)
    dates = set(
        Match.objects.filter(Q(home_team=team) | Q(away_team=team), kickoff__date__range=(lo, hi))
        .values_list('kickoff__date', flat=True)
    )
    dates |= set(
        TrainingSession.objects.filter(team=team, session_type='match', start__date__range=(lo, hi))
        .values_list('start__date', flat=True)
    )
    return sorted(dates)


def md_code_for(day: date, match_days: list[date]) -> str:
    if day in match_days:
        return 'MD'
    before = [d for d in match_days if d < day]
    after = [d for d in match_days if d > day]
    since = (day - before[-1]).days if before else None
    until = (after[0] - day).days if after else None
    if since is not None and since <= RECOVERY_DAYS:
        return f'MD+{since}'
    if until is not None and until <= LOOKAROUND_DAYS:
        return f'MD-{until}'
    if since is not None and since <= LOOKAROUND_DAYS:
        return f'MD+{since}'
    return ''
