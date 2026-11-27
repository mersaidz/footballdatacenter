"""Scoring check-ins against the player's own normal, and session RPE → sRPE."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, pstdev

from football.models import PlayerLoad, TrainingSession

from .models import ITEMS, RpeEntry, WellnessCheckin

BASELINE_DAYS, BASELINE_MIN = 28, 5
SD_FLOOR = 2.0          # points of the 5–25 total: a very steady player shouldn't be flagged for one point


def default_day(club, today: date) -> date:
    """Today — unless the club has no recent answers at all (old or demo data): then its latest answered day."""
    latest = WellnessCheckin.objects.filter(club=club, date__lte=today).order_by('-date').values_list('date', flat=True).first()
    return today if latest is None or latest >= today - timedelta(3) else latest


def baseline(player, before: date) -> dict | None:
    """Mean and SD of the player's last 28 days (needs 5+ check-ins)."""
    rows = list(WellnessCheckin.objects.filter(player=player, date__lt=before, date__gte=before - timedelta(BASELINE_DAYS)))
    if len(rows) < BASELINE_MIN:
        return None
    out = {'n': len(rows)}
    for key in ITEMS + ('total',):
        vals = [getattr(r, key) for r in rows]
        out[key] = (round(mean(vals), 2), round(pstdev(vals), 2))
    return out


def assess(c: WellnessCheckin, base: dict | None) -> dict:
    """
    level: ok / low / very_low, judged against the player's own normal (28 days):
      very_low: any item at 1, or the total 2+ SD under his normal
      low:      the total 1+ SD under his normal, or one item 2+ points under his usual for it
    The day after a match everyone is sore; a player's normal already includes that, so a 2 alone isn't a flag.
    Without a normal yet (first 5 answers), any 2 counts as low.
    """
    z, flags = None, []
    if base:
        m, sd = base['total']
        z = round((c.total - m) / max(sd, SD_FLOOR), 2)
        flags = [i for i in ITEMS if getattr(c, i) <= base[i][0] - 2 or getattr(c, i) == 1]
    else:
        flags = [i for i in ITEMS if getattr(c, i) <= 2]
    if any(getattr(c, i) == 1 for i in ITEMS) or (z is not None and z <= -2):
        level = 'very_low'
    elif flags or (z is not None and z <= -1):
        level = 'low'
    else:
        level = 'ok'
    if level != 'ok' and not flags:       # say which answers pulled the total down
        flags = [i for i in ITEMS if base and getattr(c, i) < base[i][0] - 0.75]
    return {'date': c.date.isoformat(), 'total': c.total, 'z': z, 'level': level, 'flags': flags,
            'normal': round(base['total'][0], 1) if base else None, 'worst': min(getattr(c, i) for i in ITEMS)}


def checkin_detail(c: WellnessCheckin) -> dict:
    return {**{i: getattr(c, i) for i in ITEMS}, 'sleep_hours': float(c.sleep_hours) if c.sleep_hours is not None else None,
            'sore_areas': c.sore_areas, 'comment': c.comment, 'source': c.source}


def day_summary(players, day: date) -> dict[int, dict]:
    by_player = {c.player_id: c for c in WellnessCheckin.objects.filter(player__in=players, date=day)}
    return {pid: {**assess(c, baseline(c.player, day)), **checkin_detail(c)} for pid, c in by_player.items()}


def rpe_for_session(session: TrainingSession) -> dict[int, dict]:
    """player → {rpe, srpe}. Entries linked to the session, or same-day entries not linked yet."""
    entries = RpeEntry.objects.filter(player__club=session.club, date=session.start.date())
    minutes = dict(PlayerLoad.objects.filter(training_session=session).values_list('player_id', 'duration_min'))
    out = {}
    for e in entries:
        if e.session_id not in (None, session.pk):
            continue
        mins = float(minutes[e.player_id]) if minutes.get(e.player_id) is not None else None
        out[e.player_id] = {'rpe': e.rpe, 'srpe': round(e.rpe * mins) if mins is not None else None, 'source': e.source}
    return out


def link_rpe(entry: RpeEntry) -> None:
    """Attach a day's RPE to the player's main session that day (most minutes), once the sync has made it."""
    if entry.session_id:
        return
    load = (PlayerLoad.objects.filter(player=entry.player, training_session__start__date=entry.date)
            .order_by('-duration_min').select_related('training_session').first())
    if load:
        entry.session = load.training_session
        entry.save(update_fields=['session', 'updated_at'])


def recent_sessions(player, today: date, days: int = 2) -> list[TrainingSession]:
    """Sessions the player can still rate: his team's last two days."""
    if not player.current_team_id:
        return []
    return list(TrainingSession.objects.filter(team_id=player.current_team_id, start__date__gte=today - timedelta(days),
                                               start__date__lte=today).order_by('-start'))


MONOTONY_HIGH, HARDER_THAN_USUAL = 2.0, 1.25


def internal_load(player, end: date) -> dict:
    """
    Foster's session-RPE family for the 7 days up to `end`:
      week load (sum of sRPE), monotony (daily mean / SD, rest days count as 0; > 2 = every day alike),
      strain (load × monotony); and "felt harder than usual": sRPE per km of his last rated session
      against his own 28-day average (≥ 1.25× is an early sign of fatigue or illness).
    """
    entries = list(RpeEntry.objects.filter(player=player, date__gt=end - timedelta(35), date__lte=end)
                   .select_related('session').order_by('date'))
    for e in entries:
        link_rpe(e)
    loads = {pl.training_session_id: pl for pl in PlayerLoad.objects.filter(
        player=player, training_session_id__in=[e.session_id for e in entries if e.session_id])}
    daily, ratios = {}, []
    for e in entries:
        pl = loads.get(e.session_id)
        mins = float(pl.duration_min) if pl and pl.duration_min else None
        if mins:
            daily[e.date] = daily.get(e.date, 0) + e.rpe * mins
            km = float(pl.total_distance_m or 0) / 1000
            if km >= 1:
                ratios.append((e.date, e.rpe * mins / km))
    week = [daily.get(end - timedelta(k), 0) for k in range(7)]
    load = sum(week)
    sd = pstdev(week)
    monotony = round(mean(week) / sd, 2) if load and sd else None
    out = {'week_load': round(load), 'monotony': monotony, 'strain': round(load * monotony) if monotony else None,
           'monotony_high': bool(monotony and monotony > MONOTONY_HIGH), 'harder': None}
    if ratios:
        last_day, last = ratios[-1]
        before = [r for d, r in ratios[:-1] if d >= last_day - timedelta(28)]
        if len(before) >= 4:
            usual = mean(before)
            out['harder'] = {'date': last_day.isoformat(), 'ratio': round(last / usual, 2),
                             'flag': last >= HARDER_THAN_USUAL * usual}
    return out
