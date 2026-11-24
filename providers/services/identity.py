"""
Cross-provider identity resolution — the heart of a multi-source platform.

Problem: the same player is "5503" in StatsBomb, a UUID in OpenField and
"1234" in IMPECT, spelled "Lionel Andrés Messi Cuccittini", "Lionel Messi"
or "L. Messi". Every metric that joins physical and technical data depends
on getting this right.

Strategy, in order:
  1. Known mapping (ExternalIdentity) → reuse. O(1), the hot path.
  2. Candidate search among this club's records that have NO mapping for
     this provider yet (one provider ID per internal object — DB-enforced).
       - date of birth equal + names compatible → EXACT, confirmed.
       - date of birth differs                → never the same person.
       - no DOB, very strong name match        → FUZZY, linked but `suggested`
                                                (an analyst confirms in the API).
       - several equally good candidates       → do NOT guess; create a new
                                                record, flag it `suggested`.
  3. Nothing found → create the internal record, mapping is `confirmed`.

Wrong merges are far more expensive than duplicates (a duplicate is visible
and fixable; a wrong merge silently mixes two players' loads), so every
threshold errs towards "create + flag".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Iterable

from django.contrib.contenttypes.models import ContentType
from django.db import models

from clubs.models import Club, Player, Team
from football.models import Competition, Match, Season
from providers.connectors.base import (
    NormalizedCompetition,
    NormalizedMatch,
    NormalizedPlayer,
    NormalizedSeason,
    NormalizedTeam,
)
from providers.models import ExternalIdentity

EntityType = ExternalIdentity.EntityType
Status = ExternalIdentity.Status
Method = ExternalIdentity.Method

AUTO_LINK_NAME_SCORE = 0.92    # without DOB: only near-identical names are linked
DOB_NAME_SCORE = 0.60          # with matching DOB: names only need to be compatible
AMBIGUITY_MARGIN = 0.03


# --- name similarity -------------------------------------------------------------

def normalize_name(name: str) -> str:
    """'Lionel Andrés Messi-Cuccittini' → 'lionel andres messi cuccittini'"""
    decomposed = unicodedata.normalize('NFKD', name or '')
    ascii_only = ''.join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9 ]+", ' ', ascii_only.lower().replace('ø', 'o').replace('ß', 'ss'))
    return re.sub(r'\s+', ' ', cleaned).strip()


def name_similarity(a: str, b: str) -> float:
    """
    0..1 score robust to accents, word order and extra middle/second surnames.
    "Lionel Messi" vs "Lionel Andrés Messi Cuccittini" → 0.95 (token subset).
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta == tb:
        return 1.0  # same words, different order: "Messi Lionel"
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) >= 2 and shorter <= longer:
        return 0.95
    return SequenceMatcher(None, ' '.join(sorted(ta)), ' '.join(sorted(tb))).ratio()


def best_name_score(candidate_names: Iterable[str], incoming_names: Iterable[str]) -> float:
    incoming = [n for n in incoming_names if n]
    return max(
        (name_similarity(c, i) for c in candidate_names if c for i in incoming),
        default=0.0,
    )


# --- mapping helpers -----------------------------------------------------------

def get_mapped(club: Club, provider: str, entity_type: str, external_id: str, model: type[models.Model]):
    identity = (
        ExternalIdentity.objects
        .filter(club=club, provider=provider, entity_type=entity_type, external_id=external_id)
        .only('object_id')
        .first()
    )
    if identity is None:
        return None
    return model.objects.filter(pk=identity.object_id, club=club).first()


def link(
    club: Club, provider: str, entity_type: str, external_id: str, obj: models.Model, *,
    method: str, status: str = Status.CONFIRMED, confidence: float = 1.0,
    external_name: str = '', external_meta: dict | None = None,
) -> ExternalIdentity:
    return ExternalIdentity.objects.create(
        club=club, provider=provider, entity_type=entity_type, external_id=external_id,
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk,
        method=method, status=status, confidence=Decimal(str(round(confidence, 3))),
        external_name=external_name[:200], external_meta=external_meta or {},
    )


def _unmapped_for_provider(qs: models.QuerySet, club: Club, provider: str) -> models.QuerySet:
    mapped_ids = ExternalIdentity.objects.filter(
        club=club, provider=provider, content_type=ContentType.objects.get_for_model(qs.model),
    ).values('object_id')
    return qs.exclude(pk__in=mapped_ids)


# --- resolvers -----------------------------------------------------------------

@dataclass
class PlayerMatch:
    player: Player
    score: float
    method: str


def _score_player_candidates(club: Club, provider: str, incoming: NormalizedPlayer) -> list[PlayerMatch]:
    candidates = _unmapped_for_provider(Player.objects.filter(club=club), club, provider)
    names = (incoming.full_name, incoming.known_name)
    scored: list[PlayerMatch] = []
    for cand in candidates.only('id', 'full_name', 'known_name', 'date_of_birth'):
        score = best_name_score((cand.full_name, cand.known_name), names)
        if incoming.date_of_birth and cand.date_of_birth:
            if incoming.date_of_birth != cand.date_of_birth:
                continue  # different people, however similar the name
            if score >= DOB_NAME_SCORE:
                scored.append(PlayerMatch(cand, min(0.99, 0.8 + score / 5), Method.EXACT))
        elif score >= AUTO_LINK_NAME_SCORE:
            scored.append(PlayerMatch(cand, score, Method.FUZZY))
    return sorted(scored, key=lambda m: m.score, reverse=True)


