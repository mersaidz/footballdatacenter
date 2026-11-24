from datetime import date

import pytest

from clubs.models import Player, Team
from providers.connectors.base import NormalizedPlayer, NormalizedTeam
from providers.models import ExternalIdentity
from providers.services.identity import name_similarity, normalize_name, resolve_player, resolve_team

pytestmark = pytest.mark.django_db
S = ExternalIdentity.Status
M = ExternalIdentity.Method


class TestNames:
    def test_accents_and_punctuation(self):
        assert normalize_name('Ángel Di María') == 'angel di maria'
        assert normalize_name('Martin Ødegaard') == 'martin odegaard'

    def test_token_subset_handles_long_official_names(self):
        assert name_similarity('Lionel Messi', 'Lionel Andrés Messi Cuccittini') == 0.95

    def test_word_order(self):
        assert name_similarity('Messi Lionel', 'Lionel Messi') == 1.0

    def test_single_token_is_not_enough_for_subset(self):
        # "Silva" ⊂ "Bernardo Silva" must not count as the same person.
        assert name_similarity('Silva', 'Bernardo Silva') < 0.92


def _np(ext_id, name, dob=None, known=''):
    return NormalizedPlayer(external_id=ext_id, full_name=name, date_of_birth=dob, known_name=known)


def test_known_mapping_is_reused(club):
    p1 = resolve_player(club, 'statsbomb_open', _np('1', 'Player One'))
    p2 = resolve_player(club, 'statsbomb_open', _np('1', 'Player One (renamed upstream)'))
    assert p1 == p2 and Player.objects.count() == 1


def test_new_player_created_and_confirmed(club):
    p = resolve_player(club, 'statsbomb_open', _np('1', 'Player One'))
    ident = ExternalIdentity.objects.get()
    assert ident.target == p and ident.status == S.CONFIRMED and ident.method == M.CREATED


def test_cross_provider_exact_match_by_dob(club):
    dob = date(1987, 6, 24)
    sb = resolve_player(club, 'statsbomb_open', _np('5503', 'Lionel Andrés Messi Cuccittini', dob))
    impect = resolve_player(club, 'impect', _np('ix-9', 'Lionel Messi', dob))
    assert sb == impect
    ident = ExternalIdentity.objects.get(provider='impect')
    assert ident.method == M.EXACT and ident.status == S.CONFIRMED


def test_different_dob_never_merges(club):
    a = resolve_player(club, 'statsbomb_open', _np('1', 'Danilo', date(1991, 7, 15)))
    b = resolve_player(club, 'impect', _np('2', 'Danilo', date(2001, 4, 29)))
    assert a != b


def test_fuzzy_without_dob_is_linked_but_flagged(club):
    a = resolve_player(club, 'statsbomb_open', _np('1', 'Abzal Beysebekov'))
    b = resolve_player(club, 'catapult_openfield', _np('of-1', 'Abzal Beisebekov'))
    assert a == b
    ident = ExternalIdentity.objects.get(provider='catapult_openfield')
    assert ident.status == S.SUGGESTED and ident.method == M.FUZZY


def test_ambiguous_candidates_create_new_and_flag(club):
    resolve_player(club, 'statsbomb_open', _np('1', 'Ivan Petrov'))
    resolve_player(club, 'wyscout', _np('w1', 'Ivan Petrov'))  # links to the first (fuzzy, flagged)
    Player.objects.create(club=club, full_name='Ivan Petrov')  # manual duplicate, unmapped
    Player.objects.create(club=club, full_name='Ivan Petrov')
    p = resolve_player(club, 'impect', _np('i1', 'Ivan Petrov'))
    ident = ExternalIdentity.objects.get(provider='impect')
    assert ident.status == S.SUGGESTED and ident.method == M.CREATED
    assert len(ident.external_meta['possible_duplicates']) >= 2
    assert p.pk not in ident.external_meta['possible_duplicates']


def test_one_provider_id_per_player(club):
    # Two different StatsBomb IDs with identical names must NOT collapse into one player.
    a = resolve_player(club, 'statsbomb_open', _np('1', 'Same Name'))
    b = resolve_player(club, 'statsbomb_open', _np('2', 'Same Name'))
    assert a != b


def test_tenant_isolation(club, other_club):
    a = resolve_player(club, 'statsbomb_open', _np('1', 'Player One'))
    b = resolve_player(other_club, 'statsbomb_open', _np('1', 'Player One'))
    assert a != b and a.club_id != b.club_id


def test_team_exact_name_match_across_providers(club):
    t = Team.objects.create(club=club, name='FC Astana', is_own=True)
    resolved = resolve_team(club, 'statsbomb_open', NormalizedTeam(external_id='10', name='FC ASTANA'))
    assert resolved == t