def resolve_player(club: Club, provider: str, incoming: NormalizedPlayer, team: Team | None = None) -> Player:
    existing = get_mapped(club, provider, EntityType.PLAYER, incoming.external_id, Player)
    if existing is not None:
        return existing

    meta = {'date_of_birth': incoming.date_of_birth.isoformat() if incoming.date_of_birth else None,
            'known_name': incoming.known_name}
    matches = _score_player_candidates(club, provider, incoming)
    ambiguous = len(matches) > 1 and matches[0].score - matches[1].score < AMBIGUITY_MARGIN

    if matches and not ambiguous:
        best = matches[0]
        link(club, provider, EntityType.PLAYER, incoming.external_id, best.player,
             method=best.method,
             status=Status.CONFIRMED if best.method == Method.EXACT else Status.SUGGESTED,
             confidence=best.score, external_name=incoming.full_name, external_meta=meta)
        return best.player

    player = Player.objects.create(
        club=club,
        full_name=incoming.full_name,
        known_name=incoming.known_name,
        date_of_birth=incoming.date_of_birth,
        nationality=incoming.nationality,
        current_team=team,
    )
    if ambiguous:
        meta['possible_duplicates'] = [m.player.pk for m in matches[:5]]
    link(club, provider, EntityType.PLAYER, incoming.external_id, player,
         method=Method.CREATED,
         status=Status.SUGGESTED if ambiguous else Status.CONFIRMED,
         confidence=0.5 if ambiguous else 1.0,
         external_name=incoming.full_name, external_meta=meta)
    return player


def resolve_team(club: Club, provider: str, incoming: NormalizedTeam) -> Team:
    existing = get_mapped(club, provider, EntityType.TEAM, incoming.external_id, Team)
    if existing is not None:
        return existing
    target = normalize_name(incoming.name)
    for cand in _unmapped_for_provider(Team.objects.filter(club=club, gender=incoming.gender), club, provider):
        if normalize_name(cand.name) == target:
            link(club, provider, EntityType.TEAM, incoming.external_id, cand,
                 method=Method.EXACT, external_name=incoming.name)
            return cand
    team = Team.objects.create(club=club, name=incoming.name, gender=incoming.gender, country=incoming.country)
    link(club, provider, EntityType.TEAM, incoming.external_id, team,
         method=Method.CREATED, external_name=incoming.name)
    return team


def resolve_competition(club: Club, provider: str, incoming: NormalizedCompetition) -> Competition:
    existing = get_mapped(club, provider, EntityType.COMPETITION, incoming.external_id, Competition)
    if existing is not None:
        return existing
    comp, created = Competition.objects.get_or_create(
        club=club, name=incoming.name, gender=incoming.gender, defaults={'country': incoming.country},
    )
    link(club, provider, EntityType.COMPETITION, incoming.external_id, comp,
         method=Method.CREATED if created else Method.EXACT, external_name=incoming.name)
    return comp


def resolve_season(club: Club, provider: str, competition: Competition, incoming: NormalizedSeason) -> Season:
    # Season IDs are provider-global (StatsBomb season 106 = "2022" for every competition),
    # so the mapping key includes the competition.
    key = f'{competition.pk}:{incoming.external_id}'
    existing = get_mapped(club, provider, EntityType.SEASON, key, Season)
    if existing is not None:
        return existing
    season, created = Season.objects.get_or_create(club=club, competition=competition, name=incoming.name)
    link(club, provider, EntityType.SEASON, key, season,
         method=Method.CREATED if created else Method.EXACT, external_name=incoming.name)
    return season


def resolve_match(club: Club, provider: str, incoming: NormalizedMatch) -> tuple[Match, bool]:
    """Returns (match, created). Matches a fixture another provider already created by teams + date."""
    home = resolve_team(club, provider, incoming.home_team)
    away = resolve_team(club, provider, incoming.away_team)
    season = None
    if incoming.competition:
        comp = resolve_competition(club, provider, incoming.competition)
        if incoming.season:
            season = resolve_season(club, provider, comp, incoming.season)

    fields = dict(
        season=season, home_team=home, away_team=away, kickoff=incoming.kickoff, status=incoming.status,
        home_score=incoming.home_score, away_score=incoming.away_score,
        stage=incoming.stage, venue=incoming.venue,
    )

    existing = get_mapped(club, provider, EntityType.MATCH, incoming.external_id, Match)
    if existing is not None:
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.save()
        return existing, False

    same_fixture = _unmapped_for_provider(
        Match.objects.filter(club=club, home_team=home, away_team=away, kickoff__date=incoming.kickoff.date()),
        club, provider,
    ).first()
    if same_fixture is not None:
        link(club, provider, EntityType.MATCH, incoming.external_id, same_fixture, method=Method.EXACT)
        return same_fixture, False

    match = Match.objects.create(club=club, **fields)
    link(club, provider, EntityType.MATCH, incoming.external_id, match, method=Method.CREATED)
    return match, True
